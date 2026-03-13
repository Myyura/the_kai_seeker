import json
from typing import Optional

from pydantic import BaseModel, Field

from app.services.content_index import content_index
from app.tools.base import BaseTool, ToolResult


class SearchQuestionsTool(BaseTool):
    """Search for past exam questions by school, year, tags, or keyword."""

    name = "search_questions"
    description = (
        "Search past exam questions in the database. Filter by school_id, department_id, "
        "program_id, year, tags, or keyword. Returns question metadata including title, tags, "
        "and links to full content. Use search_schools first to find valid school/department/program IDs."
    )

    class Args(BaseModel):
        school_id: Optional[str] = Field(
            default=None,
            description="School directory name, e.g. 'tokyo-university', 'kyoto-university', 'TITech'",
        )
        department_id: Optional[str] = Field(
            default=None,
            description="Department directory name, e.g. 'IST', 'informatics', 'engineering'",
        )
        program_id: Optional[str] = Field(
            default=None,
            description="Program directory name, e.g. 'ci', 'cs', 'math'",
        )
        year: Optional[int] = Field(
            default=None,
            description="Exam year (the directory year, e.g. 2024, 2025)",
        )
        tags: Optional[list[str]] = Field(
            default=None,
            description="Topic tags to filter by, e.g. ['Linear-Algebra', 'Programming']",
        )
        keyword: Optional[str] = Field(
            default=None,
            description="Free-text keyword to match in title, filename, or tags",
        )
        limit: int = Field(
            default=20,
            ge=1,
            le=50,
            description="Maximum number of results to return (default 20)",
        )

    async def execute(self, args: Args) -> ToolResult:
        if not content_index.is_loaded:
            return ToolResult(success=False, error="Content index not loaded. No data available.")

        results = content_index.search_questions(
            school_id=args.school_id,
            department_id=args.department_id,
            program_id=args.program_id,
            year=args.year,
            tags=args.tags if args.tags else None,
            keyword=args.keyword,
            limit=args.limit,
        )

        if not results:
            filters = {k: v for k, v in args.model_dump().items() if v is not None and k != "limit"}
            return ToolResult(
                success=True,
                data=f"No questions found with filters: {filters}. Try broadening your search.",
            )

        summary = []
        for q in results:
            entry = {
                "id": q["id"],
                "title": q["title"],
                "school_id": q["school_id"],
                "department_id": q["department_id"],
                "program_id": q.get("program_id"),
                "year": q["year"],
                "tags": q.get("tags", []),
                "kai_project_url": q["kai_project_url"],
            }
            summary.append(entry)

        return ToolResult(success=True, data=json.dumps(summary, ensure_ascii=False, indent=2))
