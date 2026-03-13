from pydantic import BaseModel


class ProviderSettingCreate(BaseModel):
    provider: str
    api_key: str
    base_url: str | None = None
    model: str | None = None


class ProviderSettingRead(BaseModel):
    id: int
    provider: str
    base_url: str | None
    model: str | None
    is_active: bool

    model_config = {"from_attributes": True}


class ProviderSettingUpdate(BaseModel):
    provider: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    is_active: bool | None = None
