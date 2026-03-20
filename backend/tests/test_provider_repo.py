import pytest

from app.repositories.provider_repo import ProviderRepository
from app.schemas.provider import ProviderSettingCreate, ProviderSettingUpdate


@pytest.mark.asyncio
async def test_create_provider_deactivates_previous_active(db_session) -> None:
    repo = ProviderRepository(db_session)

    first = await repo.create(
        ProviderSettingCreate(provider="openai", api_key="first", base_url=None, model=None)
    )
    second = await repo.create(
        ProviderSettingCreate(provider="gemini", api_key="second", base_url=None, model=None)
    )

    providers = {provider.id: provider for provider in await repo.list_all()}
    active = await repo.get_active()

    assert providers[first.id].is_active is False
    assert providers[second.id].is_active is True
    assert active is not None
    assert active.id == second.id


@pytest.mark.asyncio
async def test_update_provider_activation_deactivates_other_active(db_session) -> None:
    repo = ProviderRepository(db_session)

    first = await repo.create(
        ProviderSettingCreate(provider="openai", api_key="first", base_url=None, model=None)
    )
    second = await repo.create(
        ProviderSettingCreate(provider="gemini", api_key="second", base_url=None, model=None)
    )

    updated = await repo.update(first.id, ProviderSettingUpdate(is_active=True))
    providers = {provider.id: provider for provider in await repo.list_all()}
    active = await repo.get_active()

    assert updated is not None
    assert updated.is_active is True
    assert providers[first.id].is_active is True
    assert providers[second.id].is_active is False
    assert active is not None
    assert active.id == first.id
