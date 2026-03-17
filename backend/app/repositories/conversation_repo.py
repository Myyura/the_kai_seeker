from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import ChatMessage, ChatSession, ChatSessionPdfResource
from app.models.pdf_document import PdfDocument


class ConversationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_session(self, title: str = "New Chat") -> ChatSession:
        chat_session = ChatSession(title=title)
        self.session.add(chat_session)
        await self.session.commit()
        await self.session.refresh(chat_session)
        return chat_session

    async def list_sessions(self) -> list[ChatSession]:
        stmt = select(ChatSession).order_by(ChatSession.updated_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_session(self, session_id: int) -> ChatSession | None:
        stmt = (
            select(ChatSession)
            .where(ChatSession.id == session_id)
            .options(selectinload(ChatSession.messages))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_session_title(self, session_id: int, title: str) -> ChatSession | None:
        chat_session = await self.session.get(ChatSession, session_id)
        if chat_session is None:
            return None
        chat_session.title = title
        await self.session.commit()
        await self.session.refresh(chat_session)
        return chat_session

    async def delete_session(self, session_id: int) -> bool:
        chat_session = await self.session.get(ChatSession, session_id)
        if chat_session is None:
            return False
        await self.session.delete(chat_session)
        await self.session.commit()
        return True

    async def add_message(
        self, session_id: int, role: str, content: str, model: str | None = None
    ) -> ChatMessage:
        msg = ChatMessage(session_id=session_id, role=role, content=content, model=model)
        self.session.add(msg)
        await self.session.commit()
        await self.session.refresh(msg)
        return msg

    async def get_messages(self, session_id: int) -> list[ChatMessage]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def attach_pdf_resource(
        self,
        session_id: int,
        pdf_id: int,
        *,
        source_type: str = "uploaded",
        source_url: str | None = None,
    ) -> ChatSessionPdfResource:
        stmt = select(ChatSessionPdfResource).where(
            ChatSessionPdfResource.session_id == session_id,
            ChatSessionPdfResource.pdf_id == pdf_id,
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing:
            if source_type == "fetched" and existing.source_type != "fetched":
                existing.source_type = "fetched"
            if source_url and not existing.source_url:
                existing.source_url = source_url
            await self.session.commit()
            await self.session.refresh(existing)
            return existing

        resource = ChatSessionPdfResource(
            session_id=session_id,
            pdf_id=pdf_id,
            source_type=source_type,
            source_url=source_url,
        )
        self.session.add(resource)
        await self.session.commit()
        await self.session.refresh(resource)
        return resource

    async def list_session_pdf_resources(self, session_id: int) -> list[dict]:
        stmt = (
            select(ChatSessionPdfResource, PdfDocument)
            .join(PdfDocument, PdfDocument.id == ChatSessionPdfResource.pdf_id)
            .where(ChatSessionPdfResource.session_id == session_id)
            .order_by(ChatSessionPdfResource.created_at.asc())
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        return [
            {
                "pdf_id": doc.id,
                "filename": doc.filename,
                "status": doc.status,
                "source": res.source_type,
                "source_url": res.source_url,
            }
            for res, doc in rows
        ]
