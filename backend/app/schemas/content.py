from typing import Any

from pydantic import BaseModel, Field


class ContentSyncFieldOptionOut(BaseModel):
    label: str
    value: str


class ContentSyncFieldOut(BaseModel):
    name: str
    label: str
    type: str
    required: bool
    default: str | None = None
    options: list[ContentSyncFieldOptionOut] = Field(default_factory=list)


class ContentSyncSourceOut(BaseModel):
    id: str
    name: str
    kind: str
    description: str
    enabled: bool = True
    is_default: bool = False
    config_fields: list[ContentSyncFieldOut] = Field(default_factory=list)


class ContentSyncSourcesOut(BaseModel):
    sources: list[ContentSyncSourceOut]
    default_source_id: str | None = None


class ContentSyncRequest(BaseModel):
    source_id: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class ContentSyncResultOut(BaseModel):
    status: str
    message: str
    source_id: str
    schools_count: int | None = None
    questions_count: int | None = None
