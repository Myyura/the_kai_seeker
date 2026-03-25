import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.long_term_memory_repo import LongTermMemoryRepository
from app.repositories.provider_repo import ProviderRepository
from app.repositories.study_target_repo import StudyTargetRepository
from app.schemas.admin import (
    AdminConversationDetailOut,
    AdminConversationListItemOut,
    AdminConversationLongTermMemoryOut,
    AdminConversationListOut,
    AdminConversationMessageOut,
    AdminConversationPdfOut,
    AdminConversationRuntimeSnapshotOut,
    AdminConversationToolArtifactOut,
    AdminConversationToolCallOut,
    AdminConversationRunOut,
    AdminPdfChunksOut,
    AdminPdfDetailOut,
    AdminPdfListItemOut,
    AdminPdfListOut,
    AdminPdfReprocessRequest,
    AdminProviderDetailOut,
    AdminProviderListItemOut,
    AdminProviderListOut,
    AdminResourceOut,
    AdminResourcesOut,
    AdminStudyTargetDetailOut,
    AdminStudyTargetListItemOut,
    AdminStudyTargetListOut,
)
from app.schemas.pdf import PdfProcessOut
from app.services.conversation_service import ConversationService
from app.services.pdf_service import PdfService

router = APIRouter()

ADMIN_RESOURCES = [
    AdminResourceOut(
        id="pdfs",
        label="PDFs",
        description=(
            "Manage uploaded and fetched PDF documents, processing output, "
            "and session references."
        ),
        href="/data/pdfs/",
        available=True,
    ),
    AdminResourceOut(
        id="conversations",
        label="Conversations",
        description="Inspect chat sessions, messages, runs, and tool timelines.",
        href="/data/conversations/",
        available=True,
    ),
    AdminResourceOut(
        id="providers",
        label="Providers",
        description="Review stored provider records and future operational metadata.",
        href="/data/providers/",
        available=True,
    ),
    AdminResourceOut(
        id="study-targets",
        label="Study Targets",
        description="Manage saved study goals and attached notes.",
        href="/data/study-targets/",
        available=True,
    ),
]


def _mask_api_key(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 6:
        return "*" * len(secret)
    return f"{secret[:4]}...{secret[-2:]}"


def _parse_json_payload(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_json_any(raw: str | None):
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _parse_json_list(raw: str | None) -> list:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


@router.get("/resources", response_model=AdminResourcesOut)
async def list_admin_resources() -> AdminResourcesOut:
    return AdminResourcesOut(resources=ADMIN_RESOURCES)


@router.get("/conversations", response_model=AdminConversationListOut)
async def list_admin_conversations(
    query: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> AdminConversationListOut:
    repo = ConversationRepository(session)
    items = await repo.list_sessions_admin(query=query, limit=limit)
    return AdminConversationListOut(
        items=[AdminConversationListItemOut.model_validate(item) for item in items],
        count=len(items),
    )


@router.get("/conversations/{session_id}", response_model=AdminConversationDetailOut)
async def get_admin_conversation_detail(
    session_id: int,
    session: AsyncSession = Depends(get_session),
) -> AdminConversationDetailOut:
    repo = ConversationRepository(session)
    memory_repo = LongTermMemoryRepository(session)
    chat_session = await repo.get_session(session_id)
    if chat_session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    pdf_resources = await repo.list_session_pdf_resources(session_id)
    long_term_memory_records = await memory_repo.list_by_source_session(session_id)
    return AdminConversationDetailOut(
        id=chat_session.id,
        title=chat_session.title,
        created_at=chat_session.created_at,
        updated_at=chat_session.updated_at,
        messages=[
            AdminConversationMessageOut(
                id=message.id,
                role=message.role,
                content=message.content,
                model=message.model,
                created_at=message.created_at,
            )
            for message in chat_session.messages
        ],
        runs=[
            AdminConversationRunOut(
                id=run.id,
                assistant_message_id=run.assistant_message_id,
                status=run.status,
                tool_call_count=len(run.tool_calls),
                artifact_count=sum(len(tool_call.artifacts) for tool_call in run.tool_calls),
                created_at=run.created_at,
                updated_at=run.updated_at,
                tool_calls=[
                    AdminConversationToolCallOut(
                        id=tool_call.id,
                        sequence=tool_call.sequence,
                        call_id=tool_call.call_id,
                        tool_name=tool_call.tool_name,
                        display_name=tool_call.display_name,
                        activity_label=tool_call.activity_label,
                        arguments=_parse_json_payload(tool_call.arguments_json),
                        output=_parse_json_payload(tool_call.output_json),
                        success=tool_call.status != "failed",
                        status=tool_call.status,
                        error_text=tool_call.error_text,
                        started_at=tool_call.started_at,
                        finished_at=tool_call.finished_at,
                        artifacts=[
                            AdminConversationToolArtifactOut(
                                id=artifact.id,
                                kind=artifact.kind,
                                label=artifact.label,
                                summary=artifact.summary,
                                summary_format=artifact.summary_format,
                                locator=_parse_json_payload(artifact.locator_json),
                                replay=_parse_json_payload(artifact.replay_json)
                                if artifact.replay_json
                                else None,
                                is_primary=artifact.is_primary,
                                created_at=artifact.created_at,
                            )
                            for artifact in tool_call.artifacts
                        ],
                        created_at=tool_call.created_at,
                    )
                    for tool_call in run.tool_calls
                ],
                snapshot=(
                    _parse_json_payload(run.runtime_snapshots[-1].snapshot_payload)
                    if run.runtime_snapshots
                    else {}
                ),
            )
            for run in chat_session.runs
        ],
        pdf_resources=[AdminConversationPdfOut.model_validate(item) for item in pdf_resources],
        runtime_link=(
            {
                "runtime_name": chat_session.runtime_link.runtime_name,
                "runtime_session_id": chat_session.runtime_link.runtime_session_id,
                "runtime_conversation_id": chat_session.runtime_link.runtime_conversation_id,
                "base_system_prompt": chat_session.runtime_link.base_system_prompt,
                "status": chat_session.runtime_link.status,
                "metadata": _parse_json_payload(chat_session.runtime_link.metadata_json),
            }
            if chat_session.runtime_link is not None
            else {}
        ),
        runtime_snapshots=[
            AdminConversationRuntimeSnapshotOut(
                id=snapshot.id,
                created_at=snapshot.created_at,
                payload=_parse_json_any(snapshot.snapshot_payload),
            )
            for snapshot in chat_session.runtime_snapshots
        ],
        long_term_memory_records=[
            AdminConversationLongTermMemoryOut(
                id=record.id,
                memory_type=record.memory_type,
                scope=record.scope,
                content=record.content,
                summary=record.summary,
                importance=record.importance,
                confidence=record.confidence,
                related_target_id=record.related_target_id,
                source_session_id=record.source_session_id,
                source_run_id=record.source_run_id,
                tags=_parse_json_list(record.tags),
                status=record.status,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
            for record in long_term_memory_records
        ],
        short_term_memory=(
            json.loads(chat_session.short_term_memory.payload)
            if chat_session.short_term_memory is not None
            else {}
        ),
    )


@router.delete("/conversations/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_conversation(
    session_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    service = ConversationService(session)
    deleted = await service.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")


@router.get("/pdfs", response_model=AdminPdfListOut)
async def list_admin_pdfs(
    query: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> AdminPdfListOut:
    service = PdfService(session)
    items = await service.list_admin_documents(query=query, status=status_filter, limit=limit)
    return AdminPdfListOut(
        items=[AdminPdfListItemOut.model_validate(item) for item in items],
        count=len(items),
    )


@router.get("/pdfs/{pdf_id}", response_model=AdminPdfDetailOut)
async def get_admin_pdf_detail(
    pdf_id: int,
    session: AsyncSession = Depends(get_session),
) -> AdminPdfDetailOut:
    service = PdfService(session)
    try:
        detail = await service.get_admin_document_detail(pdf_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return AdminPdfDetailOut.model_validate(detail)


@router.get("/pdfs/{pdf_id}/chunks", response_model=AdminPdfChunksOut)
async def list_admin_pdf_chunks(
    pdf_id: int,
    limit: int = Query(default=40, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> AdminPdfChunksOut:
    service = PdfService(session)
    try:
        chunks = await service.get_admin_document_chunks(pdf_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return AdminPdfChunksOut.model_validate(chunks)


@router.delete("/pdfs/{pdf_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_pdf(
    pdf_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    service = PdfService(session)
    try:
        await service.delete_document(pdf_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/pdfs/{pdf_id}/reprocess", response_model=PdfProcessOut)
async def reprocess_admin_pdf(
    pdf_id: int,
    req: AdminPdfReprocessRequest,
    session: AsyncSession = Depends(get_session),
) -> PdfProcessOut:
    service = PdfService(session)
    try:
        result = await service.process_and_summarize(pdf_id, req.focus)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return PdfProcessOut.model_validate(result)


@router.get("/providers", response_model=AdminProviderListOut)
async def list_admin_providers(
    query: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> AdminProviderListOut:
    repo = ProviderRepository(session)
    providers = await repo.list_admin(query=query, limit=limit)
    items = [
        AdminProviderListItemOut(
            id=provider.id,
            provider=provider.provider,
            base_url=provider.base_url,
            model=provider.model,
            is_active=provider.is_active,
            api_key_preview=_mask_api_key(provider.api_key),
            created_at=provider.created_at,
            updated_at=provider.updated_at,
        )
        for provider in providers
    ]
    return AdminProviderListOut(items=items, count=len(items))


@router.get("/providers/{provider_id}", response_model=AdminProviderDetailOut)
async def get_admin_provider_detail(
    provider_id: int,
    session: AsyncSession = Depends(get_session),
) -> AdminProviderDetailOut:
    repo = ProviderRepository(session)
    provider = await repo.get_by_id(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    return AdminProviderDetailOut(
        id=provider.id,
        provider=provider.provider,
        base_url=provider.base_url,
        model=provider.model,
        is_active=provider.is_active,
        api_key_preview=_mask_api_key(provider.api_key),
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


@router.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_provider(
    provider_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    repo = ProviderRepository(session)
    deleted = await repo.delete(provider_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Provider not found")


@router.get("/study-targets", response_model=AdminStudyTargetListOut)
async def list_admin_study_targets(
    query: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> AdminStudyTargetListOut:
    repo = StudyTargetRepository(session)
    targets = await repo.list_all(query=query, limit=limit)
    items = [
        AdminStudyTargetListItemOut(
            id=target.id,
            school_id=target.school_id,
            program_id=target.program_id,
            label=target.label,
            has_notes=bool((target.notes or "").strip()),
            created_at=target.created_at,
        )
        for target in targets
    ]
    return AdminStudyTargetListOut(items=items, count=len(items))


@router.get("/study-targets/{target_id}", response_model=AdminStudyTargetDetailOut)
async def get_admin_study_target_detail(
    target_id: int,
    session: AsyncSession = Depends(get_session),
) -> AdminStudyTargetDetailOut:
    repo = StudyTargetRepository(session)
    target = await repo.get_by_id(target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Study target not found")
    return AdminStudyTargetDetailOut(
        id=target.id,
        school_id=target.school_id,
        program_id=target.program_id,
        label=target.label,
        notes=target.notes,
        created_at=target.created_at,
    )


@router.delete("/study-targets/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_study_target(
    target_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    repo = StudyTargetRepository(session)
    deleted = await repo.delete(target_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Study target not found")
