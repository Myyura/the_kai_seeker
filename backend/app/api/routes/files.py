import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session
from app.schemas.pdf import PdfUploadOut
from app.services.pdf_service import PdfService

router = APIRouter()

MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20MB
ALLOWED_CONTENT_TYPES = {"application/pdf", "application/octet-stream", ""}


@router.post("/upload", response_model=PdfUploadOut)
async def upload_pdf(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> PdfUploadOut:
    content_type = (file.content_type or "").strip().lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="PDF file is too large (max 20MB)")

    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Invalid PDF file signature")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    safe_name = os.path.basename(file.filename)
    result = await PdfService(session).save_upload(safe_name, content)
    return PdfUploadOut.model_validate(result)
