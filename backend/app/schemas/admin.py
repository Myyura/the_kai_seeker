from datetime import datetime

from pydantic import BaseModel


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


class AdminConversationRunOut(BaseModel):
    id: int
    assistant_message_id: int | None = None
    status: str
    event_count: int
    latest_event_type: str | None = None
    created_at: datetime
    updated_at: datetime


class AdminConversationPdfOut(BaseModel):
    pdf_id: int
    filename: str
    status: str
    source: str
    source_url: str | None = None


class AdminConversationDetailOut(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[AdminConversationMessageOut]
    runs: list[AdminConversationRunOut]
    pdf_resources: list[AdminConversationPdfOut]


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
