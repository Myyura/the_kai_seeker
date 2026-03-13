from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session
from app.providers.factory import create_provider
from app.repositories.provider_repo import ProviderRepository
from app.schemas.provider import ProviderSettingCreate, ProviderSettingRead, ProviderSettingUpdate

router = APIRouter()


@router.post("/", response_model=ProviderSettingRead, status_code=201)
async def create_provider_setting(
    data: ProviderSettingCreate,
    session: AsyncSession = Depends(get_session),
) -> ProviderSettingRead:
    repo = ProviderRepository(session)
    provider = await repo.create(data)
    return ProviderSettingRead.model_validate(provider)


@router.get("/", response_model=list[ProviderSettingRead])
async def list_providers(
    session: AsyncSession = Depends(get_session),
) -> list[ProviderSettingRead]:
    repo = ProviderRepository(session)
    providers = await repo.list_all()
    return [ProviderSettingRead.model_validate(p) for p in providers]


@router.get("/active", response_model=ProviderSettingRead | None)
async def get_active_provider(
    session: AsyncSession = Depends(get_session),
) -> ProviderSettingRead | None:
    repo = ProviderRepository(session)
    provider = await repo.get_active()
    if provider is None:
        return None
    return ProviderSettingRead.model_validate(provider)


@router.get("/{provider_id}", response_model=ProviderSettingRead)
async def get_provider(
    provider_id: int,
    session: AsyncSession = Depends(get_session),
) -> ProviderSettingRead:
    repo = ProviderRepository(session)
    provider = await repo.get_by_id(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    return ProviderSettingRead.model_validate(provider)


@router.patch("/{provider_id}", response_model=ProviderSettingRead)
async def update_provider(
    provider_id: int,
    data: ProviderSettingUpdate,
    session: AsyncSession = Depends(get_session),
) -> ProviderSettingRead:
    repo = ProviderRepository(session)
    provider = await repo.update(provider_id, data)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    return ProviderSettingRead.model_validate(provider)


@router.delete("/{provider_id}", status_code=204)
async def delete_provider(
    provider_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    repo = ProviderRepository(session)
    deleted = await repo.delete(provider_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Provider not found")


@router.post("/{provider_id}/test")
async def test_provider(
    provider_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    repo = ProviderRepository(session)
    setting = await repo.get_by_id(provider_id)
    if setting is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    provider = create_provider(setting)
    ok = await provider.test_connection()
    return {"success": ok}
