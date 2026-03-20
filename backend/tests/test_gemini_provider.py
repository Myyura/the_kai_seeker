from app.providers.base import ProviderMessage
from app.providers.gemini_provider import GeminiProvider


def test_gemini_provider_concatenates_multiple_system_messages() -> None:
    provider = GeminiProvider(api_key="test-key", model="gemini-test")

    contents, system_text = provider._build_contents(
        [
            ProviderMessage(role="system", content="base system"),
            ProviderMessage(role="system", content="session state"),
            ProviderMessage(role="user", content="hello"),
            ProviderMessage(role="assistant", content="hi"),
        ]
    )

    assert system_text == "base system\n\nsession state"
    assert contents == [
        {"role": "user", "parts": [{"text": "hello"}]},
        {"role": "model", "parts": [{"text": "hi"}]},
    ]
