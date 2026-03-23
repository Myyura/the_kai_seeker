import json

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.long_term_memory import LongTermMemoryRecord


class LongTermMemoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_active(
        self,
        *,
        memory_types: list[str] | None = None,
        related_target_id: int | None = None,
        limit: int = 100,
    ) -> list[LongTermMemoryRecord]:
        stmt = (
            select(LongTermMemoryRecord)
            .where(LongTermMemoryRecord.status == "active")
            .order_by(
                LongTermMemoryRecord.importance.desc(),
                LongTermMemoryRecord.updated_at.desc(),
                LongTermMemoryRecord.id.desc(),
            )
            .limit(limit)
        )
        if memory_types:
            stmt = stmt.where(LongTermMemoryRecord.memory_type.in_(memory_types))
        if related_target_id is not None:
            stmt = stmt.where(LongTermMemoryRecord.related_target_id == related_target_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_memory_pack(
        self,
        *,
        session_id: int,
        related_target_ids: list[int] | None = None,
        limit: int = 100,
    ) -> list[LongTermMemoryRecord]:
        session_scope = f"session:{session_id}"
        target_ids = [target_id for target_id in (related_target_ids or []) if target_id is not None]

        scope_filters = [
            LongTermMemoryRecord.scope == "global",
            LongTermMemoryRecord.scope == session_scope,
        ]
        if target_ids:
            scope_filters.append(LongTermMemoryRecord.related_target_id.in_(target_ids))
            scope_filters.append(
                LongTermMemoryRecord.scope.in_([f"target:{target_id}" for target_id in target_ids])
            )

        stmt = (
            select(LongTermMemoryRecord)
            .where(LongTermMemoryRecord.status == "active")
            .where(or_(*scope_filters))
            .order_by(
                LongTermMemoryRecord.importance.desc(),
                LongTermMemoryRecord.updated_at.desc(),
                LongTermMemoryRecord.id.desc(),
            )
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add_record(
        self,
        *,
        memory_type: str,
        scope: str,
        content: str,
        summary: str | None = None,
        importance: float = 0.5,
        confidence: float = 0.5,
        source_session_id: int | None = None,
        source_run_id: int | None = None,
        related_target_id: int | None = None,
        tags: list[str] | None = None,
        status: str = "active",
        commit: bool = True,
    ) -> LongTermMemoryRecord:
        record = LongTermMemoryRecord(
            memory_type=memory_type,
            scope=scope,
            content=content,
            summary=summary,
            importance=importance,
            confidence=confidence,
            source_session_id=source_session_id,
            source_run_id=source_run_id,
            related_target_id=related_target_id,
            tags=json.dumps(tags or [], ensure_ascii=False),
            status=status,
        )
        self.session.add(record)
        await self.session.flush()
        if commit:
            await self.session.commit()
            await self.session.refresh(record)
        return record

    async def list_by_source_session(
        self,
        session_id: int,
        *,
        limit: int = 100,
    ) -> list[LongTermMemoryRecord]:
        stmt = (
            select(LongTermMemoryRecord)
            .where(LongTermMemoryRecord.source_session_id == session_id)
            .order_by(
                LongTermMemoryRecord.updated_at.desc(),
                LongTermMemoryRecord.id.desc(),
            )
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_for_session(
        self,
        session_id: int,
        *,
        commit: bool = True,
    ) -> int:
        result = await self.session.execute(
            delete(LongTermMemoryRecord).where(
                or_(
                    LongTermMemoryRecord.source_session_id == session_id,
                    LongTermMemoryRecord.scope == f"session:{session_id}",
                )
            )
        )
        deleted = int(result.rowcount or 0)
        if commit:
            await self.session.commit()
        return deleted
