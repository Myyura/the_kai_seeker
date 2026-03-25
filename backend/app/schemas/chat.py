from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ChatMessageIn(BaseModel):
    role: str = "user"
    content: str


class ChatRequest(BaseModel):
    session_id: int | None = None
    messages: list[ChatMessageIn]
    pdf_ids: list[int] = Field(default_factory=list)
    stream: bool = False


class ChatResponseOut(BaseModel):
    session_id: int
    role: str = "assistant"
    content: str
    model: str | None = None


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    model: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatSessionOut(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatSessionDetail(ChatSessionOut):
    messages: list[ChatMessageOut]
    runs: list["ChatRunOut"] = Field(default_factory=list)
    short_term_memory: dict[str, Any] = Field(default_factory=dict)


class ChatSessionPdfResourceOut(BaseModel):
    pdf_id: int
    filename: str
    status: str
    source: str
    source_url: str | None = None


class ChatToolArtifactOut(BaseModel):
    id: int
    kind: str
    label: str | None = None
    summary: str
    summary_format: str
    locator: dict[str, Any] = Field(default_factory=dict)
    replay: dict[str, Any] | None = None
    is_primary: bool = True
    created_at: datetime


class ChatToolCallOut(BaseModel):
    id: int
    sequence: int
    call_id: str
    tool_name: str
    display_name: str | None = None
    activity_label: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    success: bool = True
    status: str
    error_text: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    artifacts: list[ChatToolArtifactOut] = Field(default_factory=list)
    created_at: datetime


class ChatRunOut(BaseModel):
    id: int
    assistant_message_id: int | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    tool_calls: list[ChatToolCallOut] = Field(default_factory=list)


ChatSessionDetail.model_rebuild()
