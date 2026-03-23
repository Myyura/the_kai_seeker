import json
from typing import Any, Awaitable, Callable

from app.agent_runtime.base import AgentRuntime
from app.agent_runtime.native_loop import run_native_agent_loop
from app.agent_runtime.short_term_memory import ShortTermMemoryService
from app.agent_runtime.tool_bridge import ToolBridge
from app.agent_runtime.types import (
    AgentRuntimeHealth,
    AgentRuntimeLink,
    AgentRuntimeSetup,
    AgentRuntimeSnapshot,
    AgentTurnInput,
    AgentTurnOutput,
    HostContextState,
    HostContextSyncResult,
    ToolDefinition,
    ToolRecord,
)
from app.config.agent_policy import build_tool_policy
from app.providers.base import BaseLLMProvider, ProviderMessage
from app.services.domain_config import domain_config
from app.services.request_context import set_active_pdf_ids


class NativeAgentRuntime(AgentRuntime):
    name = "native"

    def __init__(
        self,
        *,
        provider: BaseLLMProvider,
        stored_messages: list[Any],
        stored_runs: list[Any],
        initial_short_term_memory_payload: str | dict[str, Any] | None,
        tool_loop_runner: Callable[..., Awaitable[tuple[str, list[dict[str, Any]]]]] = run_native_agent_loop,
        short_term_memory_service: ShortTermMemoryService | None = None,
        tool_bridge: ToolBridge | None = None,
    ) -> None:
        self.provider = provider
        self.stored_messages = stored_messages
        self.stored_runs = stored_runs
        self.initial_short_term_memory_payload = initial_short_term_memory_payload
        self.tool_loop_runner = tool_loop_runner
        self.short_term_memory_service = short_term_memory_service or ShortTermMemoryService()
        self.tool_bridge = tool_bridge or ToolBridge()
        self.host_context_state: HostContextState | None = None
        self.short_term_memory = self.short_term_memory_service.load(initial_short_term_memory_payload)
        self.last_snapshot: AgentRuntimeSnapshot | None = None

    async def open_session(
        self,
        link: AgentRuntimeLink | None,
        setup: AgentRuntimeSetup,
    ) -> AgentRuntimeLink:
        if link is not None:
            return link
        runtime_session_id = f"native-session-{setup.metadata.get('chat_session_id', 'new')}"
        return AgentRuntimeLink(
            chat_session_id=int(setup.metadata.get("chat_session_id", 0)),
            runtime_name=self.name,
            runtime_session_id=runtime_session_id,
            runtime_conversation_id=None,
            base_system_prompt=setup.base_system_prompt,
            status="active",
            metadata={
                "model_name": setup.model_name,
                "timezone": setup.timezone,
                "language": setup.language,
            },
        )

    async def sync_host_context(
        self,
        link: AgentRuntimeLink,
        state: HostContextState,
    ) -> HostContextSyncResult:
        applied = self.host_context_state is None or self.host_context_state.context_version != state.context_version
        self.host_context_state = state
        return HostContextSyncResult(applied=applied, context_version=state.context_version)

    def prepare_short_term_memory(
        self,
        *,
        current_user_message_id: int,
        current_user_text: str,
    ) -> dict[str, Any]:
        payload = self.initial_short_term_memory_payload
        if isinstance(payload, str) and payload.strip() not in {"", "{}"}:
            state = self.short_term_memory_service.load(payload)
        else:
            historical_messages = [
                message for message in self.stored_messages if getattr(message, "id", 0) < current_user_message_id
            ]
            state = self.short_term_memory_service.rebuild_from_history(
                historical_messages,
                self.stored_runs,
            )
        self.short_term_memory = self.short_term_memory_service.record_user_turn(state, current_user_text)
        return self.short_term_memory

    async def run_turn(
        self,
        link: AgentRuntimeLink,
        turn_input: AgentTurnInput,
        emit: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> AgentTurnOutput:
        if self.host_context_state is None:
            raise ValueError("Host context must be synced before running a turn.")
        current_user_message_id = int(turn_input.request_metadata.get("current_user_message_id", 0))
        current_user_text = turn_input.messages[-1].content if turn_input.messages else ""
        if current_user_message_id <= 0:
            raise ValueError("current_user_message_id is required for NativeAgentRuntime.")

        self.prepare_short_term_memory(
            current_user_message_id=current_user_message_id,
            current_user_text=current_user_text,
        )
        messages = self._build_provider_messages(
            base_system_prompt=link.base_system_prompt,
            turn_input=turn_input,
            current_user_message_id=current_user_message_id,
            current_user_text=current_user_text,
        )

        allowed_tool_names = self._resolve_allowed_tool_names()
        try:
            with set_active_pdf_ids(self._collect_active_pdf_ids(turn_input)):
                assistant_text, tool_call_log = await self.tool_loop_runner(
                    self.provider,
                    messages,
                    allowed_tool_names=allowed_tool_names,
                    on_event=emit,
                )
        except Exception as exc:
            self.short_term_memory_service.record_failure(
                self.short_term_memory,
                user_request=current_user_text,
                error_message=str(exc),
            )
            self.last_snapshot = self._build_snapshot(
                link=link,
                summary="Run failed",
                opaque_state={
                    "status": "failed",
                    "context_version": self.host_context_state.context_version,
                },
            )
            raise

        self.short_term_memory_service.record_turn_outcome(
            self.short_term_memory,
            user_request=current_user_text,
            assistant_message=assistant_text,
            tool_entries=tool_call_log,
            status="completed",
        )
        self.last_snapshot = self._build_snapshot(
            link=link,
            summary=self._preview(assistant_text, limit=320),
            opaque_state={
                "status": "completed",
                "context_version": self.host_context_state.context_version,
            },
        )
        return AgentTurnOutput(
            assistant_text=assistant_text,
            events=[],
            usage=None,
            tool_records=[ToolRecord.model_validate(item) for item in tool_call_log],
            snapshot=self.last_snapshot,
            artifacts={},
            status="completed",
        )

    async def get_snapshot(self, link: AgentRuntimeLink) -> AgentRuntimeSnapshot | None:
        return self.last_snapshot

    async def close_session(self, link: AgentRuntimeLink) -> None:
        return None

    async def healthcheck(self) -> AgentRuntimeHealth:
        return AgentRuntimeHealth(ok=True, detail="native runtime available")

    def dump_short_term_memory(self) -> str:
        return self.short_term_memory_service.dump(self.short_term_memory)

    def _build_provider_messages(
        self,
        *,
        base_system_prompt: str,
        turn_input: AgentTurnInput,
        current_user_message_id: int,
        current_user_text: str,
    ) -> list[ProviderMessage]:
        recent_messages = [
            message for message in self.stored_messages if getattr(message, "id", None) != current_user_message_id
        ]
        recent_window = domain_config.recent_message_window
        if recent_window > 0:
            recent_messages = recent_messages[-recent_window:]
        else:
            recent_messages = []

        messages = [
            ProviderMessage(role="system", content=base_system_prompt),
            ProviderMessage(role="system", content=self._render_runtime_context(turn_input)),
        ]
        messages.extend(
            ProviderMessage(role=message.role, content=message.content) for message in recent_messages
        )
        messages.append(ProviderMessage(role="assistant", content=self._build_tool_results_context()))
        messages.append(ProviderMessage(role="user", content=current_user_text))
        return messages

    def _render_runtime_context(self, turn_input: AgentTurnInput) -> str:
        short_term_memory_prompt = self.short_term_memory_service.render_prompt_block(
            self.short_term_memory
        )
        host_context_prompt = self._render_host_context(turn_input)
        return f"{short_term_memory_prompt}\n\n{host_context_prompt}".strip()

    def _render_host_context(self, turn_input: AgentTurnInput) -> str:
        state = self.host_context_state
        if state is None:
            return "## Host Context\n- None."

        sections = ["## Host Context"]
        sections.append(self._render_memory_pack_section(state))
        sections.append(self._render_skill_section(state))
        sections.append(self._render_resource_section("Session Resources", state.session_resource_handles))
        sections.append(
            self._render_resource_section("Turn Resources", turn_input.transient_resource_handles)
        )
        sections.append(self._render_tool_policy_section(state.tool_definitions))
        return "\n\n".join(section for section in sections if section)

    def _render_memory_pack_section(self, state: HostContextState) -> str:
        memory_pack = state.memory_pack
        lines = ["### Memory Pack"]
        if memory_pack.study_targets:
            lines.append("- Study targets:")
            for target in memory_pack.study_targets:
                parts = [target.label, f"school={target.school_id}"]
                if target.program_id:
                    parts.append(f"program={target.program_id}")
                if target.notes:
                    parts.append(f"notes={target.notes}")
                lines.append(f"  - {' | '.join(parts)}")
        derived_sections = {
            "Preferences": memory_pack.preferences,
            "Profile facts": memory_pack.profile_facts,
            "Session insights": memory_pack.session_insights,
            "Strength signals": memory_pack.strength_signals,
            "Weakness signals": memory_pack.weakness_signals,
            "Learning patterns": memory_pack.learning_patterns,
            "Plan hints": memory_pack.plan_hints,
        }
        has_derived = False
        for title, items in derived_sections.items():
            if not items:
                continue
            has_derived = True
            lines.append(f"- {title}:")
            for item in items:
                text = item.summary or item.content
                lines.append(f"  - {text}")
        if len(lines) == 1:
            lines.append("- No long-term host context is currently available.")
        elif not memory_pack.study_targets and not has_derived:
            lines.append("- No long-term host context is currently available.")
        return "\n".join(lines)

    def _render_skill_section(self, state: HostContextState) -> str:
        if not state.skill_definitions:
            return "### Active Skills\n- None."
        blocks = ["### Active Skills"]
        for skill in state.skill_definitions:
            blocks.append(f"#### {skill.name}\n{skill.prompt_block}")
        return "\n\n".join(blocks)

    def _render_resource_section(self, title: str, handles: list[Any]) -> str:
        if not handles:
            return f"### {title}\n- None."
        lines = [f"### {title}"]
        for handle in self._dedupe_resource_handles(handles):
            parts = [f"{handle.resource_type}:{handle.resource_id}"]
            if handle.label:
                parts.append(f"label={handle.label}")
            if handle.source:
                parts.append(f"source={handle.source}")
            metadata = ", ".join(
                f"{key}={value}" for key, value in handle.metadata.items() if value not in (None, "")
            )
            if metadata:
                parts.append(metadata)
            lines.append(f"- {' | '.join(parts)}")
        return "\n".join(lines)

    def _render_tool_policy_section(self, definitions: list[ToolDefinition]) -> str:
        allowed_tool_names = self._resolve_allowed_tool_names()
        filtered = definitions
        if allowed_tool_names is not None:
            filtered = [definition for definition in definitions if definition.name in allowed_tool_names]
        if not filtered:
            return "### Tool Access\n- No Kai host tools are currently available."
        policy = build_tool_policy(self.tool_bridge.build_tool_policy_schemas(filtered))
        if allowed_tool_names is not None:
            policy += (
                "\n\n## Tool Access\n"
                "For this request, you may only use these tools: "
                f"{', '.join(sorted(allowed_tool_names))}."
            )
        return policy

    def _resolve_allowed_tool_names(self) -> set[str] | None:
        if self.host_context_state is None:
            return None
        restricted = [skill for skill in self.host_context_state.skill_definitions if skill.allowed_tools]
        if not restricted:
            return None
        allowed: set[str] = set()
        for skill in restricted:
            allowed.update(skill.allowed_tools)
        return allowed

    def _build_tool_results_context(self) -> str:
        entries: list[dict[str, Any]] = []
        for run in sorted(
            self.stored_runs,
            key=lambda item: (
                item.created_at.isoformat() if getattr(item, "created_at", None) else "",
                getattr(item, "id", 0),
            ),
        ):
            entries.extend(self.short_term_memory_service.extract_tool_entries_from_run(run))

        lines = [
            "## Session Tool Results",
            (
                "These are complete results from prior tool executions in the current session. "
                "Reuse them when they already contain the needed URL, content, or identifiers."
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

    def _collect_active_pdf_ids(self, turn_input: AgentTurnInput) -> list[int]:
        handles = self.host_context_state.session_resource_handles if self.host_context_state else []
        merged = self._dedupe_resource_handles([*handles, *turn_input.transient_resource_handles])
        pdf_ids: list[int] = []
        for handle in merged:
            if handle.resource_type != "pdf":
                continue
            try:
                pdf_ids.append(int(handle.resource_id))
            except (TypeError, ValueError):
                continue
        return pdf_ids

    def _build_snapshot(
        self,
        *,
        link: AgentRuntimeLink,
        summary: str | None,
        opaque_state: dict[str, Any],
    ) -> AgentRuntimeSnapshot:
        return AgentRuntimeSnapshot(
            runtime_name=link.runtime_name,
            runtime_session_id=link.runtime_session_id,
            short_term_memory=self.short_term_memory,
            summary=summary,
            opaque_state=opaque_state,
        )

    @staticmethod
    def _dedupe_resource_handles(handles: list[Any]) -> list[Any]:
        deduped: dict[str, Any] = {}
        for handle in handles:
            key = getattr(handle, "resource_key", None) or f"{handle.resource_type}:{handle.resource_id}"
            deduped[key] = handle
        return list(deduped.values())

    @staticmethod
    def _preview(text: str, limit: int = 240) -> str:
        cleaned = " ".join(text.split())
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[: limit - 1] + "…"
