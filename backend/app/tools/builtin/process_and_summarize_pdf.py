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
        pdf_id: int | None = Field(default=None, description="Uploaded PDF id. If omitted, uses active chat PDF.")
        focus: str | None = Field(default=None, description="Optional focus area for summary.")

    async def execute(self, args: Args) -> ToolResult:
        pdf_id = args.pdf_id
        if pdf_id is None:
            active = get_active_pdf_ids()
            if active:
                pdf_id = active[0]

        if pdf_id is None:
            return ToolResult(
                success=False,
                error="Missing pdf_id. Please upload a PDF first or pass pdf_id explicitly.",
            )

        async with async_session() as session:
            service = PdfService(session)
            try:
                result = await service.process_and_summarize(pdf_id=pdf_id, focus=args.focus)
            except ValueError as e:
                return ToolResult(success=False, error=str(e))
            return ToolResult(success=True, data=result)
