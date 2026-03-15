from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session
from app.schemas.pdf import PdfProcessOut, PdfProcessRequest, PdfQueryOut, PdfQueryRequest
from app.services.pdf_service import PdfService

router = APIRouter()


@router.post("/process", response_model=PdfProcessOut)
async def process_pdf(
    req: PdfProcessRequest,
    session: AsyncSession = Depends(get_session),
) -> PdfProcessOut:
    try:
        result = await PdfService(session).process_and_summarize(req.pdf_id, req.focus)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return PdfProcessOut.model_validate(result)


@router.post("/query", response_model=PdfQueryOut)
async def query_pdf(
    req: PdfQueryRequest,
    session: AsyncSession = Depends(get_session),
) -> PdfQueryOut:
    try:
        result = await PdfService(session).query_details(req.pdf_id, req.question, req.top_k)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return PdfQueryOut.model_validate(result)
