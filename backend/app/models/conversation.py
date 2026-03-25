import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ChatSession(Base):
    """A conversation session containing multiple messages."""

    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False, default="New Chat")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.id",
    )
    pdf_resources: Mapped[list["ChatSessionPdfResource"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="ChatSessionPdfResource.id"
    )
    runs: Mapped[list["ChatRun"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="ChatRun.id"
    )
    short_term_memory: Mapped["ChatSessionShortTermMemory | None"] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        uselist=False,
    )
    runtime_link: Mapped["AgentRuntimeLink | None"] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        uselist=False,
    )
    runtime_snapshots: Mapped[list["AgentRuntimeSnapshotRecord"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AgentRuntimeSnapshotRecord.id",
    )


class ChatMessage(Base):
    """A single message within a conversation session."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    session: Mapped["ChatSession"] = relationship(back_populates="messages")
    run: Mapped["ChatRun | None"] = relationship(back_populates="assistant_message")


class ChatRun(Base):
    """One assistant run for a user turn."""

    __tablename__ = "chat_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    assistant_message_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    session: Mapped["ChatSession"] = relationship(back_populates="runs")
    assistant_message: Mapped["ChatMessage | None"] = relationship(back_populates="run")
    tool_calls: Mapped[list["ChatToolCall"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="ChatToolCall.sequence",
    )
    runtime_snapshots: Mapped[list["AgentRuntimeSnapshotRecord"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AgentRuntimeSnapshotRecord.id",
    )


class ChatToolCall(Base):
    """A persisted tool call executed during a run."""

    __tablename__ = "chat_tool_calls"
    __table_args__ = (UniqueConstraint("run_id", "sequence", name="uq_tool_call_sequence"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chat_runs.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    call_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_item_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    activity_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    arguments_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    output_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    run: Mapped["ChatRun"] = relationship(back_populates="tool_calls")
    artifacts: Mapped[list["ChatToolArtifact"]] = relationship(
        back_populates="tool_call",
        cascade="all, delete-orphan",
        order_by="ChatToolArtifact.id",
    )


class ChatToolArtifact(Base):
    """A persisted artifact produced by a tool call."""

    __tablename__ = "chat_tool_artifacts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tool_call_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("chat_tool_calls.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary_format: Mapped[str] = mapped_column(String(16), nullable=False, default="text")
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    locator_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    replay_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tool_call: Mapped["ChatToolCall"] = relationship(back_populates="artifacts")


class ChatSessionPdfResource(Base):
    """PDF resources associated with a chat session."""

    __tablename__ = "chat_session_pdf_resources"
    __table_args__ = (UniqueConstraint("session_id", "pdf_id", name="uq_session_pdf"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    pdf_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pdf_documents.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(16), nullable=False, default="uploaded")
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    session: Mapped["ChatSession"] = relationship(back_populates="pdf_resources")


class ChatSessionShortTermMemory(Base):
    """Structured short-term memory used by the native AgentRuntime."""

    __tablename__ = "chat_session_short_term_memories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    payload: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    session: Mapped["ChatSession"] = relationship(back_populates="short_term_memory")
