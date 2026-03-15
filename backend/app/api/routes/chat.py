import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session
from app.repositories.conversation_repo import ConversationRepository
from app.schemas.chat import (
    ChatRequest,
    ChatResponseOut,
    ChatSessionDetail,
    ChatSessionOut,
)
from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/", response_model=ChatResponseOut)
async def send_message(
    req: ChatRequest,
    session: AsyncSession = Depends(get_session),
) -> ChatResponseOut | StreamingResponse:
    service = ChatService(session)

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
        content, model, sid = await service.chat(req.messages, req.session_id, req.pdf_ids)
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
    return ChatSessionDetail.model_validate(chat_session)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    repo = ConversationRepository(session)
    deleted = await repo.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
