import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AgentRuntimeLink(Base):
    """Persistent binding between a chat session and an agent runtime session."""

    __tablename__ = "agent_runtime_links"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    runtime_name: Mapped[str] = mapped_column(String(64), nullable=False)
    runtime_session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    runtime_conversation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    base_system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    metadata_json: Mapped[str] = mapped_column("metadata", Text, nullable=False, default="{}")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    session: Mapped["ChatSession"] = relationship(back_populates="runtime_link")


class AgentRuntimeSnapshotRecord(Base):
    """Stored runtime snapshot captured after a turn completes."""

    __tablename__ = "agent_runtime_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("chat_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    runtime_name: Mapped[str] = mapped_column(String(64), nullable=False)
    runtime_session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    snapshot_payload: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    session: Mapped["ChatSession"] = relationship(back_populates="runtime_snapshots")
    run: Mapped["ChatRun | None"] = relationship(back_populates="runtime_snapshots")
