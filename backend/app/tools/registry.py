import logging
from typing import Any

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Simple registry that holds all available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool
        logger.info("Registered tool: %s", tool.name)

    def clear(self) -> None:
        self._tools.clear()

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_all(self, allowed_names: set[str] | None = None) -> list[BaseTool]:
        if allowed_names is None:
            return list(self._tools.values())
        return [tool for tool in self._tools.values() if tool.name in allowed_names]

    def list_schemas(self, allowed_names: set[str] | None = None) -> list[dict]:
        return [tool.schema() for tool in self.list_all(allowed_names)]

    async def execute(
        self,
        name: str,
        *,
        allowed_names: set[str] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        if allowed_names is not None and name not in allowed_names:
            return ToolResult(
                success=False,
                error=(
                    f"Tool '{name}' is not allowed in the current context. "
                    f"Allowed tools: {sorted(allowed_names)}. "
                    "Please choose one of the allowed tools or answer without tools."
                ),
            )
        tool = self.get(name)
        if tool is None:
            return ToolResult(
                success=False,
                error=(
                    f"Unknown tool: '{name}'. "
                    f"Available tools: {[t.name for t in self._tools.values()]}. "
                    f"Please use one of the available tool names."
                ),
            )
        return await tool.validate_and_execute(**kwargs)


# Global singleton
tool_registry = ToolRegistry()
