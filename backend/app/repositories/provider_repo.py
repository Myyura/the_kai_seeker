from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provider_setting import ProviderSetting
from app.schemas.provider import ProviderSettingCreate, ProviderSettingUpdate


class ProviderRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _deactivate_other_active(self, *, exclude_id: int | None = None) -> None:
        stmt = update(ProviderSetting).where(ProviderSetting.is_active.is_(True))
        if exclude_id is not None:
            stmt = stmt.where(ProviderSetting.id != exclude_id)
        await self.session.execute(stmt.values(is_active=False))

    async def create(self, data: ProviderSettingCreate) -> ProviderSetting:
        await self._deactivate_other_active()
        provider = ProviderSetting(**data.model_dump(), is_active=True)
        self.session.add(provider)
        await self.session.commit()
        await self.session.refresh(provider)
        return provider

    async def get_by_id(self, provider_id: int) -> ProviderSetting | None:
        return await self.session.get(ProviderSetting, provider_id)

    async def get_active(self) -> ProviderSetting | None:
        stmt = (
            select(ProviderSetting)
            .where(ProviderSetting.is_active.is_(True))
            .order_by(ProviderSetting.updated_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self) -> list[ProviderSetting]:
        stmt = select(ProviderSetting).order_by(ProviderSetting.updated_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_admin(
        self,
        *,
        query: str | None = None,
        limit: int = 100,
    ) -> list[ProviderSetting]:
        stmt = (
            select(ProviderSetting)
            .order_by(ProviderSetting.updated_at.desc(), ProviderSetting.id.desc())
            .limit(limit)
        )
        if query:
            stmt = stmt.where(
                ProviderSetting.provider.ilike(f"%{query}%")
                | ProviderSetting.model.ilike(f"%{query}%")
                | ProviderSetting.base_url.ilike(f"%{query}%")
            )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self, provider_id: int, data: ProviderSettingUpdate
    ) -> ProviderSetting | None:
        provider = await self.get_by_id(provider_id)
        if provider is None:
            return None
        updates = data.model_dump(exclude_unset=True)
        make_active = updates.pop("is_active", None)
        if make_active is True:
            await self._deactivate_other_active(exclude_id=provider_id)
            provider.is_active = True
        elif make_active is False:
            provider.is_active = False

        for field, value in updates.items():
            setattr(provider, field, value)
        await self.session.commit()
        await self.session.refresh(provider)
        return provider

    async def delete(self, provider_id: int) -> bool:
        provider = await self.get_by_id(provider_id)
        if provider is None:
            return False
        await self.session.delete(provider)
        await self.session.commit()
        return True
