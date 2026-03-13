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

    def list_all(self) -> list[BaseTool]:
        return list(self._tools.values())

    def list_schemas(self) -> list[dict]:
        return [t.schema() for t in self._tools.values()]

    async def execute(self, name: str, **kwargs: Any) -> ToolResult:
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
