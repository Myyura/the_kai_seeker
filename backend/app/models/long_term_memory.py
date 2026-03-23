import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LongTermMemoryRecord(Base):
    """Derived long-term memory records produced by the host from chat activity."""

    __tablename__ = "long_term_memory_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    memory_type: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(128), nullable=False, default="global")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    importance: Mapped[float] = mapped_column(nullable=False, default=0.5)
    # TODO: Replace this placeholder field usage with evidence-based confidence scoring.
    # Future scoring should consider explicit user statements, repetition, tool support,
    # and contradictions with stronger existing memory.
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.5)
    source_session_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("chat_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_run_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("chat_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    related_target_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("study_targets.id", ondelete="SET NULL"),
        nullable=True,
    )
    tags: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
