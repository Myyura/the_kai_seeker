import logging
import re

import httpx
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

MAX_CONTENT_LENGTH = 8000


class WebFetchTool(BaseTool):
    """Fetch a web page and return its text content."""

    name = "web_fetch"
    description = (
        "Fetch a web page URL and return its text content. "
        "Use this to retrieve public information such as school admission pages (募集要項), "
        "program details, or exam schedules."
    )

    class Args(BaseModel):
        url: str = Field(description="The full URL to fetch (must start with http:// or https://)")

    async def execute(self, args: Args) -> ToolResult:
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(
                    args.url,
                    headers={"User-Agent": "TheKaiSeeker/0.1 (study-agent)"},
                )
                resp.raise_for_status()
                html = resp.text
        except httpx.HTTPStatusError as e:
            return ToolResult(success=False, error=f"HTTP {e.response.status_code}: {args.url}")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to fetch {args.url}: {e}")

        text = self._html_to_text(html)
        if len(text) > MAX_CONTENT_LENGTH:
            text = text[:MAX_CONTENT_LENGTH] + "\n\n[Content truncated]"

        return ToolResult(success=True, data=text)

    @staticmethod
    def _html_to_text(html: str) -> str:
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"&#\d+;", "", text)
        text = re.sub(r"&\w+;", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return "\n".join(lines)
