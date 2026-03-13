"""Tool abstraction layer for The Kai Seeker (解を求める者).

This file is part of The Kai Seeker, licensed under AGPL-3.0.
Source: https://github.com/Myyura/the_kai_seeker
"""

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: str | None = None

    def to_text(self) -> str:
        if not self.success:
            return f"Error: {self.error}"
        if isinstance(self.data, str):
            return self.data
        return json.dumps(self.data, ensure_ascii=False, indent=2)


class BaseTool(ABC):
    """Base class for all tools.

    Subclasses must:
    1. Set `name` and `description` class attributes
    2. Define an inner `Args(BaseModel)` class with typed, documented fields
    3. Implement `execute(self, args: Args) -> ToolResult`
    """

    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    Args: ClassVar[type[BaseModel]]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.name:
            cls.name = cls.__name__

    @abstractmethod
    async def execute(self, args: BaseModel) -> ToolResult:
        """Execute the tool with validated arguments."""

    async def validate_and_execute(self, **kwargs: Any) -> ToolResult:
        """Validate kwargs against the Args model, then execute.

        If validation fails, returns a ToolResult with the Pydantic error
        message so the LLM can self-correct on the next turn.
        """
        try:
            args = self.Args.model_validate(kwargs)
        except ValidationError as e:
            errors = []
            for err in e.errors():
                loc = " → ".join(str(x) for x in err["loc"])
                errors.append(f"  - {loc}: {err['msg']} (type: {err['type']})")
            hint = "\n".join(errors)
            expected = self._describe_params()
            return ToolResult(
                success=False,
                error=(
                    f"Invalid arguments for tool '{self.name}':\n{hint}\n\n"
                    f"Expected parameters:\n{expected}\n\n"
                    f"Please fix the arguments and try again."
                ),
            )

        return await self.execute(args)

    def _describe_params(self) -> str:
        lines = []
        schema = self.Args.model_json_schema()
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        for field_name, field_info in props.items():
            ftype = field_info.get("type", "any")
            desc = field_info.get("description", "")
            req = "required" if field_name in required else "optional"
            lines.append(f"  - {field_name} ({ftype}, {req}): {desc}")
        return "\n".join(lines) if lines else "  (no parameters)"

    def schema(self) -> dict:
        """Return a JSON-serializable description for LLM prompt injection."""
        json_schema = self.Args.model_json_schema()
        props = json_schema.get("properties", {})
        required = set(json_schema.get("required", []))
        params = []
        for field_name, field_info in props.items():
            params.append({
                "name": field_name,
                "type": field_info.get("type", "any"),
                "description": field_info.get("description", ""),
                "required": field_name in required,
            })
        return {
            "name": self.name,
            "description": self.description,
            "parameters": params,
        }
