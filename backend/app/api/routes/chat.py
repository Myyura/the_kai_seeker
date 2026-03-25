import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session
from app.repositories.conversation_repo import ConversationRepository
from app.schemas.chat import (
    ChatMessageOut,
    ChatRequest,
    ChatResponseOut,
    ChatToolArtifactOut,
    ChatToolCallOut,
    ChatRunOut,
    ChatSessionDetail,
    ChatSessionOut,
    ChatSessionPdfResourceOut,
)
from app.services.conversation_service import ConversationService

logger = logging.getLogger(__name__)

router = APIRouter()


def _loads_json(raw: str | None, fallback):
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


@router.post("/", response_model=ChatResponseOut)
async def send_message(
    req: ChatRequest,
    session: AsyncSession = Depends(get_session),
) -> ChatResponseOut | StreamingResponse:
    service = ConversationService(session)

    if req.stream:
        try:
            token_iter, sid = await service.chat_stream(req.messages, req.session_id, req.pdf_ids)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        return StreamingResponse(
            _stream_response(token_iter, sid),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    try:
        content, model, sid, _ = await service.chat(req.messages, req.session_id, req.pdf_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Chat error")
        raise HTTPException(status_code=502, detail="LLM provider request failed")

    return ChatResponseOut(session_id=sid, content=content, model=model)


async def _stream_response(event_iter, session_id: int):
    try:
        meta = json.dumps({"session_id": session_id})
        yield f"data: {meta}\n\n"
        async for event in event_iter:
            data = json.dumps(event, ensure_ascii=False)
            yield f"data: {data}\n\n"
        yield "data: [DONE]\n\n"
    except ValueError as e:
        error = json.dumps({"error": str(e)}, ensure_ascii=False)
        yield f"data: {error}\n\n"
    except Exception:
        logger.exception("Stream error")
        error = json.dumps({"error": "LLM provider request failed"})
        yield f"data: {error}\n\n"


# --- Conversation history endpoints ---


@router.get("/sessions", response_model=list[ChatSessionOut])
async def list_sessions(
    session: AsyncSession = Depends(get_session),
) -> list[ChatSessionOut]:
    repo = ConversationRepository(session)
    sessions = await repo.list_sessions()
    return [ChatSessionOut.model_validate(s) for s in sessions]


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
async def get_session_detail(
    session_id: int,
    session: AsyncSession = Depends(get_session),
) -> ChatSessionDetail:
    repo = ConversationRepository(session)
    chat_session = await repo.get_session(session_id)
    if chat_session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return ChatSessionDetail(
        id=chat_session.id,
        title=chat_session.title,
        created_at=chat_session.created_at,
        updated_at=chat_session.updated_at,
        messages=[ChatMessageOut.model_validate(message) for message in chat_session.messages],
        runs=[
            ChatRunOut(
                id=run.id,
                assistant_message_id=run.assistant_message_id,
                status=run.status,
                created_at=run.created_at,
                updated_at=run.updated_at,
                tool_calls=[
                    ChatToolCallOut(
                        id=tool_call.id,
                        sequence=tool_call.sequence,
                        call_id=tool_call.call_id,
                        tool_name=tool_call.tool_name,
                        display_name=tool_call.display_name,
                        activity_label=tool_call.activity_label,
                        arguments=_loads_json(tool_call.arguments_json, {}),
                        output=_loads_json(tool_call.output_json, {}),
                        success=tool_call.status != "failed",
                        status=tool_call.status,
                        error_text=tool_call.error_text,
                        started_at=tool_call.started_at,
                        finished_at=tool_call.finished_at,
                        artifacts=[
                            ChatToolArtifactOut(
                                id=artifact.id,
                                kind=artifact.kind,
                                label=artifact.label,
                                summary=artifact.summary,
                                summary_format=artifact.summary_format,
                                locator=_loads_json(artifact.locator_json, {}),
                                replay=_loads_json(artifact.replay_json, {})
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
            )
            for run in chat_session.runs
        ],
        short_term_memory=(
            json.loads(chat_session.short_term_memory.payload)
            if chat_session.short_term_memory is not None
            else {}
        ),
    )


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    service = ConversationService(session)
    deleted = await service.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")


@router.get("/sessions/{session_id}/pdfs", response_model=list[ChatSessionPdfResourceOut])
async def get_session_pdfs(
    session_id: int,
    session: AsyncSession = Depends(get_session),
) -> list[ChatSessionPdfResourceOut]:
    repo = ConversationRepository(session)
    chat_session = await repo.get_session(session_id)
    if chat_session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    resources = await repo.list_session_pdf_resources(session_id)
    return [ChatSessionPdfResourceOut.model_validate(r) for r in resources]
