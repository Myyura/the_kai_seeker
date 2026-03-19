"""Chat orchestration service for The Kai Seeker (解を求める者).

This file is part of The Kai Seeker, licensed under AGPL-3.0.
Source: https://github.com/Myyura/the_kai_seeker
"""

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.providers.base import ChatMessage
from app.providers.factory import create_provider
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.provider_repo import ProviderRepository
from app.schemas.chat import ChatMessageIn
from app.services.agent import build_system_prompt, run_agent_loop
from app.services.request_context import set_active_pdf_ids

logger = logging.getLogger(__name__)

MAX_TITLE_LENGTH = 60


class ChatService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.provider_repo = ProviderRepository(session)
        self.conversation_repo = ConversationRepository(session)

    async def _get_provider(self):
        setting = await self.provider_repo.get_active()
        if setting is None:
            raise ValueError("No active LLM provider configured. Please add one in Settings.")
        return create_provider(setting)

    def _build_messages(self, user_messages: list[ChatMessageIn], pdf_ids: list[int] | None = None) -> list[ChatMessage]:
        last_user_text = user_messages[-1].content if user_messages else ""
        system_prompt = build_system_prompt(user_message=last_user_text)
        if pdf_ids:
            system_prompt += (
                "\n\n## Active Uploaded PDFs\n"
                f"Use these pdf_ids when calling PDF tools: {pdf_ids}. "
                "If the user asks about the uploaded document and does not specify one, use the first id."
            )
        messages = [ChatMessage(role="system", content=system_prompt)]
        for m in user_messages:
            messages.append(ChatMessage(role=m.role, content=m.content))
        return messages

    async def _ensure_session(self, session_id: int | None, first_message: str) -> int:
        if session_id is not None:
            existing = await self.conversation_repo.get_session(session_id)
            if existing is not None:
                return existing.id

        title = first_message[:MAX_TITLE_LENGTH].strip()
        if len(first_message) > MAX_TITLE_LENGTH:
            title += "…"
        chat_session = await self.conversation_repo.create_session(title=title)
        return chat_session.id

    async def _attach_initial_pdf_ids(self, session_id: int, pdf_ids: list[int] | None) -> None:
        for pid in pdf_ids or []:
            await self.conversation_repo.attach_pdf_resource(
                session_id,
                pid,
                source_type="uploaded",
            )

    async def _attach_fetched_pdfs_from_log(self, session_id: int, tool_call_log: list[dict]) -> None:
        for log in tool_call_log:
            if log.get("tool") != "fetch_pdf_and_upload":
                continue
            fetched = self._parse_fetch_pdf_tool_result(log.get("result", ""))
            if not fetched:
                continue
            await self.conversation_repo.attach_pdf_resource(
                session_id,
                fetched["pdf_id"],
                source_type="fetched",
                source_url=fetched.get("source_url"),
            )

    async def chat(
        self,
        user_messages: list[ChatMessageIn],
        session_id: int | None = None,
        pdf_ids: list[int] | None = None,
    ) -> tuple[str, str | None, int, list[dict]]:
        """Returns (content, model_name, session_id, tool_call_log)."""
        sid = await self._ensure_session(
            session_id, user_messages[-1].content if user_messages else "New Chat"
        )

        last_user_msg = user_messages[-1] if user_messages else None
        if last_user_msg:
            await self.conversation_repo.add_message(sid, last_user_msg.role, last_user_msg.content)

        await self._attach_initial_pdf_ids(sid, pdf_ids)

        provider = await self._get_provider()
        messages = self._build_messages(user_messages, pdf_ids=pdf_ids)
        run = await self.conversation_repo.create_run(sid, status="running")

        with set_active_pdf_ids(pdf_ids or []):
            final_answer, tool_call_log = await run_agent_loop(provider, messages)

        await self._attach_fetched_pdfs_from_log(sid, tool_call_log)
        assistant_message = await self.conversation_repo.add_message(sid, "assistant", final_answer)
        await self.conversation_repo.update_run(
            run.id,
            status="completed",
            assistant_message_id=assistant_message.id,
        )
        await self._persist_tool_log(run.id, tool_call_log, assistant_message.id)

        return final_answer, provider.model, sid, tool_call_log

    async def chat_stream(
        self,
        user_messages: list[ChatMessageIn],
        session_id: int | None = None,
        pdf_ids: list[int] | None = None,
    ) -> tuple[AsyncIterator[dict], int]:
        """Returns (event_iterator, session_id).

        Each yielded event is a dict, one of:
        - {"tool_call": name, "args": {...}}
        - {"tool_result": name, "result": "..."}
        - {"token": "..."}
        """
        sid = await self._ensure_session(
            session_id, user_messages[-1].content if user_messages else "New Chat"
        )

        last_user_msg = user_messages[-1] if user_messages else None
        if last_user_msg:
            await self.conversation_repo.add_message(sid, last_user_msg.role, last_user_msg.content)

        await self._attach_initial_pdf_ids(sid, pdf_ids)

        provider = await self._get_provider()
        messages = self._build_messages(user_messages, pdf_ids=pdf_ids)
        run = await self.conversation_repo.create_run(sid, status="running")

        async def _generate() -> AsyncIterator[dict]:
            queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
            sequence = 0

            async def emit(event: dict[str, Any], *, persist: bool = True) -> None:
                nonlocal sequence
                sequence += 1
                payload = {"sequence": sequence, **event}
                if persist:
                    await self.conversation_repo.add_run_event(
                        run.id,
                        sequence=sequence,
                        event_type=event["type"],
                        payload=payload,
                    )
                await queue.put(payload)

            async def on_agent_event(event: dict[str, Any]) -> None:
                payload = dict(event)
                if payload.get("type") == "tool.finished":
                    raw_result = payload.get("result")
                    if isinstance(raw_result, str):
                        if payload.get("success") is False:
                            payload["error_message"] = self._extract_error_message(raw_result)
                        payload.pop("result", None)
                        fetched = None
                        if payload.get("tool_name") == "fetch_pdf_and_upload":
                            fetched = self._parse_fetch_pdf_tool_result(raw_result)
                        if fetched:
                            payload["resource"] = fetched
                await emit(payload)

            async def produce() -> None:
                try:
                    await emit({"type": "run.started", "run_id": run.id, "status": "running"})
                    await emit({
                        "type": "status",
                        "status": "thinking",
                        "label": "Thinking",
                        "detail": "Planning the next step",
                    })

                    with set_active_pdf_ids(pdf_ids or []):
                        final_answer, tool_call_log = await run_agent_loop(
                            provider, messages, on_event=on_agent_event
                        )

                    await self._attach_fetched_pdfs_from_log(sid, tool_call_log)

                    assistant_message = await self.conversation_repo.add_message(
                        sid, "assistant", final_answer
                    )
                    await self.conversation_repo.update_run(
                        run.id,
                        status="completed",
                        assistant_message_id=assistant_message.id,
                    )

                    await emit({
                        "type": "status",
                        "status": "answering",
                        "label": "Answering",
                        "detail": "Composing the final answer",
                    })
                    for chunk in _chunk_text(final_answer, 20):
                        await emit({"type": "answer.delta", "delta": chunk}, persist=False)
                    await emit(
                        {
                            "type": "answer.completed",
                            "assistant_message_id": assistant_message.id,
                            "content": final_answer,
                        },
                        persist=False,
                    )
                    await emit(
                        {
                            "type": "run.completed",
                            "run_id": run.id,
                            "assistant_message_id": assistant_message.id,
                            "status": "completed",
                        }
                    )
                except ValueError as e:
                    await self.conversation_repo.update_run(run.id, status="failed")
                    await emit(
                        {
                            "type": "error",
                            "message": str(e),
                            "run_id": run.id,
                        }
                    )
                except Exception:
                    logger.exception("Streaming run failed")
                    await self.conversation_repo.update_run(run.id, status="failed")
                    await emit(
                        {
                            "type": "error",
                            "message": "LLM provider request failed",
                            "run_id": run.id,
                        }
                    )
                finally:
                    await queue.put(None)

            producer = asyncio.create_task(produce())
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
            await producer

        return _generate(), sid

    @staticmethod
    def _parse_fetch_pdf_tool_result(result: str) -> dict | None:
        try:
            payload = json.loads(result)
        except Exception:
            return None

        if not isinstance(payload, dict):
            return None

        pdf_id = payload.get("pdf_id")
        if not isinstance(pdf_id, int):
            return None
        source_url = payload.get("source_url")
        filename = payload.get("filename")
        status = payload.get("status")
        return {
            "pdf_id": pdf_id,
            "source_url": source_url,
            "filename": filename,
            "status": status,
        }

    @staticmethod
    def _trim_tool_result(result: str, limit: int = 500) -> str:
        if len(result) <= limit:
            return result
        return result[:limit] + "…"

    @staticmethod
    def _extract_error_message(result: str) -> str:
        text = result.strip()
        if text.startswith("Error:"):
            text = text[len("Error:"):].strip()
        return text

    async def _persist_tool_log(
        self,
        run_id: int,
        tool_call_log: list[dict],
        assistant_message_id: int | None = None,
    ) -> None:
        sequence = 0

        async def add(event_type: str, payload: dict[str, Any]) -> None:
            nonlocal sequence
            sequence += 1
            await self.conversation_repo.add_run_event(
                run_id,
                sequence=sequence,
                event_type=event_type,
                payload={"sequence": sequence, "type": event_type, **payload},
            )

        await add("run.started", {"run_id": run_id, "status": "running"})
        await add(
            "status",
            {
                "status": "thinking",
                "label": "Thinking",
                "detail": "Planning the next step",
            },
        )

        for log in tool_call_log:
            await add(
                "tool.started",
                {
                    "tool_call_id": log.get("tool_call_id"),
                    "tool_name": log.get("tool"),
                    "tool_display_name": log.get("tool_display_name"),
                    "tool_activity_label": log.get("tool_activity_label"),
                    "args": log.get("args", {}),
                },
            )
            tool_finished_payload = {
                "tool_call_id": log.get("tool_call_id"),
                "tool_name": log.get("tool"),
                "tool_display_name": log.get("tool_display_name"),
                "tool_activity_label": log.get("tool_activity_label"),
                "args": log.get("args", {}),
                "success": log.get("success", True),
            }
            if log.get("success") is False:
                tool_finished_payload["error_message"] = self._extract_error_message(
                    log.get("result", "")
                )
            fetched = None
            if log.get("tool") == "fetch_pdf_and_upload":
                fetched = self._parse_fetch_pdf_tool_result(log.get("result", ""))
            if fetched:
                tool_finished_payload["resource"] = fetched
            await add("tool.finished", tool_finished_payload)

        await add(
            "run.completed",
            {
                "run_id": run_id,
                "assistant_message_id": assistant_message_id,
                "status": "completed",
            },
        )


def _chunk_text(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]
