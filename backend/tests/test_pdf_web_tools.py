from app.services.conversation_service import ConversationService
from app.tools.builtin.fetch_pdf_and_upload import (
    _derive_pdf_filename,
    _parse_content_disposition_filename,
)
from app.tools.builtin.web_fetch import WebFetchTool


def test_parse_content_disposition_filename_rfc5987() -> None:
    header = "attachment; filename*=UTF-8''%E5%8B%9F%E9%9B%86%E8%A6%81%E9%A0%852026.pdf"
    assert _parse_content_disposition_filename(header) == "募集要項2026.pdf"


def test_derive_pdf_filename_fallback_to_url() -> None:
    name = _derive_pdf_filename("https://example.com/files/a-guide.pdf", "")
    assert name == "a-guide.pdf"


def test_web_fetch_html_to_markdown_preserves_links() -> None:
    html = """
    <html><body>
      <h1>募集要項</h1>
      <a href=\"/files/guide.pdf\">download</a>
    </body></html>
    """
    markdown, links = WebFetchTool._html_to_markdown(html, "https://example.com/page")
    assert "[download](https://example.com/files/guide.pdf)" in markdown
    assert "https://example.com/files/guide.pdf" in links
    assert WebFetchTool._is_pdf_link("https://example.com/files/guide.pdf")


def test_parse_fetch_pdf_tool_result() -> None:
    payload = '{"pdf_id": 11, "source_url": "https://example.com/a.pdf"}'
    parsed = ConversationService._parse_fetch_pdf_tool_result(payload)
    assert parsed == {"pdf_id": 11, "source_url": "https://example.com/a.pdf"}
