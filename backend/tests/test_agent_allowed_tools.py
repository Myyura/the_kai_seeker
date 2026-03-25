import json

import pytest

from app.agent_runtime.native import NativeAgentRuntime
from app.agent_runtime.native_loop import run_native_agent_loop
from app.agent_runtime.tool_bridge import ToolBridge
from app.agent_runtime.types import HostContextState, MemoryPack, SkillDefinition
from app.providers.base import BaseLLMProvider, ChatResponse, ProviderMessage
from app.tools.base import BaseTool, ToolResult
from app.tools.registry import tool_registry


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo input."
    display_name = "Echo"
    activity_label = "Echoing"

    class Args:  # type: ignore[no-redef]
        @staticmethod
        def model_validate(kwargs):  # type: ignore[no-untyped-def]
            class _Args:
                message = kwargs.get("message", "")

            return _Args()

        @staticmethod
        def model_json_schema() -> dict:
            return {
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Message to echo",
                    }
                },
                "required": ["message"],
            }

    async def execute(self, args) -> ToolResult:  # type: ignore[no-untyped-def]
        return ToolResult(success=True, data=f"Echo: {args.message}")


class OtherTool(EchoTool):
    name = "other_tool"
    description = "Another tool."
    display_name = "Other Tool"


class FakePdfQueryTool(BaseTool):
    name = "query_pdf_details"
    description = "Query a processed PDF."
    display_name = "Query PDF"
    activity_label = "Searching PDF details"

    class Args:  # type: ignore[no-redef]
        @staticmethod
        def model_validate(kwargs):  # type: ignore[no-untyped-def]
            class _Args:
                question = kwargs.get("question", "")
                pdf_id = kwargs.get("pdf_id")
                top_k = kwargs.get("top_k", 4)

            return _Args()

        @staticmethod
        def model_json_schema() -> dict:
            return {
                "properties": {
                    "question": {"type": "string", "description": "PDF question"},
                    "pdf_id": {"type": "integer"},
                    "top_k": {"type": "integer"},
                },
                "required": ["question"],
            }

    async def execute(self, args) -> ToolResult:  # type: ignore[no-untyped-def]
        return ToolResult(
            success=True,
            data={
                "pdf_id": args.pdf_id or 15,
                "question": args.question,
                "snippets": [],
                "match_count": 0,
                "no_match": True,
            },
        )


class FakeProvider(BaseLLMProvider):
    def __init__(self, responses: list[str]):
        super().__init__(api_key="test")
        self._responses = responses

    async def chat(self, messages: list[ProviderMessage]) -> ChatResponse:
        return ChatResponse(content=self._responses.pop(0), model="fake")

    async def chat_stream(self, messages: list[ProviderMessage]):  # type: ignore[override]
        raise NotImplementedError

    async def test_connection(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def restore_registries():
    original_tools = dict(tool_registry._tools)
    try:
        tool_registry.clear()
        yield
    finally:
        tool_registry.clear()
        tool_registry._tools.update(original_tools)


def test_native_runtime_tool_policy_filters_tools_by_allowed_tools() -> None:
    tool_registry.register(EchoTool())
    tool_registry.register(OtherTool())

    runtime = NativeAgentRuntime(
        provider=FakeProvider([]),
        stored_messages=[],
        stored_runs=[],
        initial_short_term_memory_payload="{}",
    )
    state = HostContextState.build(
        memory_pack=MemoryPack(),
        tool_definitions=ToolBridge().build_definitions(),
        skill_definitions=[
            SkillDefinition(
                name="restricted",
                description="Limit tools",
                prompt_block="Use only echo.",
                allowed_tools=["echo"],
            )
        ],
        session_resource_handles=[],
    )
    runtime.host_context_state = state

    prompt = runtime._render_tool_policy_section(state.tool_definitions)
    assert runtime._resolve_allowed_tool_names() == {"echo"}
    assert "**echo**" in prompt
    assert "other_tool" not in prompt


@pytest.mark.asyncio
async def test_run_agent_loop_rejects_disallowed_tools() -> None:
    tool_registry.register(EchoTool())
    tool_registry.register(OtherTool())

    provider = FakeProvider(
        [
            json.dumps(
                {
                    "response_type": "tool_call",
                    "assistant_text": "",
                    "turn_summary": "",
                    "tool_call": {"name": "other_tool", "arguments": {"message": "hi"}},
                }
            ),
            json.dumps(
                {
                    "response_type": "final",
                    "assistant_text": "final answer",
                    "turn_summary": "final answer summary",
                    "tool_call": None,
                }
            ),
        ]
    )

    result = await run_native_agent_loop(
        provider,
        [ProviderMessage(role="user", content="hello")],
        allowed_tool_names={"echo"},
    )

    assert result.assistant_text == "final answer"
    assert result.turn_summary == "final answer summary"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "other_tool"
    assert result.tool_calls[0].success is False
    assert "not allowed" in (result.tool_calls[0].error_text or "")


@pytest.mark.asyncio
async def test_run_agent_loop_stops_after_repeated_similar_pdf_no_match() -> None:
    tool_registry.register(FakePdfQueryTool())

    provider = FakeProvider(
        [
            json.dumps(
                {
                    "response_type": "tool_call",
                    "assistant_text": "",
                    "turn_summary": "",
                    "tool_call": {
                        "name": "query_pdf_details",
                        "arguments": {"pdf_id": 15, "question": "有没有特殊材料"},
                    },
                }
            ),
            json.dumps(
                {
                    "response_type": "tool_call",
                    "assistant_text": "",
                    "turn_summary": "",
                    "tool_call": {
                        "name": "query_pdf_details",
                        "arguments": {"pdf_id": 15, "question": "有没有特殊的申请材料或补充材料"},
                    },
                }
            ),
        ]
    )

    result = await run_native_agent_loop(
        provider,
        [ProviderMessage(role="user", content="帮我查 PDF 里有没有特殊材料")],
    )

    assert len(result.tool_calls) == 2
    assert all(record.tool_name == "query_pdf_details" for record in result.tool_calls)
    assert "没有找到明确匹配的片段" in result.assistant_text
    assert "未找到" in (result.turn_summary or "")
