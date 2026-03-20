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
    state: dict[str, Any] = Field(default_factory=dict)


class ChatSessionPdfResourceOut(BaseModel):
    pdf_id: int
    filename: str
    status: str
    source: str
    source_url: str | None = None


class ChatRunEventOut(BaseModel):
    id: int
    sequence: int
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class ChatRunOut(BaseModel):
    id: int
    assistant_message_id: int | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    events: list[ChatRunEventOut] = Field(default_factory=list)


ChatSessionDetail.model_rebuild()
