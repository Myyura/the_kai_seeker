from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pdf_document import PdfChunk, PdfDocument


class PdfRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_document(self, filename: str, storage_path: str, status: str = "uploaded") -> PdfDocument:
        doc = PdfDocument(filename=filename, storage_path=storage_path, status=status)
        self.session.add(doc)
        await self.session.commit()
        await self.session.refresh(doc)
        return doc

    async def get_document(self, document_id: int, with_chunks: bool = False) -> PdfDocument | None:
        if with_chunks:
            stmt = (
                select(PdfDocument)
                .where(PdfDocument.id == document_id)
                .options(selectinload(PdfDocument.chunks))
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        return await self.session.get(PdfDocument, document_id)

    async def update_document(
        self,
        document_id: int,
        *,
        status: str | None = None,
        summary_markdown: str | None = None,
        extracted_text: str | None = None,
    ) -> PdfDocument | None:
        doc = await self.get_document(document_id)
        if doc is None:
            return None
        if status is not None:
            doc.status = status
        if summary_markdown is not None:
            doc.summary_markdown = summary_markdown
        if extracted_text is not None:
            doc.extracted_text = extracted_text
        await self.session.commit()
        await self.session.refresh(doc)
        return doc

    async def replace_chunks(self, document_id: int, chunks: list[tuple[int, str]]) -> None:
        await self.session.execute(delete(PdfChunk).where(PdfChunk.document_id == document_id))
        for page_number, content in chunks:
            self.session.add(PdfChunk(document_id=document_id, page_number=page_number, content=content))
        await self.session.commit()

    async def search_chunks(self, document_id: int) -> list[PdfChunk]:
        stmt = (
            select(PdfChunk)
            .where(PdfChunk.document_id == document_id)
            .order_by(PdfChunk.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
