from app.models.provider_setting import ProviderSetting
from app.providers.base import BaseLLMProvider
from app.providers.gemini_provider import GeminiProvider
from app.providers.openai_provider import OpenAIProvider

PROVIDER_MAP: dict[str, type[BaseLLMProvider]] = {
    "openai": OpenAIProvider,
    "deepseek": OpenAIProvider,
    "gemini": GeminiProvider,
    "openai-compatible": OpenAIProvider,
}


def create_provider(setting: ProviderSetting) -> BaseLLMProvider:
    """Instantiate an LLM provider from a persisted ProviderSetting."""
    provider_cls = PROVIDER_MAP.get(setting.provider, OpenAIProvider)
    return provider_cls(
        api_key=setting.api_key,
        base_url=setting.base_url,
        model=setting.model,
    )
