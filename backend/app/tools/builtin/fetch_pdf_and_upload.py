import os
import re
import time
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from app.db.engine import async_session
from app.services.pdf_service import PdfService
from app.tools.base import BaseTool, ToolResult


class FetchPdfAndUploadTool(BaseTool):
    name = "fetch_pdf_and_upload"
    description = (
        "Download a PDF from a URL, save it into the local PDF store, "
        "run full processing (including OCR when needed), and return a summary. "
        "Use this when you discover a PDF link on the web (e.g.,募集要項)."
    )
    display_name = "Fetch PDF"
    activity_label = "Fetching and analyzing PDF"

    class Args(BaseModel):
        url: str = Field(
            description=(
                "Direct URL to a PDF file (must be publicly accessible over HTTP/HTTPS). "
                "Prefer official募集要項 or admission guideline PDFs."
            )
        )
        focus: str | None = Field(
            default=None,
            description="Optional focus area for the summary (e.g., eligibility, exam subjects).",
        )

    async def execute(self, args: Args) -> ToolResult:
        try:
            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                resp = await client.get(args.url)
                resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=f"HTTP {e.response.status_code} when fetching PDF: {args.url}",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to fetch PDF from {args.url}: {e}")

        content_type = resp.headers.get("Content-Type", "")
        if "pdf" not in content_type.lower():
            parsed = urlparse(args.url)
            if not parsed.path.lower().endswith(".pdf"):
                return ToolResult(
                    success=False,
                    error=(
                        f"URL does not appear to be a PDF (Content-Type: {content_type!r}). "
                        "Please provide a direct link to a PDF file."
                    ),
                )

        pdf_bytes = resp.content
        filename = _derive_pdf_filename(args.url, resp.headers.get("Content-Disposition", ""))

        async with async_session() as session:
            service = PdfService(session)
            try:
                upload_info = await service.save_upload(filename=filename, content=pdf_bytes)
                pdf_id = upload_info["pdf_id"]
                processed = await service.process_and_summarize(pdf_id=pdf_id, focus=args.focus)
            except Exception as e:
                return ToolResult(
                    success=False,
                    error=f"Failed to save or process PDF from {args.url}: {e}",
                )

        return ToolResult(
            success=True,
            data={
                "source_url": args.url,
                "pdf_id": processed["pdf_id"],
                "filename": filename,
                "status": processed["status"],
                "image_pages": processed.get("image_pages", []),
                "summary_markdown": processed.get("summary_markdown", ""),
            },
        )


def _derive_pdf_filename(url: str, content_disposition: str) -> str:
    filename_from_header = _parse_content_disposition_filename(content_disposition)
    if filename_from_header:
        return filename_from_header

    parsed = urlparse(url)
    path_name = os.path.basename(parsed.path)
    if path_name:
        return path_name

    return f"downloaded-{int(time.time())}.pdf"


def _parse_content_disposition_filename(content_disposition: str) -> str | None:
    if not content_disposition:
        return None

    # RFC 5987: filename*=UTF-8''encoded-name.pdf
    m = re.search(r"filename\*=([^;]+)", content_disposition, flags=re.IGNORECASE)
    if m:
        value = m.group(1).strip().strip('"')
        if "''" in value:
            _, encoded = value.split("''", 1)
            try:
                from urllib.parse import unquote

                decoded = unquote(encoded)
                if decoded:
                    return decoded
            except Exception:
                pass

    # fallback: filename="..."
    m = re.search(r"filename=\"?([^\";]+)\"?", content_disposition, flags=re.IGNORECASE)
    if m:
        name = m.group(1).strip()
        if name:
            return name

    return None
