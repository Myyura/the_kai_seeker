"""Chat orchestration service for The Kai Seeker (解を求める者).

This file is part of The Kai Seeker, licensed under AGPL-3.0.
Source: https://github.com/Myyura/the_kai_seeker
"""

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import ChatMessage
from app.providers.base import ProviderMessage
from app.providers.factory import create_provider
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.provider_repo import ProviderRepository
from app.schemas.chat import ChatMessageIn
from app.services.agent import build_prompt_context, run_agent_loop
from app.services.domain_config import domain_config
from app.services.request_context import set_active_pdf_ids
from app.services.session_state_service import SessionStateService

logger = logging.getLogger(__name__)

MAX_TITLE_LENGTH = 60
TOOL_RESULT_PREVIEW_LIMIT = 4000


class ChatService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.provider_repo = ProviderRepository(session)
        self.conversation_repo = ConversationRepository(session)
        self.session_state_service = SessionStateService()

    async def _get_provider(self):
        setting = await self.provider_repo.get_active()
        if setting is None:
            raise ValueError("No active LLM provider configured. Please add one in Settings.")
        return create_provider(setting)

    @staticmethod
    def _validate_request_messages(user_messages: list[ChatMessageIn]) -> None:
        if not user_messages:
            raise ValueError("At least one message is required.")

        allowed_roles = {"user", "assistant"}
        invalid_roles = {
            message.role for message in user_messages if message.role not in allowed_roles
        }
        if invalid_roles:
            invalid = ", ".join(sorted(invalid_roles))
            raise ValueError(f"Unsupported chat roles: {invalid}.")

        if user_messages[-1].role != "user":
            raise ValueError("The last incoming message must be from the user.")

    def _build_messages(
        self,
        stored_messages: list[ChatMessage],
        runs: list[Any],
        session_state: dict[str, Any],
        current_user_message_id: int,
        current_user_text: str,
        system_prompt: str,
        pdf_ids: list[int] | None = None,
    ) -> list[ProviderMessage]:
        if pdf_ids:
            system_prompt += (
                "\n\n## Active Uploaded PDFs\n"
                f"Use these pdf_ids when calling PDF tools: {pdf_ids}. "
                "If the user asks about the uploaded document and does not "
                "specify one, use the first id."
            )
        session_state_prompt = self.session_state_service.render_prompt_block(session_state)

        recent_messages = [
            message for message in stored_messages if message.id != current_user_message_id
        ]
        recent_window = domain_config.recent_message_window
        if recent_window > 0:
            recent_messages = recent_messages[-recent_window:]
        else:
            recent_messages = []

        messages = [
            ProviderMessage(role="system", content=system_prompt),
            ProviderMessage(role="system", content=session_state_prompt),
        ]
        messages.extend(
            ProviderMessage(role=message.role, content=message.content)
            for message in recent_messages
        )
        messages.append(
            ProviderMessage(role="assistant", content=self._build_tool_results_context(runs))
        )
        messages.append(ProviderMessage(role="user", content=current_user_text))
        return messages

    async def _ensure_session(self, session_id: int | None, first_message: str) -> tuple[int, bool]:
        if session_id is not None:
            if await self.conversation_repo.session_exists(session_id):
                return session_id, False

        title = first_message[:MAX_TITLE_LENGTH].strip()
        if len(first_message) > MAX_TITLE_LENGTH:
            title += "…"
        chat_session = await self.conversation_repo.create_session(title=title)
        return chat_session.id, True

    async def _persist_incoming_messages(
        self,
        session_id: int,
        user_messages: list[ChatMessageIn],
        *,
        session_created: bool,
    ) -> list[ChatMessage]:
        messages_to_store = user_messages if session_created else [user_messages[-1]]
        return await self.conversation_repo.add_messages_bulk(
            session_id,
            [{"role": message.role, "content": message.content} for message in messages_to_store],
            commit=False,
        )

    async def _attach_initial_pdf_ids(self, session_id: int, pdf_ids: list[int] | None) -> None:
        await self.conversation_repo.attach_pdf_resources_bulk(
            session_id,
            [
                {
                    "pdf_id": pid,
                    "source_type": "uploaded",
                }
                for pid in (pdf_ids or [])
            ],
            commit=False,
        )

    async def _attach_fetched_pdfs_from_log(
        self,
        session_id: int,
        tool_call_log: list[dict],
    ) -> None:
        resources: list[dict[str, Any]] = []
        for log in tool_call_log:
            if log.get("tool") != "fetch_pdf_and_upload":
                continue
            fetched = self._parse_fetch_pdf_tool_result(log.get("result", ""))
            if not fetched:
                continue
            resources.append(
                {
                    "pdf_id": fetched["pdf_id"],
                    "source_type": "fetched",
                    "source_url": fetched.get("source_url"),
                }
            )
        await self.conversation_repo.attach_pdf_resources_bulk(
            session_id,
            resources,
            commit=False,
        )

    async def chat(
        self,
        user_messages: list[ChatMessageIn],
        session_id: int | None = None,
        pdf_ids: list[int] | None = None,
    ) -> tuple[str, str | None, int, list[dict]]:
        """Returns (content, model_name, session_id, tool_call_log)."""
        self._validate_request_messages(user_messages)
        sid, session_created = await self._ensure_session(
            session_id, user_messages[-1].content if user_messages else "New Chat"
        )

        persisted_messages = await self._persist_incoming_messages(
            sid,
            user_messages,
            session_created=session_created,
        )
        await self._attach_initial_pdf_ids(sid, pdf_ids)

        provider = await self._get_provider()
        chat_session = await self.conversation_repo.get_session(sid)
        if chat_session is None:
            raise ValueError(f"Session not found: {sid}")
        current_user_message = persisted_messages[-1]
        system_prompt, allowed_tool_names = build_prompt_context(
            user_message=current_user_message.content
        )
        session_state = await self._load_or_rebuild_session_state(
            chat_session,
            current_user_message_id=current_user_message.id,
            current_user_text=current_user_message.content,
            commit=False,
        )
        messages = self._build_messages(
            chat_session.messages,
            chat_session.runs,
            session_state,
            current_user_message.id,
            current_user_message.content,
            system_prompt,
            pdf_ids=pdf_ids,
        )
        run = await self.conversation_repo.create_run(sid, status="running", commit=False)
        await self.session.commit()

        try:
            with set_active_pdf_ids(pdf_ids or []):
                final_answer, tool_call_log = await run_agent_loop(
                    provider,
                    messages,
                    allowed_tool_names=allowed_tool_names,
                )
        except Exception as exc:
            await self.conversation_repo.update_run(run.id, status="failed", commit=False)
            failed_state = self.session_state_service.record_failure(
                session_state,
                user_request=current_user_message.content,
                error_message=str(exc),
            )
            await self.conversation_repo.update_session_state(
                sid,
                self.session_state_service.dump(failed_state),
                commit=False,
            )
            await self.session.commit()
            raise

        await self._attach_fetched_pdfs_from_log(sid, tool_call_log)
        assistant_message = await self.conversation_repo.add_message(
            sid,
            "assistant",
            final_answer,
            commit=False,
        )
        await self.conversation_repo.update_run(
            run.id,
            status="completed",
            assistant_message_id=assistant_message.id,
            commit=False,
        )
        await self._persist_tool_log(
            run.id,
            tool_call_log,
            assistant_message.id,
            commit=False,
        )
        updated_state = self.session_state_service.record_turn_outcome(
            session_state,
            user_request=current_user_message.content,
            assistant_message=final_answer,
            tool_entries=tool_call_log,
            status="completed",
        )
        await self.conversation_repo.update_session_state(
            sid,
            self.session_state_service.dump(updated_state),
            commit=False,
        )
        await self.session.commit()

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
        self._validate_request_messages(user_messages)
        sid, session_created = await self._ensure_session(
            session_id, user_messages[-1].content if user_messages else "New Chat"
        )

        persisted_messages = await self._persist_incoming_messages(
            sid,
            user_messages,
            session_created=session_created,
        )
        await self._attach_initial_pdf_ids(sid, pdf_ids)

        provider = await self._get_provider()
        chat_session = await self.conversation_repo.get_session(sid)
        if chat_session is None:
            raise ValueError(f"Session not found: {sid}")
        current_user_message = persisted_messages[-1]
        system_prompt, allowed_tool_names = build_prompt_context(
            user_message=current_user_message.content
        )
        session_state = await self._load_or_rebuild_session_state(
            chat_session,
            current_user_message_id=current_user_message.id,
            current_user_text=current_user_message.content,
            commit=False,
        )
        messages = self._build_messages(
            chat_session.messages,
            chat_session.runs,
            session_state,
            current_user_message.id,
            current_user_message.content,
            system_prompt,
            pdf_ids=pdf_ids,
        )
        run = await self.conversation_repo.create_run(sid, status="running", commit=False)
        await self.session.commit()

        async def _generate() -> AsyncIterator[dict]:
            queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
            sequence = 0
            pending_events: list[dict[str, Any]] = []

            async def emit(
                event: dict[str, Any],
                *,
                persist: bool = True,
                persist_payload: dict[str, Any] | None = None,
            ) -> None:
                nonlocal sequence
                sequence += 1
                payload = {"sequence": sequence, **event}
                if persist:
                    event_for_storage = persist_payload or event
                    pending_events.append(
                        {
                            "sequence": sequence,
                            "event_type": event_for_storage["type"],
                            "payload": {"sequence": sequence, **event_for_storage},
                        }
                    )
                await queue.put(payload)

            async def flush_pending_events(*, commit: bool) -> None:
                nonlocal pending_events
                if not pending_events:
                    return
                await self.conversation_repo.add_run_events_bulk(
                    run.id,
                    pending_events,
                    commit=commit,
                )
                pending_events = []

            async def on_agent_event(event: dict[str, Any]) -> None:
                payload = dict(event)
                persist_payload = dict(event)
                if payload.get("type") == "tool.finished":
                    raw_result = payload.get("result")
                    if isinstance(raw_result, str):
                        persist_payload["tool_result"] = raw_result
                        persist_payload["tool_result_preview"] = self._trim_tool_result(
                            raw_result,
                            limit=TOOL_RESULT_PREVIEW_LIMIT,
                        )
                        if payload.get("success") is False:
                            payload["error_message"] = self._extract_error_message(raw_result)
                        payload.pop("result", None)
                        fetched = None
                        if payload.get("tool_name") == "fetch_pdf_and_upload":
                            fetched = self._parse_fetch_pdf_tool_result(raw_result)
                        if fetched:
                            payload["resource"] = fetched
                            persist_payload["resource"] = fetched
                await emit(payload, persist_payload=persist_payload)
                if persist_payload.get("type") == "tool.finished":
                    await flush_pending_events(commit=True)

            async def produce() -> None:
                try:
                    await emit({"type": "run.started", "run_id": run.id, "status": "running"})
                    await emit(
                        {
                            "type": "status",
                            "status": "thinking",
                            "label": "Thinking",
                            "detail": "Planning the next step",
                        }
                    )

                    with set_active_pdf_ids(pdf_ids or []):
                        final_answer, tool_call_log = await run_agent_loop(
                            provider,
                            messages,
                            allowed_tool_names=allowed_tool_names,
                            on_event=on_agent_event,
                        )

                    await self._attach_fetched_pdfs_from_log(sid, tool_call_log)

                    assistant_message = await self.conversation_repo.add_message(
                        sid,
                        "assistant",
                        final_answer,
                        commit=False,
                    )
                    await self.conversation_repo.update_run(
                        run.id,
                        status="completed",
                        assistant_message_id=assistant_message.id,
                        commit=False,
                    )
                    updated_state = self.session_state_service.record_turn_outcome(
                        session_state,
                        user_request=current_user_message.content,
                        assistant_message=final_answer,
                        tool_entries=tool_call_log,
                        status="completed",
                    )
                    await self.conversation_repo.update_session_state(
                        sid,
                        self.session_state_service.dump(updated_state),
                        commit=False,
                    )

                    await emit(
                        {
                            "type": "status",
                            "status": "answering",
                            "label": "Answering",
                            "detail": "Composing the final answer",
                        }
                    )
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
                    await flush_pending_events(commit=False)
                    await self.session.commit()
                except ValueError as e:
                    await self.conversation_repo.update_run(run.id, status="failed", commit=False)
                    failed_state = self.session_state_service.record_failure(
                        session_state,
                        user_request=current_user_message.content,
                        error_message=str(e),
                    )
                    await self.conversation_repo.update_session_state(
                        sid,
                        self.session_state_service.dump(failed_state),
                        commit=False,
                    )
                    await emit(
                        {
                            "type": "error",
                            "message": str(e),
                            "run_id": run.id,
                        }
                    )
                    await flush_pending_events(commit=False)
                    await self.session.commit()
                except Exception:
                    logger.exception("Streaming run failed")
                    await self.conversation_repo.update_run(run.id, status="failed", commit=False)
                    failed_state = self.session_state_service.record_failure(
                        session_state,
                        user_request=current_user_message.content,
                        error_message="LLM provider request failed",
                    )
                    await self.conversation_repo.update_session_state(
                        sid,
                        self.session_state_service.dump(failed_state),
                        commit=False,
                    )
                    await emit(
                        {
                            "type": "error",
                            "message": "LLM provider request failed",
                            "run_id": run.id,
                        }
                    )
                    await flush_pending_events(commit=False)
                    await self.session.commit()
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
        parsed = {"pdf_id": pdf_id}
        source_url = payload.get("source_url")
        filename = payload.get("filename")
        status = payload.get("status")
        if source_url is not None:
            parsed["source_url"] = source_url
        if filename is not None:
            parsed["filename"] = filename
        if status is not None:
            parsed["status"] = status
        return parsed

    @staticmethod
    def _trim_tool_result(result: str, limit: int = 500) -> str:
        if len(result) <= limit:
            return result
        head = max(1, int(limit * 0.65))
        tail = max(1, limit - head - len("\n...[truncated]...\n"))
        return result[:head] + "\n...[truncated]...\n" + result[-tail:]

    @staticmethod
    def _extract_error_message(result: str) -> str:
        text = result.strip()
        if text.startswith("Error:"):
            text = text[len("Error:") :].strip()
        return text

    async def _persist_tool_log(
        self,
        run_id: int,
        tool_call_log: list[dict],
        assistant_message_id: int | None = None,
        *,
        commit: bool = True,
    ) -> None:
        sequence = 0
        events: list[dict[str, Any]] = []

        def add(event_type: str, payload: dict[str, Any]) -> None:
            nonlocal sequence
            sequence += 1
            events.append(
                {
                    "sequence": sequence,
                    "event_type": event_type,
                    "payload": {"sequence": sequence, "type": event_type, **payload},
                }
            )

        add("run.started", {"run_id": run_id, "status": "running"})
        add(
            "status",
            {
                "status": "thinking",
                "label": "Thinking",
                "detail": "Planning the next step",
            },
        )

        for log in tool_call_log:
            add(
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
            raw_result = log.get("result", "")
            if isinstance(raw_result, str) and raw_result:
                tool_finished_payload["tool_result"] = raw_result
                tool_finished_payload["tool_result_preview"] = self._trim_tool_result(
                    raw_result,
                    limit=TOOL_RESULT_PREVIEW_LIMIT,
                )
            if log.get("success") is False:
                tool_finished_payload["error_message"] = self._extract_error_message(raw_result)
            fetched = None
            if log.get("tool") == "fetch_pdf_and_upload":
                fetched = self._parse_fetch_pdf_tool_result(raw_result)
            if fetched:
                tool_finished_payload["resource"] = fetched
            add("tool.finished", tool_finished_payload)

        add(
            "run.completed",
            {
                "run_id": run_id,
                "assistant_message_id": assistant_message_id,
                "status": "completed",
            },
        )
        await self.conversation_repo.add_run_events_bulk(run_id, events, commit=commit)

    async def _load_or_rebuild_session_state(
        self,
        chat_session: Any,
        *,
        current_user_message_id: int,
        current_user_text: str,
        commit: bool = True,
    ) -> dict[str, Any]:
        state_record = chat_session.state
        if state_record is not None and state_record.payload.strip() not in {"", "{}"}:
            state = self.session_state_service.load(state_record.payload)
        else:
            historical_messages = [
                message for message in chat_session.messages if message.id < current_user_message_id
            ]
            state = self.session_state_service.rebuild_from_history(
                historical_messages,
                chat_session.runs,
            )

        state = self.session_state_service.record_user_turn(state, current_user_text)
        await self.conversation_repo.update_session_state(
            chat_session.id,
            self.session_state_service.dump(state),
            commit=commit,
        )
        return state

    def _build_tool_results_context(self, runs: list[Any]) -> str:
        entries: list[dict[str, Any]] = []
        for run in sorted(
            runs,
            key=lambda item: (
                item.created_at.isoformat() if getattr(item, "created_at", None) else "",
                getattr(item, "id", 0),
            ),
        ):
            entries.extend(self.session_state_service.extract_tool_entries_from_run(run))

        lines = [
            "## Session Tool Results",
            (
                "These are complete results from prior tool executions in the current session. "
                "Reuse them instead of repeating the same lookup, fetch, or PDF processing work "
                "when they already contain the needed URL, content, or identifiers."
            ),
        ]
        if not entries:
            lines.append("No previous tool results are recorded for this session.")
            return "\n\n".join(lines)

        for index, entry in enumerate(entries, start=1):
            lines.append(f"### Tool Result {index}: {entry.get('tool')}")
            lines.append(f"Args: {json.dumps(entry.get('args', {}), ensure_ascii=False)}")
            lines.append(f"Success: {entry.get('success', True)}")
            lines.append("Result:")
            lines.append(entry.get("result") or "(empty)")
        return "\n\n".join(lines)


def _chunk_text(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]
