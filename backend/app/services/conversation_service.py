"""Conversation service backed by the AgentRuntime abstraction."""

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.base_system_prompt import build_base_system_prompt
from app.agent_runtime.native import NativeAgentRuntime
from app.agent_runtime.native_loop import run_native_agent_loop
from app.agent_runtime.skill_bridge import SkillBridge
from app.agent_runtime.tool_bridge import ToolBridge
from app.agent_runtime.types import (
    AgentRuntimeLink,
    AgentRuntimeSetup,
    AgentTurnInput,
    HostContextState,
    ResourceHandle,
    TurnMessage,
)
from app.providers.factory import create_provider
from app.repositories.agent_runtime_repo import AgentRuntimeRepository
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.provider_repo import ProviderRepository
from app.schemas.chat import ChatMessageIn
from app.services.long_term_memory_service import LongTermMemoryService
from app.services.session_lock_service import session_lock_service
from app.skills.registry import skill_registry

logger = logging.getLogger(__name__)

MAX_TITLE_LENGTH = 60
TOOL_RESULT_PREVIEW_LIMIT = 4000
RUN_DEBUG_PAYLOAD_VERSION = 1


class ConversationService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        base_system_prompt_builder: Callable[[], str] = build_base_system_prompt,
        tool_loop_runner: Callable[..., Awaitable[tuple[str, list[dict[str, Any]]]]] = run_native_agent_loop,
    ):
        self.session = session
        self.provider_repo = ProviderRepository(session)
        self.conversation_repo = ConversationRepository(session)
        self.agent_runtime_repo = AgentRuntimeRepository(session)
        self.long_term_memory_service = LongTermMemoryService(session)
        self.tool_bridge = ToolBridge()
        self.skill_bridge = SkillBridge()
        self.base_system_prompt_builder = base_system_prompt_builder
        self.tool_loop_runner = tool_loop_runner

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

    async def _ensure_session(self, session_id: int | None, first_message: str) -> tuple[int, bool]:
        if session_id is not None and await self.conversation_repo.session_exists(session_id):
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
    ) -> list[Any]:
        messages_to_store = user_messages if session_created else [user_messages[-1]]
        return await self.conversation_repo.add_messages_bulk(
            session_id,
            [{"role": message.role, "content": message.content} for message in messages_to_store],
            commit=False,
        )

    async def _get_or_open_runtime_link(
        self,
        *,
        session_id: int,
        provider_model: str | None,
        provider: Any | None = None,
    ) -> AgentRuntimeLink:
        existing = await self.agent_runtime_repo.get_link_by_session_id(session_id)
        if existing is not None:
            return self.agent_runtime_repo.to_data(existing)

        setup = AgentRuntimeSetup(
            base_system_prompt=self.base_system_prompt_builder(),
            model_name=provider_model,
            metadata={"chat_session_id": session_id},
        )
        runtime = NativeAgentRuntime(
            provider=provider or await self._get_provider(),
            stored_messages=[],
            stored_runs=[],
            initial_short_term_memory_payload="{}",
            tool_loop_runner=self.tool_loop_runner,
            tool_bridge=self.tool_bridge,
        )
        link = await runtime.open_session(None, setup)
        saved = await self.agent_runtime_repo.save_link(session_id, link, commit=False)
        return self.agent_runtime_repo.to_data(saved)

    def _build_session_resource_handles(self, chat_session: Any) -> list[ResourceHandle]:
        handles: list[ResourceHandle] = []
        for resource in getattr(chat_session, "pdf_resources", []):
            metadata = {}
            if resource.source_url:
                metadata["source_url"] = resource.source_url
            handles.append(
                ResourceHandle(
                    resource_type="pdf",
                    resource_id=str(resource.pdf_id),
                    label=f"pdf:{resource.pdf_id}",
                    source=resource.source_type,
                    metadata=metadata,
                )
            )
        return handles

    @staticmethod
    def _build_transient_resource_handles(pdf_ids: list[int] | None) -> list[ResourceHandle]:
        return [
            ResourceHandle(
                resource_type="pdf",
                resource_id=str(pdf_id),
                label=f"pdf:{pdf_id}",
                source="request",
            )
            for pdf_id in (pdf_ids or [])
        ]

    async def _build_host_context_state(
        self,
        *,
        current_user_text: str,
        chat_session: Any,
    ) -> HostContextState:
        memory_pack = await self.long_term_memory_service.build_memory_pack(
            session_id=chat_session.id,
        )
        active_skills = skill_registry.get_active_skills(current_user_text)
        skill_definitions = self.skill_bridge.build_definitions(active_skills)
        tool_definitions = self.tool_bridge.build_definitions()
        return HostContextState.build(
            memory_pack=memory_pack,
            tool_definitions=tool_definitions,
            skill_definitions=skill_definitions,
            session_resource_handles=self._build_session_resource_handles(chat_session),
        )

    def _create_native_runtime(
        self,
        *,
        provider: Any,
        chat_session: Any,
    ) -> NativeAgentRuntime:
        return NativeAgentRuntime(
            provider=provider,
            stored_messages=chat_session.messages,
            stored_runs=chat_session.runs,
            initial_short_term_memory_payload=(
                chat_session.short_term_memory.payload
                if chat_session.short_term_memory is not None
                else "{}"
            ),
            tool_loop_runner=self.tool_loop_runner,
            tool_bridge=self.tool_bridge,
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
        tool_call_log: list[dict[str, Any]],
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
        await self.conversation_repo.attach_pdf_resources_bulk(session_id, resources, commit=False)

    async def _persist_runtime_state(
        self,
        *,
        session_id: int,
        runtime: NativeAgentRuntime,
        runtime_link: AgentRuntimeLink,
        commit: bool = False,
    ) -> dict[str, Any] | None:
        await self.conversation_repo.update_short_term_memory(
            session_id,
            runtime.dump_short_term_memory(),
            commit=False,
        )
        snapshot = await runtime.get_snapshot(runtime_link)
        if snapshot is not None:
            await self.agent_runtime_repo.save_snapshot(session_id, snapshot, commit=commit)
            return snapshot.model_dump(mode="json")
        elif commit:
            await self.session.commit()
        return None

    async def _write_long_term_memory(
        self,
        *,
        session_id: int,
        run_id: int,
        user_request: str,
        assistant_message: str,
        tool_records: list[dict[str, Any]],
        commit: bool = False,
    ) -> list[dict[str, Any]]:
        created_records: list[dict[str, Any]] = []
        record = await self.long_term_memory_service.write_session_insight(
            session_id=session_id,
            run_id=run_id,
            user_request=user_request,
            assistant_message=assistant_message,
            tool_records=tool_records,
            commit=commit,
        )
        if record is not None:
            created_records.append(self._serialize_long_term_memory_record(record))
        return created_records

    @staticmethod
    def _serialize_runtime_link(runtime_link: AgentRuntimeLink) -> dict[str, Any]:
        return runtime_link.model_dump(mode="json")

    @staticmethod
    def _serialize_long_term_memory_record(record: Any) -> dict[str, Any]:
        return {
            "id": record.id,
            "memory_type": record.memory_type,
            "scope": record.scope,
            "content": record.content,
            "summary": record.summary,
            "importance": record.importance,
            "confidence": record.confidence,
            "related_target_id": record.related_target_id,
            "source_session_id": record.source_session_id,
            "source_run_id": record.source_run_id,
            "tags": json.loads(record.tags) if record.tags else [],
            "status": record.status,
        }

    def _build_run_debug_payload(
        self,
        *,
        provider: Any,
        runtime_link: AgentRuntimeLink,
        context_sync_result: Any,
        host_context_state: HostContextState,
        turn_input: AgentTurnInput,
        runtime_snapshot: dict[str, Any] | None,
        tool_records: list[dict[str, Any]],
        long_term_memory_writes: list[dict[str, Any]],
        assistant_text: str | None,
        status: str,
        assistant_message_id: int | None = None,
        artifacts: dict[str, Any] | None = None,
        usage: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "version": RUN_DEBUG_PAYLOAD_VERSION,
            "provider": {
                "name": provider.__class__.__name__,
                "model": getattr(provider, "model", None),
            },
            "runtime_link": self._serialize_runtime_link(runtime_link),
            "context_sync": context_sync_result.model_dump(mode="json"),
            "host_context_state": host_context_state.model_dump(mode="json"),
            "turn_input": turn_input.model_dump(mode="json"),
            "runtime_snapshot": runtime_snapshot,
            "tool_records": tool_records,
            "long_term_memory_writes": long_term_memory_writes,
            "assistant_text": assistant_text,
            "assistant_message_id": assistant_message_id,
            "artifacts": artifacts or {},
            "usage": usage,
            "status": status,
            "error": error,
        }

    async def _persist_run_debug_payload(
        self,
        *,
        run_id: int,
        payload: dict[str, Any],
        commit: bool = False,
    ) -> None:
        await self.conversation_repo.save_run_debug_payload(run_id, payload, commit=commit)

    async def delete_session(self, session_id: int) -> bool:
        if not await self.conversation_repo.session_exists(session_id):
            return False
        await self.long_term_memory_service.delete_session_records(session_id, commit=False)
        deleted = await self.conversation_repo.delete_session(session_id, commit=False)
        if not deleted:
            await self.session.rollback()
            return False
        await self.session.commit()
        return True

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

        async with session_lock_service.lock(sid):
            persisted_messages = await self._persist_incoming_messages(
                sid,
                user_messages,
                session_created=session_created,
            )
            provider = await self._get_provider()
            runtime_link = await self._get_or_open_runtime_link(
                session_id=sid,
                provider_model=provider.model,
                provider=provider,
            )
            chat_session = await self.conversation_repo.get_session(sid)
            if chat_session is None:
                raise ValueError(f"Session not found: {sid}")

            current_user_message = persisted_messages[-1]
            host_context_state = await self._build_host_context_state(
                current_user_text=current_user_message.content,
                chat_session=chat_session,
            )
            runtime = self._create_native_runtime(provider=provider, chat_session=chat_session)
            context_sync_result = await runtime.sync_host_context(runtime_link, host_context_state)
            turn_input = AgentTurnInput(
                messages=[TurnMessage(role="user", content=current_user_message.content)],
                stream=False,
                transient_resource_handles=self._build_transient_resource_handles(pdf_ids),
                request_metadata={"current_user_message_id": current_user_message.id},
            )
            run = await self.conversation_repo.create_run(sid, status="running", commit=False)
            await self.session.commit()

            try:
                output = await runtime.run_turn(runtime_link, turn_input)
            except Exception as exc:
                await self.conversation_repo.update_run(run.id, status="failed", commit=False)
                runtime_snapshot = await self._persist_runtime_state(
                    session_id=sid,
                    runtime=runtime,
                    runtime_link=runtime_link,
                    commit=False,
                )
                await self._attach_initial_pdf_ids(sid, pdf_ids)
                await self._persist_run_debug_payload(
                    run_id=run.id,
                    payload=self._build_run_debug_payload(
                        provider=provider,
                        runtime_link=runtime_link,
                        context_sync_result=context_sync_result,
                        host_context_state=host_context_state,
                        turn_input=turn_input,
                        runtime_snapshot=runtime_snapshot,
                        tool_records=[],
                        long_term_memory_writes=[],
                        assistant_text=None,
                        status="failed",
                        error={
                            "type": exc.__class__.__name__,
                            "message": str(exc),
                        },
                    ),
                    commit=False,
                )
                await self.session.commit()
                raise

            tool_call_log = [record.model_dump(mode="json") for record in output.tool_records]
            await self._attach_initial_pdf_ids(sid, pdf_ids)
            await self._attach_fetched_pdfs_from_log(sid, tool_call_log)

            assistant_message = await self.conversation_repo.add_message(
                sid,
                "assistant",
                output.assistant_text,
                commit=False,
            )
            await self.conversation_repo.update_run(
                run.id,
                status=output.status,
                assistant_message_id=assistant_message.id,
                commit=False,
            )
            await self._persist_tool_log(
                run.id,
                tool_call_log,
                assistant_message.id,
                commit=False,
            )
            runtime_snapshot = await self._persist_runtime_state(
                session_id=sid,
                runtime=runtime,
                runtime_link=runtime_link,
                commit=False,
            )
            long_term_memory_writes = await self._write_long_term_memory(
                session_id=sid,
                run_id=run.id,
                user_request=current_user_message.content,
                assistant_message=output.assistant_text,
                tool_records=tool_call_log,
                commit=False,
            )
            await self._persist_run_debug_payload(
                run_id=run.id,
                payload=self._build_run_debug_payload(
                    provider=provider,
                    runtime_link=runtime_link,
                    context_sync_result=context_sync_result,
                    host_context_state=host_context_state,
                    turn_input=turn_input,
                    runtime_snapshot=runtime_snapshot,
                    tool_records=tool_call_log,
                    long_term_memory_writes=long_term_memory_writes,
                    assistant_text=output.assistant_text,
                    assistant_message_id=assistant_message.id,
                    artifacts=output.artifacts,
                    usage=output.usage,
                    status=output.status,
                ),
                commit=False,
            )
            await self.session.commit()
            return output.assistant_text, provider.model, sid, tool_call_log

    async def chat_stream(
        self,
        user_messages: list[ChatMessageIn],
        session_id: int | None = None,
        pdf_ids: list[int] | None = None,
    ) -> tuple[AsyncIterator[dict], int]:
        self._validate_request_messages(user_messages)
        sid, session_created = await self._ensure_session(
            session_id, user_messages[-1].content if user_messages else "New Chat"
        )

        async def _generate() -> AsyncIterator[dict]:
            async with session_lock_service.lock(sid):
                persisted_messages = await self._persist_incoming_messages(
                    sid,
                    user_messages,
                    session_created=session_created,
                )
                provider = await self._get_provider()
                runtime_link = await self._get_or_open_runtime_link(
                    session_id=sid,
                    provider_model=provider.model,
                    provider=provider,
                )
                chat_session = await self.conversation_repo.get_session(sid)
                if chat_session is None:
                    raise ValueError(f"Session not found: {sid}")
                current_user_message = persisted_messages[-1]
                host_context_state = await self._build_host_context_state(
                    current_user_text=current_user_message.content,
                    chat_session=chat_session,
                )
                runtime = self._create_native_runtime(provider=provider, chat_session=chat_session)
                context_sync_result = await runtime.sync_host_context(runtime_link, host_context_state)
                turn_input = AgentTurnInput(
                    messages=[TurnMessage(role="user", content=current_user_message.content)],
                    stream=True,
                    transient_resource_handles=self._build_transient_resource_handles(pdf_ids),
                    request_metadata={"current_user_message_id": current_user_message.id},
                )
                run = await self.conversation_repo.create_run(sid, status="running", commit=False)
                await self.session.commit()

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

                async def on_runtime_event(event: dict[str, Any]) -> None:
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
                        output = await runtime.run_turn(runtime_link, turn_input, emit=on_runtime_event)
                        tool_call_log = [record.model_dump(mode="json") for record in output.tool_records]
                        await self._attach_initial_pdf_ids(sid, pdf_ids)
                        await self._attach_fetched_pdfs_from_log(sid, tool_call_log)
                        assistant_message = await self.conversation_repo.add_message(
                            sid,
                            "assistant",
                            output.assistant_text,
                            commit=False,
                        )
                        await self.conversation_repo.update_run(
                            run.id,
                            status=output.status,
                            assistant_message_id=assistant_message.id,
                            commit=False,
                        )
                        runtime_snapshot = await self._persist_runtime_state(
                            session_id=sid,
                            runtime=runtime,
                            runtime_link=runtime_link,
                            commit=False,
                        )
                        long_term_memory_writes = await self._write_long_term_memory(
                            session_id=sid,
                            run_id=run.id,
                            user_request=current_user_message.content,
                            assistant_message=output.assistant_text,
                            tool_records=tool_call_log,
                            commit=False,
                        )
                        await self._persist_run_debug_payload(
                            run_id=run.id,
                            payload=self._build_run_debug_payload(
                                provider=provider,
                                runtime_link=runtime_link,
                                context_sync_result=context_sync_result,
                                host_context_state=host_context_state,
                                turn_input=turn_input,
                                runtime_snapshot=runtime_snapshot,
                                tool_records=tool_call_log,
                                long_term_memory_writes=long_term_memory_writes,
                                assistant_text=output.assistant_text,
                                assistant_message_id=assistant_message.id,
                                artifacts=output.artifacts,
                                usage=output.usage,
                                status=output.status,
                            ),
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
                        for chunk in _chunk_text(output.assistant_text, 20):
                            await emit({"type": "answer.delta", "delta": chunk}, persist=False)
                        await emit(
                            {
                                "type": "answer.completed",
                                "assistant_message_id": assistant_message.id,
                                "content": output.assistant_text,
                            },
                            persist=False,
                        )
                        await emit(
                            {
                                "type": "run.completed",
                                "run_id": run.id,
                                "assistant_message_id": assistant_message.id,
                                "status": output.status,
                            }
                        )
                        await flush_pending_events(commit=False)
                        await self.session.commit()
                    except ValueError as exc:
                        await self.conversation_repo.update_run(run.id, status="failed", commit=False)
                        runtime_snapshot = await self._persist_runtime_state(
                            session_id=sid,
                            runtime=runtime,
                            runtime_link=runtime_link,
                            commit=False,
                        )
                        await self._attach_initial_pdf_ids(sid, pdf_ids)
                        await self._persist_run_debug_payload(
                            run_id=run.id,
                            payload=self._build_run_debug_payload(
                                provider=provider,
                                runtime_link=runtime_link,
                                context_sync_result=context_sync_result,
                                host_context_state=host_context_state,
                                turn_input=turn_input,
                                runtime_snapshot=runtime_snapshot,
                                tool_records=[],
                                long_term_memory_writes=[],
                                assistant_text=None,
                                status="failed",
                                error={
                                    "type": exc.__class__.__name__,
                                    "message": str(exc),
                                },
                            ),
                            commit=False,
                        )
                        await emit({"type": "error", "message": str(exc), "run_id": run.id})
                        await flush_pending_events(commit=False)
                        await self.session.commit()
                    except Exception as exc:
                        logger.exception("Streaming run failed")
                        await self.conversation_repo.update_run(run.id, status="failed", commit=False)
                        runtime_snapshot = await self._persist_runtime_state(
                            session_id=sid,
                            runtime=runtime,
                            runtime_link=runtime_link,
                            commit=False,
                        )
                        await self._attach_initial_pdf_ids(sid, pdf_ids)
                        await self._persist_run_debug_payload(
                            run_id=run.id,
                            payload=self._build_run_debug_payload(
                                provider=provider,
                                runtime_link=runtime_link,
                                context_sync_result=context_sync_result,
                                host_context_state=host_context_state,
                                turn_input=turn_input,
                                runtime_snapshot=runtime_snapshot,
                                tool_records=[],
                                long_term_memory_writes=[],
                                assistant_text=None,
                                status="failed",
                                error={
                                    "type": exc.__class__.__name__,
                                    "message": str(exc),
                                },
                            ),
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
        tool_call_log: list[dict[str, Any]],
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


def _chunk_text(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]
