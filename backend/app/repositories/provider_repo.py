from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provider_setting import ProviderSetting
from app.schemas.provider import ProviderSettingCreate, ProviderSettingUpdate


class ProviderRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, data: ProviderSettingCreate) -> ProviderSetting:
        provider = ProviderSetting(**data.model_dump())
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

    async def update(
        self, provider_id: int, data: ProviderSettingUpdate
    ) -> ProviderSetting | None:
        provider = await self.get_by_id(provider_id)
        if provider is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
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
