from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import ChatSession, ChatSessionPdfResource
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

    async def list_documents(
        self,
        *,
        query: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        chunk_counts = (
            select(
                PdfChunk.document_id.label("pdf_id"),
                func.count(PdfChunk.id).label("chunk_count"),
            )
            .group_by(PdfChunk.document_id)
            .subquery()
        )
        reference_counts = (
            select(
                ChatSessionPdfResource.pdf_id.label("pdf_id"),
                func.count(func.distinct(ChatSessionPdfResource.session_id)).label(
                    "referenced_session_count"
                ),
            )
            .group_by(ChatSessionPdfResource.pdf_id)
            .subquery()
        )

        stmt = (
            select(
                PdfDocument,
                func.coalesce(chunk_counts.c.chunk_count, 0).label("chunk_count"),
                func.coalesce(
                    reference_counts.c.referenced_session_count, 0
                ).label("referenced_session_count"),
            )
            .outerjoin(chunk_counts, chunk_counts.c.pdf_id == PdfDocument.id)
            .outerjoin(reference_counts, reference_counts.c.pdf_id == PdfDocument.id)
            .order_by(PdfDocument.updated_at.desc(), PdfDocument.id.desc())
            .limit(limit)
        )

        if query:
            stmt = stmt.where(PdfDocument.filename.ilike(f"%{query}%"))
        if status:
            stmt = stmt.where(PdfDocument.status == status)

        result = await self.session.execute(stmt)
        rows = result.all()
        return [
            {
                "id": doc.id,
                "filename": doc.filename,
                "status": doc.status,
                "summary_available": bool(doc.summary_markdown),
                "extracted_text_length": len(doc.extracted_text or ""),
                "chunk_count": int(chunk_count or 0),
                "referenced_session_count": int(referenced_session_count or 0),
                "created_at": doc.created_at,
                "updated_at": doc.updated_at,
            }
            for doc, chunk_count, referenced_session_count in rows
        ]

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

    async def list_document_references(self, document_id: int) -> list[dict]:
        stmt = (
            select(ChatSessionPdfResource, ChatSession)
            .join(ChatSession, ChatSession.id == ChatSessionPdfResource.session_id)
            .where(ChatSessionPdfResource.pdf_id == document_id)
            .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        return [
            {
                "session_id": session.id,
                "session_title": session.title,
                "source_type": resource.source_type,
                "source_url": resource.source_url,
                "attached_at": resource.created_at,
            }
            for resource, session in rows
        ]

    async def delete_document(self, document_id: int) -> bool:
        doc = await self.get_document(document_id)
        if doc is None:
            return False
        await self.session.delete(doc)
        await self.session.commit()
        return True
