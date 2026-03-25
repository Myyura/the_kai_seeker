import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class TurnMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ResourceHandle(BaseModel):
    resource_type: str
    resource_id: str
    label: str | None = None
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def resource_key(self) -> str:
        return f"{self.resource_type}:{self.resource_id}"


class CommandSpec(BaseModel):
    command: str
    args_template: str
    example: str
    output_format: str


class ToolDefinition(BaseModel):
    name: str
    description: str
    display_name: str
    activity_label: str
    args_schema: dict[str, Any]
    usage_guidelines: list[str] = Field(default_factory=list)
    native_handler: str | None = None
    command_spec: CommandSpec
    timeout_seconds: int = 60
    supports_streaming: bool = False
    tags: list[str] = Field(default_factory=list)

    def canonical_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        return payload


class SkillDefinition(BaseModel):
    name: str
    description: str
    trigger_rules: list[str] = Field(default_factory=list)
    prompt_block: str
    allowed_tools: list[str] = Field(default_factory=list)
    priority: int = 0
    tags: list[str] = Field(default_factory=list)

    def canonical_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class MemoryItem(BaseModel):
    id: int | None = None
    memory_type: str
    content: str
    summary: str | None = None
    importance: float = 0.5
    confidence: float = 0.5
    related_target_id: int | None = None
    tags: list[str] = Field(default_factory=list)

    def canonical_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"id"})


class StudyTargetMemory(BaseModel):
    id: int
    school_id: str
    program_id: str | None = None
    label: str
    notes: str | None = None


class MemoryPack(BaseModel):
    study_targets: list[StudyTargetMemory] = Field(default_factory=list)
    preferences: list[MemoryItem] = Field(default_factory=list)
    profile_facts: list[MemoryItem] = Field(default_factory=list)
    session_insights: list[MemoryItem] = Field(default_factory=list)
    strength_signals: list[MemoryItem] = Field(default_factory=list)
    weakness_signals: list[MemoryItem] = Field(default_factory=list)
    learning_patterns: list[MemoryItem] = Field(default_factory=list)
    plan_hints: list[MemoryItem] = Field(default_factory=list)

    def canonical_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class HostContextState(BaseModel):
    context_version: str
    memory_pack: MemoryPack = Field(default_factory=MemoryPack)
    tool_definitions: list[ToolDefinition] = Field(default_factory=list)
    skill_definitions: list[SkillDefinition] = Field(default_factory=list)
    session_resource_handles: list[ResourceHandle] = Field(default_factory=list)

    @classmethod
    def build(
        cls,
        *,
        memory_pack: MemoryPack,
        tool_definitions: list[ToolDefinition],
        skill_definitions: list[SkillDefinition],
        session_resource_handles: list[ResourceHandle],
    ) -> "HostContextState":
        payload = {
            "memory_pack": memory_pack.canonical_payload(),
            "tool_definitions": [tool.canonical_payload() for tool in tool_definitions],
            "skill_definitions": [skill.canonical_payload() for skill in skill_definitions],
            "session_resource_handles": [
                handle.model_dump(mode="json") for handle in session_resource_handles
            ],
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        version = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return cls(
            context_version=version,
            memory_pack=memory_pack,
            tool_definitions=tool_definitions,
            skill_definitions=skill_definitions,
            session_resource_handles=session_resource_handles,
        )


class AgentRuntimeLink(BaseModel):
    id: int | None = None
    chat_session_id: int
    runtime_name: str
    runtime_session_id: str
    runtime_conversation_id: str | None = None
    base_system_prompt: str
    status: str = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRuntimeSetup(BaseModel):
    base_system_prompt: str
    model_name: str | None = None
    timezone: str | None = None
    language: str | None = None
    runtime_capabilities_required: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentTurnInput(BaseModel):
    messages: list[TurnMessage]
    stream: bool = False
    model_override: str | None = None
    max_steps: int | None = None
    transient_resource_handles: list[ResourceHandle] = Field(default_factory=list)
    request_metadata: dict[str, Any] = Field(default_factory=dict)


class ToolArtifact(BaseModel):
    id: int | None = None
    kind: str
    label: str | None = None
    summary: str
    summary_format: Literal["text", "markdown", "json"] = "text"
    body_text: str | None = None
    body_json: dict[str, Any] | list[Any] | None = None
    locator: dict[str, Any] = Field(default_factory=dict)
    replay: dict[str, Any] | None = None
    search_text: str = ""
    is_primary: bool = True


class ToolCallRecord(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    call_id: str
    provider_item_id: str | None = None
    display_name: str | None = None
    activity_label: str | None = None
    success: bool = True
    status: Literal["requested", "running", "completed", "failed"] = "completed"
    error_text: str | None = None
    output: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[ToolArtifact] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ToolLoopResult(BaseModel):
    assistant_text: str
    turn_summary: str | None = None
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    usage: dict[str, Any] | None = None


class AgentRuntimeSnapshot(BaseModel):
    runtime_name: str
    runtime_session_id: str
    short_term_memory: dict[str, Any] = Field(default_factory=dict)
    turn_summary: str | None = None
    opaque_state: dict[str, Any] = Field(default_factory=dict)
    provider: dict[str, Any] = Field(default_factory=dict)
    runtime_link: dict[str, Any] = Field(default_factory=dict)
    context_sync: dict[str, Any] = Field(default_factory=dict)
    host_context_state: dict[str, Any] = Field(default_factory=dict)
    turn_input: dict[str, Any] = Field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    long_term_memory_writes: list[dict[str, Any]] = Field(default_factory=list)
    assistant_text: str | None = None
    usage: dict[str, Any] | None = None
    status: str | None = None
    error: dict[str, Any] | None = None
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentTurnOutput(BaseModel):
    assistant_text: str
    turn_summary: str | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    usage: dict[str, Any] | None = None
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    snapshot: AgentRuntimeSnapshot | None = None
    status: str = "completed"


class HostContextSyncResult(BaseModel):
    applied: bool = True
    context_version: str


class AgentRuntimeHealth(BaseModel):
    ok: bool
    detail: str | None = None
