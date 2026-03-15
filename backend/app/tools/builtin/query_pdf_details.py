from pydantic import BaseModel, Field

from app.db.engine import async_session
from app.services.pdf_service import PdfService
from app.services.request_context import get_active_pdf_ids
from app.tools.base import BaseTool, ToolResult


class QueryPdfDetailsTool(BaseTool):
    name = "query_pdf_details"
    description = (
        "Answer detailed questions about an already-processed PDF by returning "
        "relevant snippets with page citations."
    )

    class Args(BaseModel):
        question: str = Field(description="User's detailed question about the PDF content.")
        pdf_id: int | None = Field(default=None, description="Uploaded PDF id. If omitted, uses active chat PDF.")
        top_k: int = Field(default=4, description="How many snippets to retrieve.")

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
                result = await service.query_details(pdf_id=pdf_id, question=args.question, top_k=args.top_k)
            except ValueError as e:
                return ToolResult(success=False, error=str(e))
            return ToolResult(success=True, data=result)
