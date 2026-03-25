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
    AgentRuntimeSnapshot,
    AgentRuntimeSetup,
    AgentTurnInput,
    HostContextState,
    ResourceHandle,
    ToolLoopResult,
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
RUNTIME_SNAPSHOT_VERSION = 3


class ConversationService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        base_system_prompt_builder: Callable[[], str] = build_base_system_prompt,
        tool_loop_runner: Callable[..., Awaitable[ToolLoopResult]] = run_native_agent_loop,
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
        tool_calls: list[dict[str, Any]],
    ) -> None:
        resources: list[dict[str, Any]] = []
        for tool_call in tool_calls:
            if tool_call.get("tool_name") != "fetch_pdf_and_upload":
                continue
            for artifact in tool_call.get("artifacts", []):
                locator = artifact.get("locator", {}) if isinstance(artifact, dict) else {}
                if not isinstance(locator, dict):
                    continue
                pdf_id = locator.get("pdf_id")
                if not isinstance(pdf_id, int):
                    continue
                resources.append(
                    {
                        "pdf_id": pdf_id,
                        "source_type": "fetched",
                        "source_url": locator.get("source_url"),
                    }
                )
        await self.conversation_repo.attach_pdf_resources_bulk(session_id, resources, commit=False)

    async def _persist_runtime_state(
        self,
        *,
        session_id: int,
        runtime: NativeAgentRuntime,
        runtime_link: AgentRuntimeLink,
    ) -> AgentRuntimeSnapshot | None:
        await self.conversation_repo.update_short_term_memory(
            session_id,
            runtime.dump_short_term_memory(),
            commit=False,
        )
        return await runtime.get_snapshot(runtime_link)

    async def _write_long_term_memory(
        self,
        *,
        session_id: int,
        run_id: int,
        user_request: str,
        assistant_message: str,
        turn_summary: str | None,
        tool_calls: list[dict[str, Any]],
        commit: bool = False,
    ) -> list[dict[str, Any]]:
        created_records: list[dict[str, Any]] = []
        record = await self.long_term_memory_service.write_session_insight(
            session_id=session_id,
            run_id=run_id,
            user_request=user_request,
            assistant_message=assistant_message,
            turn_summary=turn_summary,
            tool_calls=tool_calls,
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

    def _build_runtime_snapshot(
        self,
        *,
        base_snapshot: AgentRuntimeSnapshot | None,
        provider: Any,
        runtime_link: AgentRuntimeLink,
        context_sync_result: Any,
        host_context_state: HostContextState,
        turn_input: AgentTurnInput,
        tool_calls: list[dict[str, Any]],
        long_term_memory_writes: list[dict[str, Any]],
        assistant_text: str | None,
        turn_summary: str | None,
        status: str,
        usage: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> AgentRuntimeSnapshot:
        if base_snapshot is None:
            base_snapshot = AgentRuntimeSnapshot(
                runtime_name=runtime_link.runtime_name,
                runtime_session_id=runtime_link.runtime_session_id,
            )
        return base_snapshot.model_copy(
            update={
                "opaque_state": {
                    **base_snapshot.opaque_state,
                    "version": RUNTIME_SNAPSHOT_VERSION,
                },
                "provider": {
                    "name": provider.__class__.__name__,
                    "model": getattr(provider, "model", None),
                },
                "runtime_link": self._serialize_runtime_link(runtime_link),
                "context_sync": context_sync_result.model_dump(mode="json"),
                "host_context_state": host_context_state.model_dump(mode="json"),
                "turn_input": turn_input.model_dump(mode="json"),
                "tool_calls": tool_calls,
                "long_term_memory_writes": long_term_memory_writes,
                "assistant_text": assistant_text,
                "turn_summary": turn_summary,
                "usage": usage,
                "status": status,
                "error": error,
            }
        )

    @staticmethod
    def _serialize_tool_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
        return {
            "kind": artifact.get("kind"),
            "label": artifact.get("label"),
            "summary": artifact.get("summary"),
            "summary_format": artifact.get("summary_format"),
            "locator": artifact.get("locator", {}),
            "replay": artifact.get("replay"),
            "id": artifact.get("id"),
        }

    def _serialize_tool_call(self, tool_call: dict[str, Any]) -> dict[str, Any]:
        return {
            "tool_name": tool_call.get("tool_name"),
            "call_id": tool_call.get("call_id"),
            "provider_item_id": tool_call.get("provider_item_id"),
            "display_name": tool_call.get("display_name"),
            "activity_label": tool_call.get("activity_label"),
            "arguments": tool_call.get("arguments", {}),
            "success": tool_call.get("success", True),
            "status": tool_call.get("status", "completed"),
            "error_text": tool_call.get("error_text"),
            "output": tool_call.get("output", {}),
            "artifacts": [
                self._serialize_tool_artifact(artifact)
                for artifact in tool_call.get("artifacts", [])
                if isinstance(artifact, dict)
            ],
            "started_at": tool_call.get("started_at"),
            "finished_at": tool_call.get("finished_at"),
        }

    async def _persist_tool_calls(
        self,
        *,
        run_id: int,
        tool_calls: list[dict[str, Any]],
        commit: bool = False,
    ) -> list[dict[str, Any]]:
        await self.conversation_repo.save_tool_calls(run_id, tool_calls, commit=commit)
        return [self._serialize_tool_call(tool_call) for tool_call in tool_calls]

    @staticmethod
    def _extract_partial_tool_calls(exc: Exception) -> list[dict[str, Any]]:
        partial = getattr(exc, "tool_calls", None)
        if not isinstance(partial, list):
            return []
        serialized: list[dict[str, Any]] = []
        for item in partial:
            if hasattr(item, "model_dump"):
                serialized.append(item.model_dump(mode="json"))
            elif isinstance(item, dict):
                serialized.append(item)
        return serialized

    @staticmethod
    def _error_payload(exc: Exception) -> dict[str, Any]:
        return {
            "type": getattr(exc, "error_type", exc.__class__.__name__),
            "message": getattr(exc, "error_message", str(exc)),
        }

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
        """Returns (content, model_name, session_id, tool_calls)."""
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
                partial_tool_calls = self._extract_partial_tool_calls(exc)
                await self.conversation_repo.update_run(run.id, status="failed", commit=False)
                await self._attach_initial_pdf_ids(sid, pdf_ids)
                await self._attach_fetched_pdfs_from_log(sid, partial_tool_calls)
                serialized_tool_calls = await self._persist_tool_calls(
                    run_id=run.id,
                    tool_calls=partial_tool_calls,
                    commit=False,
                )
                base_snapshot = await self._persist_runtime_state(
                    session_id=sid,
                    runtime=runtime,
                    runtime_link=runtime_link,
                )
                snapshot = self._build_runtime_snapshot(
                    base_snapshot=base_snapshot,
                    provider=provider,
                    runtime_link=runtime_link,
                    context_sync_result=context_sync_result,
                    host_context_state=host_context_state,
                    turn_input=turn_input,
                    tool_calls=serialized_tool_calls,
                    long_term_memory_writes=[],
                    assistant_text=None,
                    turn_summary=None,
                    status="failed",
                    error=self._error_payload(exc),
                )
                await self.agent_runtime_repo.save_snapshot(
                    sid,
                    snapshot,
                    run_id=run.id,
                    commit=False,
                )
                await self.session.commit()
                raise

            tool_calls = [record.model_dump() for record in output.tool_calls]
            await self._attach_initial_pdf_ids(sid, pdf_ids)
            await self._attach_fetched_pdfs_from_log(sid, tool_calls)

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
            serialized_tool_calls = await self._persist_tool_calls(
                run_id=run.id,
                tool_calls=tool_calls,
                commit=False,
            )
            base_snapshot = await self._persist_runtime_state(
                session_id=sid,
                runtime=runtime,
                runtime_link=runtime_link,
            )
            long_term_memory_writes = await self._write_long_term_memory(
                session_id=sid,
                run_id=run.id,
                user_request=current_user_message.content,
                assistant_message=output.assistant_text,
                turn_summary=output.turn_summary,
                tool_calls=tool_calls,
                commit=False,
            )
            snapshot = self._build_runtime_snapshot(
                base_snapshot=base_snapshot,
                provider=provider,
                runtime_link=runtime_link,
                context_sync_result=context_sync_result,
                host_context_state=host_context_state,
                turn_input=turn_input,
                tool_calls=serialized_tool_calls,
                long_term_memory_writes=long_term_memory_writes,
                assistant_text=output.assistant_text,
                turn_summary=output.turn_summary,
                usage=output.usage,
                status=output.status,
            )
            await self.agent_runtime_repo.save_snapshot(
                sid,
                snapshot,
                run_id=run.id,
                commit=False,
            )
            await self.session.commit()
            return output.assistant_text, provider.model, sid, tool_calls

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

                async def emit(event: dict[str, Any]) -> None:
                    nonlocal sequence
                    sequence += 1
                    payload = {"sequence": sequence, **event}
                    await queue.put(payload)

                async def on_runtime_event(event: dict[str, Any]) -> None:
                    await emit(dict(event))

                async def produce() -> None:
                    try:
                        await emit({"type": "run.started", "run_id": run.id, "status": "running"})
                        output = await runtime.run_turn(runtime_link, turn_input, emit=on_runtime_event)
                        tool_calls = [record.model_dump() for record in output.tool_calls]
                        await self._attach_initial_pdf_ids(sid, pdf_ids)
                        await self._attach_fetched_pdfs_from_log(sid, tool_calls)
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
                        serialized_tool_calls = await self._persist_tool_calls(
                            run_id=run.id,
                            tool_calls=tool_calls,
                            commit=False,
                        )
                        base_snapshot = await self._persist_runtime_state(
                            session_id=sid,
                            runtime=runtime,
                            runtime_link=runtime_link,
                        )
                        long_term_memory_writes = await self._write_long_term_memory(
                            session_id=sid,
                            run_id=run.id,
                            user_request=current_user_message.content,
                            assistant_message=output.assistant_text,
                            tool_calls=tool_calls,
                            commit=False,
                        )
                        snapshot = self._build_runtime_snapshot(
                            base_snapshot=base_snapshot,
                            provider=provider,
                            runtime_link=runtime_link,
                            context_sync_result=context_sync_result,
                            host_context_state=host_context_state,
                            turn_input=turn_input,
                            tool_calls=serialized_tool_calls,
                            long_term_memory_writes=long_term_memory_writes,
                            assistant_text=output.assistant_text,
                            turn_summary=output.turn_summary,
                            usage=output.usage,
                            status=output.status,
                        )
                        await self.agent_runtime_repo.save_snapshot(
                            sid,
                            snapshot,
                            run_id=run.id,
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
                            await emit({"type": "answer.delta", "delta": chunk})
                        await emit(
                            {
                                "type": "answer.completed",
                                "assistant_message_id": assistant_message.id,
                                "content": output.assistant_text,
                                "turn_summary": output.turn_summary,
                            },
                        )
                        await emit(
                            {
                                "type": "run.completed",
                                "run_id": run.id,
                                "assistant_message_id": assistant_message.id,
                                "status": output.status,
                            }
                        )
                        await self.session.commit()
                    except ValueError as exc:
                        partial_tool_calls = self._extract_partial_tool_calls(exc)
                        await self.conversation_repo.update_run(run.id, status="failed", commit=False)
                        await self._attach_initial_pdf_ids(sid, pdf_ids)
                        await self._attach_fetched_pdfs_from_log(sid, partial_tool_calls)
                        serialized_tool_calls = await self._persist_tool_calls(
                            run_id=run.id,
                            tool_calls=partial_tool_calls,
                            commit=False,
                        )
                        base_snapshot = await self._persist_runtime_state(
                            session_id=sid,
                            runtime=runtime,
                            runtime_link=runtime_link,
                        )
                        snapshot = self._build_runtime_snapshot(
                            base_snapshot=base_snapshot,
                            provider=provider,
                            runtime_link=runtime_link,
                            context_sync_result=context_sync_result,
                            host_context_state=host_context_state,
                            turn_input=turn_input,
                            tool_calls=serialized_tool_calls,
                            long_term_memory_writes=[],
                            assistant_text=None,
                            turn_summary=None,
                            status="failed",
                            error=self._error_payload(exc),
                        )
                        await self.agent_runtime_repo.save_snapshot(
                            sid,
                            snapshot,
                            run_id=run.id,
                            commit=False,
                        )
                        await emit({"type": "error", "message": str(exc), "run_id": run.id})
                        await self.session.commit()
                    except Exception as exc:
                        logger.exception("Streaming run failed")
                        partial_tool_calls = self._extract_partial_tool_calls(exc)
                        error_payload = self._error_payload(exc)
                        await self.conversation_repo.update_run(run.id, status="failed", commit=False)
                        await self._attach_initial_pdf_ids(sid, pdf_ids)
                        await self._attach_fetched_pdfs_from_log(sid, partial_tool_calls)
                        serialized_tool_calls = await self._persist_tool_calls(
                            run_id=run.id,
                            tool_calls=partial_tool_calls,
                            commit=False,
                        )
                        base_snapshot = await self._persist_runtime_state(
                            session_id=sid,
                            runtime=runtime,
                            runtime_link=runtime_link,
                        )
                        snapshot = self._build_runtime_snapshot(
                            base_snapshot=base_snapshot,
                            provider=provider,
                            runtime_link=runtime_link,
                            context_sync_result=context_sync_result,
                            host_context_state=host_context_state,
                            turn_input=turn_input,
                            tool_calls=serialized_tool_calls,
                            long_term_memory_writes=[],
                            assistant_text=None,
                            turn_summary=None,
                            status="failed",
                            error=error_payload,
                        )
                        await self.agent_runtime_repo.save_snapshot(
                            sid,
                            snapshot,
                            run_id=run.id,
                            commit=False,
                        )
                        await emit(
                            {
                                "type": "error",
                                "message": error_payload["message"],
                                "run_id": run.id,
                            }
                        )
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

def _chunk_text(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]
