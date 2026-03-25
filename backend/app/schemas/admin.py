from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AdminResourceOut(BaseModel):
    id: str
    label: str
    description: str
    href: str
    available: bool = True


class AdminResourcesOut(BaseModel):
    resources: list[AdminResourceOut]


class AdminConversationListItemOut(BaseModel):
    id: int
    title: str
    message_count: int
    run_count: int
    pdf_count: int
    created_at: datetime
    updated_at: datetime


class AdminConversationListOut(BaseModel):
    items: list[AdminConversationListItemOut]
    count: int


class AdminConversationMessageOut(BaseModel):
    id: int
    role: str
    content: str
    model: str | None = None
    created_at: datetime


class AdminConversationToolArtifactOut(BaseModel):
    id: int
    kind: str
    label: str | None = None
    summary: str
    summary_format: str
    locator: dict[str, Any] = Field(default_factory=dict)
    replay: dict[str, Any] | None = None
    is_primary: bool = True
    created_at: datetime


class AdminConversationToolCallOut(BaseModel):
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
    artifacts: list[AdminConversationToolArtifactOut] = Field(default_factory=list)
    created_at: datetime


class AdminConversationRunOut(BaseModel):
    id: int
    assistant_message_id: int | None = None
    status: str
    tool_call_count: int
    artifact_count: int
    created_at: datetime
    updated_at: datetime
    tool_calls: list[AdminConversationToolCallOut] = Field(default_factory=list)
    snapshot: dict[str, Any] = Field(default_factory=dict)


class AdminConversationPdfOut(BaseModel):
    pdf_id: int
    filename: str
    status: str
    source: str
    source_url: str | None = None


class AdminConversationRuntimeSnapshotOut(BaseModel):
    id: int
    created_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class AdminConversationLongTermMemoryOut(BaseModel):
    id: int
    memory_type: str
    scope: str
    content: str
    summary: str | None = None
    importance: float
    confidence: float
    related_target_id: int | None = None
    source_session_id: int | None = None
    source_run_id: int | None = None
    tags: list[str] = Field(default_factory=list)
    status: str
    created_at: datetime
    updated_at: datetime


class AdminConversationDetailOut(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[AdminConversationMessageOut]
    runs: list[AdminConversationRunOut]
    pdf_resources: list[AdminConversationPdfOut]
    runtime_link: dict[str, Any] = Field(default_factory=dict)
    runtime_snapshots: list[AdminConversationRuntimeSnapshotOut] = Field(default_factory=list)
    long_term_memory_records: list[AdminConversationLongTermMemoryOut] = Field(default_factory=list)
    short_term_memory: dict[str, Any] = Field(default_factory=dict)


class AdminPdfListItemOut(BaseModel):
    id: int
    filename: str
    status: str
    summary_available: bool
    extracted_text_length: int
    chunk_count: int
    referenced_session_count: int
    created_at: datetime
    updated_at: datetime


class AdminPdfListOut(BaseModel):
    items: list[AdminPdfListItemOut]
    count: int


class AdminPdfReferenceOut(BaseModel):
    session_id: int
    session_title: str
    source_type: str
    source_url: str | None = None
    attached_at: datetime


class AdminPdfDetailOut(BaseModel):
    id: int
    filename: str
    status: str
    storage_path: str
    storage_exists: bool
    summary_markdown: str | None = None
    extracted_text_preview: str | None = None
    extracted_text_length: int
    chunk_count: int
    referenced_sessions: list[AdminPdfReferenceOut]
    created_at: datetime
    updated_at: datetime


class AdminPdfChunkOut(BaseModel):
    id: int
    page_number: int
    content_preview: str
    content_length: int


class AdminPdfChunksOut(BaseModel):
    pdf_id: int
    chunks: list[AdminPdfChunkOut]
    count: int


class AdminPdfReprocessRequest(BaseModel):
    focus: str | None = None


class AdminProviderListItemOut(BaseModel):
    id: int
    provider: str
    base_url: str | None = None
    model: str | None = None
    is_active: bool
    api_key_preview: str
    created_at: datetime
    updated_at: datetime


class AdminProviderListOut(BaseModel):
    items: list[AdminProviderListItemOut]
    count: int


class AdminProviderDetailOut(AdminProviderListItemOut):
    pass


class AdminStudyTargetListItemOut(BaseModel):
    id: int
    school_id: str
    program_id: str | None = None
    label: str
    has_notes: bool
    created_at: datetime


class AdminStudyTargetListOut(BaseModel):
    items: list[AdminStudyTargetListItemOut]
    count: int


class AdminStudyTargetDetailOut(BaseModel):
    id: int
    school_id: str
    program_id: str | None = None
    label: str
    notes: str | None = None
    created_at: datetime


AdminConversationRunOut.model_rebuild()
