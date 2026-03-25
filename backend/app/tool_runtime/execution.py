import datetime
from typing import Any

from app.agent_runtime.types import ToolCallRecord
from app.providers.base import BaseLLMProvider
from app.tool_runtime.summary_builder import ToolSummaryBuilder
from app.tools.registry import tool_registry


class ToolExecutionService:
    """Executes tools and converts raw results into compact tool-call records."""

    def __init__(self, provider: BaseLLMProvider | None = None):
        self.summary_builder = ToolSummaryBuilder(provider=provider)

    async def execute(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        allowed_tool_names: set[str] | None,
        call_id: str,
        display_name: str | None = None,
        activity_label: str | None = None,
        provider_item_id: str | None = None,
        started_at: datetime.datetime | None = None,
    ) -> ToolCallRecord:
        started = started_at or datetime.datetime.now(datetime.timezone.utc)
        result = await tool_registry.execute(
            tool_name,
            allowed_names=allowed_tool_names,
            **arguments,
        )
        artifacts = await self.summary_builder.build(
            tool_name=tool_name,
            arguments=arguments,
            result=result,
        )
        finished = datetime.datetime.now(datetime.timezone.utc)
        success = bool(result.success)
        error_text = result.error if not success else None
        output = self._build_output(
            call_id=call_id,
            tool_name=tool_name,
            success=success,
            error_text=error_text,
            artifacts=artifacts,
        )
        return ToolCallRecord(
            tool_name=tool_name,
            arguments=arguments,
            call_id=call_id,
            provider_item_id=provider_item_id,
            display_name=display_name,
            activity_label=activity_label,
            success=success,
            status="completed" if success else "failed",
            error_text=error_text,
            output=output,
            artifacts=artifacts,
            started_at=started,
            finished_at=finished,
        )

    @staticmethod
    def _build_output(
        *,
        call_id: str,
        tool_name: str,
        success: bool,
        error_text: str | None,
        artifacts: list,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": success,
            "call_id": call_id,
            "tool_name": tool_name,
        }
        if success:
            payload["artifacts"] = [
                {
                    "kind": artifact.kind,
                    "label": artifact.label,
                    "summary": artifact.summary,
                    "locator": artifact.locator,
                    "replay": artifact.replay,
                }
                for artifact in artifacts
            ]
        elif error_text:
            payload["error"] = error_text
        return payload
