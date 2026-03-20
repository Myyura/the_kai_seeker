import datetime
import json
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import (
    ChatMessage,
    ChatRun,
    ChatRunEvent,
    ChatSession,
    ChatSessionPdfResource,
    ChatSessionState,
)
from app.models.pdf_document import PdfDocument


class ConversationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _timestamp_now() -> datetime.datetime:
        return datetime.datetime.now(datetime.timezone.utc)

    async def touch_session(self, session_id: int, *, commit: bool = True) -> None:
        await self.session.execute(
            update(ChatSession)
            .where(ChatSession.id == session_id)
            .values(updated_at=self._timestamp_now())
        )
        if commit:
            await self.session.commit()

    async def session_exists(self, session_id: int) -> bool:
        stmt = select(ChatSession.id).where(ChatSession.id == session_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def create_session(self, title: str = "New Chat", *, commit: bool = True) -> ChatSession:
        chat_session = ChatSession(title=title)
        chat_session.state = ChatSessionState(payload="{}")
        self.session.add(chat_session)
        await self.session.flush()
        if commit:
            await self.session.commit()
            await self.session.refresh(chat_session)
        return chat_session

    async def list_sessions(self) -> list[ChatSession]:
        stmt = select(ChatSession).order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_sessions_admin(
        self,
        *,
        query: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        message_counts = (
            select(
                ChatMessage.session_id.label("session_id"),
                func.count(ChatMessage.id).label("message_count"),
            )
            .group_by(ChatMessage.session_id)
            .subquery()
        )
        run_counts = (
            select(
                ChatRun.session_id.label("session_id"),
                func.count(ChatRun.id).label("run_count"),
            )
            .group_by(ChatRun.session_id)
            .subquery()
        )
        pdf_counts = (
            select(
                ChatSessionPdfResource.session_id.label("session_id"),
                func.count(ChatSessionPdfResource.id).label("pdf_count"),
            )
            .group_by(ChatSessionPdfResource.session_id)
            .subquery()
        )

        stmt = (
            select(
                ChatSession,
                func.coalesce(message_counts.c.message_count, 0).label("message_count"),
                func.coalesce(run_counts.c.run_count, 0).label("run_count"),
                func.coalesce(pdf_counts.c.pdf_count, 0).label("pdf_count"),
            )
            .outerjoin(message_counts, message_counts.c.session_id == ChatSession.id)
            .outerjoin(run_counts, run_counts.c.session_id == ChatSession.id)
            .outerjoin(pdf_counts, pdf_counts.c.session_id == ChatSession.id)
            .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
            .limit(limit)
        )
        if query:
            stmt = stmt.where(ChatSession.title.ilike(f"%{query}%"))

        result = await self.session.execute(stmt)
        rows = result.all()
        return [
            {
                "id": chat_session.id,
                "title": chat_session.title,
                "message_count": int(message_count or 0),
                "run_count": int(run_count or 0),
                "pdf_count": int(pdf_count or 0),
                "created_at": chat_session.created_at,
                "updated_at": chat_session.updated_at,
            }
            for chat_session, message_count, run_count, pdf_count in rows
        ]

    async def get_session(self, session_id: int) -> ChatSession | None:
        stmt = (
            select(ChatSession)
            .where(ChatSession.id == session_id)
            .options(
                selectinload(ChatSession.messages),
                selectinload(ChatSession.pdf_resources),
                selectinload(ChatSession.runs).selectinload(ChatRun.events),
                selectinload(ChatSession.state),
            )
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
        self,
        session_id: int,
        role: str,
        content: str,
        model: str | None = None,
        *,
        commit: bool = True,
        touch_session: bool = True,
    ) -> ChatMessage:
        msg = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            model=model,
        )
        self.session.add(msg)
        if touch_session:
            await self.touch_session(session_id, commit=False)
        await self.session.flush()
        if commit:
            await self.session.commit()
            await self.session.refresh(msg)
        return msg

    async def add_messages_bulk(
        self,
        session_id: int,
        messages: list[dict[str, Any]],
        *,
        commit: bool = True,
        touch_session: bool = True,
    ) -> list[ChatMessage]:
        created = [
            ChatMessage(
                session_id=session_id,
                role=message["role"],
                content=message["content"],
                model=message.get("model"),
            )
            for message in messages
        ]
        if not created:
            return []

        self.session.add_all(created)
        if touch_session:
            await self.touch_session(session_id, commit=False)
        await self.session.flush()
        if commit:
            await self.session.commit()
            for message in created:
                await self.session.refresh(message)
        return created

    async def get_messages(self, session_id: int) -> list[ChatMessage]:
        stmt = (
            select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_run(
        self,
        session_id: int,
        status: str = "running",
        *,
        commit: bool = True,
        touch_session: bool = True,
    ) -> ChatRun:
        run = ChatRun(session_id=session_id, status=status)
        self.session.add(run)
        if touch_session:
            await self.touch_session(session_id, commit=False)
        await self.session.flush()
        if commit:
            await self.session.commit()
            await self.session.refresh(run)
        return run

    async def add_run_event(
        self,
        run_id: int,
        sequence: int,
        event_type: str,
        payload: dict,
        *,
        commit: bool = True,
    ) -> ChatRunEvent:
        event = ChatRunEvent(
            run_id=run_id,
            sequence=sequence,
            event_type=event_type,
            payload=json.dumps(payload, ensure_ascii=False),
        )
        self.session.add(event)
        await self.session.flush()
        if commit:
            await self.session.commit()
            await self.session.refresh(event)
        return event

    async def add_run_events_bulk(
        self,
        run_id: int,
        events: list[dict[str, Any]],
        *,
        commit: bool = True,
    ) -> list[ChatRunEvent]:
        created = [
            ChatRunEvent(
                run_id=run_id,
                sequence=event["sequence"],
                event_type=event["event_type"],
                payload=json.dumps(event["payload"], ensure_ascii=False),
            )
            for event in events
        ]
        if not created:
            return []

        self.session.add_all(created)
        await self.session.flush()
        if commit:
            await self.session.commit()
        return created

    async def update_run(
        self,
        run_id: int,
        *,
        status: str | None = None,
        assistant_message_id: int | None = None,
        commit: bool = True,
        touch_session: bool = True,
    ) -> ChatRun | None:
        run = await self.session.get(ChatRun, run_id)
        if run is None:
            return None
        if status is not None:
            run.status = status
        if assistant_message_id is not None:
            run.assistant_message_id = assistant_message_id
        if touch_session:
            await self.touch_session(run.session_id, commit=False)
        await self.session.flush()
        if commit:
            await self.session.commit()
            await self.session.refresh(run)
        return run

    async def attach_pdf_resource(
        self,
        session_id: int,
        pdf_id: int,
        *,
        source_type: str = "uploaded",
        source_url: str | None = None,
        commit: bool = True,
        touch_session: bool = True,
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
            if touch_session:
                await self.touch_session(session_id, commit=False)
            await self.session.flush()
            if commit:
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
        if touch_session:
            await self.touch_session(session_id, commit=False)
        await self.session.flush()
        if commit:
            await self.session.commit()
            await self.session.refresh(resource)
        return resource

    async def attach_pdf_resources_bulk(
        self,
        session_id: int,
        resources: list[dict[str, Any]],
        *,
        commit: bool = True,
        touch_session: bool = True,
    ) -> list[ChatSessionPdfResource]:
        if not resources:
            return []

        normalized: list[dict[str, Any]] = []
        seen_pdf_ids: set[int] = set()
        for resource in resources:
            pdf_id = resource["pdf_id"]
            if pdf_id in seen_pdf_ids:
                continue
            seen_pdf_ids.add(pdf_id)
            normalized.append(resource)

        stmt = select(ChatSessionPdfResource).where(
            ChatSessionPdfResource.session_id == session_id,
            ChatSessionPdfResource.pdf_id.in_([resource["pdf_id"] for resource in normalized]),
        )
        existing_rows = (await self.session.execute(stmt)).scalars().all()
        existing_by_pdf_id = {resource.pdf_id: resource for resource in existing_rows}

        results: list[ChatSessionPdfResource] = []
        new_rows: list[ChatSessionPdfResource] = []
        for resource in normalized:
            existing = existing_by_pdf_id.get(resource["pdf_id"])
            if existing is not None:
                if resource.get("source_type") == "fetched" and existing.source_type != "fetched":
                    existing.source_type = "fetched"
                source_url = resource.get("source_url")
                if source_url and not existing.source_url:
                    existing.source_url = source_url
                results.append(existing)
                continue

            row = ChatSessionPdfResource(
                session_id=session_id,
                pdf_id=resource["pdf_id"],
                source_type=resource.get("source_type", "uploaded"),
                source_url=resource.get("source_url"),
            )
            new_rows.append(row)
            results.append(row)

        if new_rows:
            self.session.add_all(new_rows)
        if touch_session:
            await self.touch_session(session_id, commit=False)
        await self.session.flush()
        if commit:
            await self.session.commit()
        return results

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

    async def get_or_create_session_state(
        self,
        session_id: int,
        *,
        commit: bool = True,
    ) -> ChatSessionState:
        stmt = select(ChatSessionState).where(ChatSessionState.session_id == session_id)
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            return existing

        state = ChatSessionState(session_id=session_id, payload="{}")
        self.session.add(state)
        await self.session.flush()
        if commit:
            await self.session.commit()
            await self.session.refresh(state)
        return state

    async def update_session_state(
        self,
        session_id: int,
        payload: str,
        *,
        commit: bool = True,
        touch_session: bool = True,
    ) -> ChatSessionState:
        state = await self.get_or_create_session_state(session_id, commit=False)
        state.payload = payload
        if touch_session:
            await self.touch_session(session_id, commit=False)
        await self.session.flush()
        if commit:
            await self.session.commit()
            await self.session.refresh(state)
        return state
