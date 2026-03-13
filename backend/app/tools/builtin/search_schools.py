import json
from typing import Optional

from pydantic import BaseModel, Field

from app.services.content_index import content_index
from app.tools.base import BaseTool, ToolResult


class SearchSchoolsTool(BaseTool):
    """Search for schools, departments, and programs in the exam database."""

    name = "search_schools"
    description = (
        "Search for graduate schools and their departments/programs available in the exam database. "
        "Use this to find school IDs, department IDs, and program IDs needed for question search. "
        "Returns school names (Japanese), departments, and programs."
    )

    class Args(BaseModel):
        query: Optional[str] = Field(
            default=None,
            description=(
                "Search keyword to filter schools (matches school name, ID, or department name). "
                "Examples: 'tokyo', '東京', 'kyoto', '情報'. Leave empty to list all schools."
            ),
        )

    async def execute(self, args: Args) -> ToolResult:
        if not content_index.is_loaded:
            return ToolResult(success=False, error="Content index not loaded. No data available.")

        results = content_index.search_schools(query=args.query)

        if not results:
            return ToolResult(
                success=True,
                data=f"No schools found matching '{args.query}'. Try a broader search or leave query empty to list all.",
            )

        return ToolResult(success=True, data=json.dumps(results, ensure_ascii=False, indent=2))
