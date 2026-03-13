import json
from typing import Optional

from pydantic import BaseModel, Field

from app.services.domain_config import domain_config
from app.tools.base import BaseTool, ToolResult


class LookupSourceTool(BaseTool):
    """Look up predefined URLs for schools, organizations, and resources."""

    name = "lookup_source"
    description = (
        "Look up predefined official URLs for schools, organizations, and resources "
        "(e.g. admission pages, past exam archives, scholarship sites). "
        "Use this before web_fetch to find the correct URL without guessing. "
        "Search by school_id, keyword, or category."
    )

    class Args(BaseModel):
        query: Optional[str] = Field(
            default=None,
            description=(
                "Keyword to search for in source name, school_id, or category. "
                "Examples: '東京大学', 'kyoto', 'JASSO', 'scholarship'"
            ),
        )
        school_id: Optional[str] = Field(
            default=None,
            description="Filter by school_id, e.g. 'tokyo-university', 'TITech'",
        )
        category: Optional[str] = Field(
            default=None,
            description="Filter by category: 'admission', 'general'",
        )

    async def execute(self, args: Args) -> ToolResult:
        if not domain_config.is_loaded:
            return ToolResult(success=False, error="Domain config not loaded.")

        if not domain_config.sources:
            return ToolResult(
                success=True,
                data="No predefined sources available for the current domain.",
            )

        results = domain_config.search_sources(
            query=args.query,
            school_id=args.school_id,
            category=args.category,
        )

        if not results:
            return ToolResult(
                success=True,
                data=(
                    f"No sources found matching query='{args.query}', "
                    f"school_id='{args.school_id}', category='{args.category}'. "
                    f"Try a broader search or leave all fields empty to list all sources."
                ),
            )

        compact = []
        for src in results:
            entry = {
                "id": src["id"],
                "name": src["name"],
                "category": src.get("category", ""),
                "urls": src.get("urls", {}),
            }
            if src.get("school_id"):
                entry["school_id"] = src["school_id"]
            compact.append(entry)

        return ToolResult(
            success=True,
            data=json.dumps(compact, ensure_ascii=False, indent=2),
        )
