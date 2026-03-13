"""Example user tool — rename this file (remove the leading underscore) to activate.

This tool demonstrates the structure of a user-defined tool.
"""

from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolResult


class ExampleTool(BaseTool):
    name = "example_calculator"
    description = "Evaluate a simple arithmetic expression. Useful when the user needs precise calculations."

    class Args(BaseModel):
        expression: str = Field(description="Arithmetic expression to evaluate, e.g. '2 + 3 * 4'")

    async def execute(self, args: Args) -> ToolResult:
        try:
            allowed_chars = set("0123456789+-*/.() ")
            if not all(c in allowed_chars for c in args.expression):
                return ToolResult(success=False, error="Expression contains invalid characters")
            result = eval(args.expression)  # noqa: S307
            return ToolResult(success=True, data=f"{args.expression} = {result}")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to evaluate: {e}")
