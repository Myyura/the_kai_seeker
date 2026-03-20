from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.study_target import StudyTarget


class StudyTargetRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_all(
        self,
        *,
        query: str | None = None,
        limit: int = 100,
    ) -> list[StudyTarget]:
        stmt = select(StudyTarget).order_by(StudyTarget.created_at.desc(), StudyTarget.id.desc()).limit(limit)
        if query:
            stmt = stmt.where(
                StudyTarget.label.ilike(f"%{query}%")
                | StudyTarget.school_id.ilike(f"%{query}%")
                | StudyTarget.program_id.ilike(f"%{query}%")
            )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, target_id: int) -> StudyTarget | None:
        return await self.session.get(StudyTarget, target_id)

    async def delete(self, target_id: int) -> bool:
        target = await self.get_by_id(target_id)
        if target is None:
            return False
        await self.session.delete(target)
        await self.session.commit()
        return True
