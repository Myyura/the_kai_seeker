import logging

import httpx
from pydantic import BaseModel, Field

from app.services.content_index import content_index
from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

MAX_CONTENT_LENGTH = 12000


class FetchQuestionTool(BaseTool):
    """Fetch the full Markdown content of a specific exam question from The Kai Project."""

    name = "fetch_question"
    description = (
        "Fetch the full exam question content (Markdown) from The Kai Project GitHub repository. "
        "Requires a question_id obtained from the search_questions tool. "
        "Returns the complete problem statement and solution."
    )

    class Args(BaseModel):
        question_id: str = Field(
            description=(
                "The question ID from search_questions results, "
                "e.g. 'tokyo-university/IST/ci/2025/ci_202408_written_exam_1'"
            ),
        )

    async def execute(self, args: Args) -> ToolResult:
        if not content_index.is_loaded:
            return ToolResult(success=False, error="Content index not loaded.")

        question = content_index.get_question(args.question_id)
        if question is None:
            return ToolResult(
                success=False,
                error=(
                    f"Question '{args.question_id}' not found in the index. "
                    f"Use search_questions first to find valid question IDs."
                ),
            )

        raw_url = question["kai_project_raw_url"]
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(raw_url)
                resp.raise_for_status()
                content = resp.text
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=f"HTTP {e.response.status_code} fetching {raw_url}",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to fetch question: {e}")

        if len(content) > MAX_CONTENT_LENGTH:
            content = content[:MAX_CONTENT_LENGTH] + "\n\n[Content truncated]"

        header = (
            f"Source: {question['kai_project_url']}\n"
            f"School: {question['school_id']} | Dept: {question['department_id']}"
        )
        if question.get("program_id"):
            header += f" | Program: {question['program_id']}"
        header += f" | Year: {question['year']}\n---\n"

        return ToolResult(success=True, data=header + content)
