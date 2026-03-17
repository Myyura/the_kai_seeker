from pydantic import BaseModel, Field

from app.db.engine import async_session
from app.services.pdf_service import PdfService
from app.services.request_context import get_active_pdf_ids
from app.tools.base import BaseTool, ToolResult


class ProcessAndSummarizePdfTool(BaseTool):
    name = "process_and_summarize_pdf"
    description = (
        "Process an uploaded PDF end-to-end (text extraction, image-page OCR if needed) "
        "and return a structured markdown summary."
    )

    class Args(BaseModel):
        pdf_id: int | None = Field(
            default=None,
            description=(
                "Uploaded PDF id. If omitted, will run on all active chat PDFs "
                "(or the single active PDF if only one is provided)."
            ),
        )
        focus: str | None = Field(default=None, description="Optional focus area for summary.")

    async def execute(self, args: Args) -> ToolResult:
        # Explicit pdf_id: process just that one
        if args.pdf_id is not None:
            async with async_session() as session:
                service = PdfService(session)
                try:
                    result = await service.process_and_summarize(pdf_id=args.pdf_id, focus=args.focus)
                except ValueError as e:
                    return ToolResult(success=False, error=str(e))
                return ToolResult(success=True, data=result)

        # No explicit id: use all active PDFs in the current chat context
        active_ids = get_active_pdf_ids()
        if not active_ids:
            return ToolResult(
                success=False,
                error="Missing pdf_id. Please upload at least one PDF first or pass pdf_id explicitly.",
            )

        async with async_session() as session:
            service = PdfService(session)
            results: list[dict] = []
            for pid in active_ids:
                try:
                    res = await service.process_and_summarize(pdf_id=pid, focus=args.focus)
                except ValueError as e:
                    # Skip missing/invalid PDFs but record the error message
                    results.append({"pdf_id": pid, "error": str(e)})
                else:
                    results.append(res)

        return ToolResult(success=True, data={"results": results})
