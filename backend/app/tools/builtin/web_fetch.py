import logging
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

MAX_CONTENT_LENGTH = 8000

try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    BeautifulSoup = None

try:
    from markdownify import markdownify as md  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    md = None


class _SimpleLinkMarkdownParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.parts: list[str] = []
        self.links: list[str] = []
        self._active_href: str | None = None
        self._active_anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs):  # type: ignore[override]
        attrs_dict = dict(attrs)
        if tag == "a" and attrs_dict.get("href"):
            self._active_href = urljoin(self.base_url, attrs_dict["href"])
            self._active_anchor_text = []
        elif tag in {"br", "p", "div", "li", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str):  # type: ignore[override]
        if tag == "a" and self._active_href:
            text = "".join(self._active_anchor_text).strip() or self._active_href
            self.parts.append(f"[{text}]({self._active_href})")
            if self._active_href not in self.links:
                self.links.append(self._active_href)
            self._active_href = None
            self._active_anchor_text = []
        elif tag in {"p", "div", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str):  # type: ignore[override]
        text = unescape(data)
        if self._active_href:
            self._active_anchor_text.append(text)
        else:
            self.parts.append(text)


class WebFetchTool(BaseTool):
    """Fetch a web page and return markdown content while preserving links."""

    name = "web_fetch"
    description = (
        "Fetch a web page URL and return markdown content while preserving links. "
        "Use this to retrieve public information such as school admission pages (募集要項), "
        "program details, exam schedules, and downloadable PDF links."
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

        markdown, links = self._html_to_markdown(html, args.url)
        pdf_links = [u for u in links if self._is_pdf_link(u)]

        if len(markdown) > MAX_CONTENT_LENGTH:
            markdown = markdown[:MAX_CONTENT_LENGTH] + "\n\n[Content truncated]"

        return ToolResult(
            success=True,
            data={
                "url": args.url,
                "markdown": markdown,
                "pdf_links": pdf_links,
                "links": links,
            },
        )

    @staticmethod
    def _html_to_markdown(html: str, base_url: str) -> tuple[str, list[str]]:
        if BeautifulSoup is not None and md is not None:
            soup = BeautifulSoup(html, "html.parser")
            for node in soup(["script", "style", "noscript"]):
                node.decompose()

            links: list[str] = []
            seen: set[str] = set()
            for a in soup.find_all("a", href=True):
                abs_url = urljoin(base_url, a.get("href", "").strip())
                if abs_url and abs_url not in seen:
                    seen.add(abs_url)
                    links.append(abs_url)

            markdown = md(
                str(soup),
                heading_style="ATX",
                strip=["script", "style", "noscript"],
                bullets="-",
            )
            markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()
            return markdown, links

        parser = _SimpleLinkMarkdownParser(base_url)
        cleaned = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.S | re.I)
        cleaned = re.sub(r"<style[^>]*>.*?</style>", "", cleaned, flags=re.S | re.I)
        parser.feed(cleaned)
        markdown = re.sub(r"\n{3,}", "\n\n", "".join(parser.parts)).strip()
        return markdown, parser.links

    @staticmethod
    def _is_pdf_link(url: str) -> bool:
        return bool(re.search(r"\.pdf(?:$|[?#])", url, flags=re.IGNORECASE))
