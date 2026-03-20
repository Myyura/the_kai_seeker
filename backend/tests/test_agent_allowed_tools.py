import pytest

from app.providers.base import BaseLLMProvider, ChatResponse, ProviderMessage
from app.services.agent import build_prompt_context, run_agent_loop
from app.skills.base import Skill
from app.skills.registry import skill_registry
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
    original_skills = dict(skill_registry._skills)
    try:
        tool_registry.clear()
        skill_registry.clear()
        yield
    finally:
        tool_registry.clear()
        tool_registry._tools.update(original_tools)
        skill_registry.clear()
        skill_registry._skills.update(original_skills)


def test_build_prompt_context_filters_tools_by_allowed_tools() -> None:
    tool_registry.register(EchoTool())
    tool_registry.register(OtherTool())
    skill_registry.register(
        Skill(
            name="restricted",
            display_name="Restricted",
            description="Limit tools",
            body="Use only echo.",
            trigger="restricted",
            allowed_tools=["echo"],
        )
    )

    prompt, allowed_tool_names = build_prompt_context("this is a restricted task")

    assert allowed_tool_names == {"echo"}
    assert "**echo**" in prompt
    assert "other_tool" not in prompt


@pytest.mark.asyncio
async def test_run_agent_loop_rejects_disallowed_tools() -> None:
    tool_registry.register(EchoTool())
    tool_registry.register(OtherTool())

    provider = FakeProvider(
        [
            '<tool_call>\n{"name": "other_tool", "arguments": {"message": "hi"}}\n</tool_call>',
            "final answer",
        ]
    )

    final_answer, tool_call_log = await run_agent_loop(
        provider,
        [ProviderMessage(role="user", content="hello")],
        allowed_tool_names={"echo"},
    )

    assert final_answer == "final answer"
    assert len(tool_call_log) == 1
    assert tool_call_log[0]["tool"] == "other_tool"
    assert tool_call_log[0]["success"] is False
    assert "not allowed" in tool_call_log[0]["result"]
