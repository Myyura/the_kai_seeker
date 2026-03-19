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
    display_name = "Query PDF"
    activity_label = "Searching PDF details"

    class Args(BaseModel):
        question: str = Field(description="User's detailed question about the PDF content.")
        pdf_id: int | None = Field(
            default=None,
            description=(
                "Uploaded PDF id. If omitted, will query across all active chat PDFs "
                "(or the single active PDF if only one is provided)."
            ),
        )
        top_k: int = Field(default=4, description="How many snippets to retrieve.")

    async def execute(self, args: Args) -> ToolResult:
        # Explicit pdf_id: query just that one
        if args.pdf_id is not None:
            async with async_session() as session:
                service = PdfService(session)
                try:
                    result = await service.query_details(
                        pdf_id=args.pdf_id,
                        question=args.question,
                        top_k=args.top_k,
                    )
                except ValueError as e:
                    return ToolResult(success=False, error=str(e))
                return ToolResult(success=True, data=result)

        # No explicit id: query across all active PDFs in the current chat context
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
                    res = await service.query_details(
                        pdf_id=pid,
                        question=args.question,
                        top_k=args.top_k,
                    )
                except ValueError as e:
                    # Skip missing/invalid PDFs but record the error message
                    results.append({"pdf_id": pid, "error": str(e)})
                else:
                    results.append(res)

        return ToolResult(success=True, data={"results": results})
