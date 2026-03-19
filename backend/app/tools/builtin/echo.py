from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolResult


class EchoTool(BaseTool):
    """Simple echo tool for testing the tool-calling pipeline."""

    name = "echo"
    description = "Echo back the input message. Useful for testing tool calls."
    display_name = "Echo"
    activity_label = "Echoing input"

    class Args(BaseModel):
        message: str = Field(description="The message to echo back")

    async def execute(self, args: Args) -> ToolResult:
        return ToolResult(success=True, data=f"Echo: {args.message}")
