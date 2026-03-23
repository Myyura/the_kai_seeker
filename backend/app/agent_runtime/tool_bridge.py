import json
from typing import Any

from app.agent_runtime.types import CommandSpec, ToolDefinition
from app.tools.base import BaseTool, ToolResult
from app.tools.registry import tool_registry

DEFAULT_TOOL_TIMEOUT_SECONDS = 60


class ToolBridge:
    """Builds stable tool definitions and executes native tools."""

    def build_definitions(self, *, allowed_names: set[str] | None = None) -> list[ToolDefinition]:
        return [self._build_definition(tool) for tool in tool_registry.list_all(allowed_names)]

    async def execute_native(self, name: str, **kwargs: Any) -> ToolResult:
        return await tool_registry.execute(name, **kwargs)

    @staticmethod
    def _build_definition(tool: BaseTool) -> ToolDefinition:
        args_schema = tool.Args.model_json_schema()
        command = f"kai-tool run {tool.name} --json '<json-args>'"
        example_payload = json.dumps({}, ensure_ascii=False)
        return ToolDefinition(
            name=tool.name,
            description=tool.description,
            display_name=tool.display_name,
            activity_label=tool.activity_label,
            args_schema=args_schema,
            usage_guidelines=list(tool.usage_guidelines),
            native_handler=tool.name,
            command_spec=CommandSpec(
                command="kai-tool",
                args_template=f"run {tool.name} --json '<json-args>'",
                example=f"{command.replace('<json-args>', example_payload)}",
                output_format='{"ok": true, "data": ...} or {"ok": false, "error": "..."}',
            ),
            timeout_seconds=DEFAULT_TOOL_TIMEOUT_SECONDS,
            supports_streaming=False,
            tags=[],
        )

    @staticmethod
    def build_tool_policy_schemas(definitions: list[ToolDefinition]) -> list[dict[str, Any]]:
        schemas: list[dict[str, Any]] = []
        for definition in definitions:
            props = definition.args_schema.get("properties", {})
            required = set(definition.args_schema.get("required", []))
            params = []
            for field_name, field_info in props.items():
                params.append(
                    {
                        "name": field_name,
                        "type": field_info.get("type", "any"),
                        "description": field_info.get("description", ""),
                        "required": field_name in required,
                    }
                )
            schemas.append(
                {
                    "name": definition.name,
                    "description": definition.description,
                    "display_name": definition.display_name,
                    "activity_label": definition.activity_label,
                    "usage_guidelines": definition.usage_guidelines,
                    "parameters": params,
                }
            )
        return schemas
