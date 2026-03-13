import json
import logging
from typing import AsyncIterator

import httpx

from app.providers.base import BaseLLMProvider, ChatMessage, ChatResponse

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-2.5-flash"

ROLE_MAP = {"system": "user", "user": "user", "assistant": "model"}


class GeminiProvider(BaseLLMProvider):
    """Native Google Gemini API provider."""

    def __init__(self, api_key: str, base_url: str | None = None, model: str | None = None):
        super().__init__(api_key, base_url, model)
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or DEFAULT_MODEL

    def _build_contents(self, messages: list[ChatMessage]) -> tuple[list[dict], str | None]:
        """Convert ChatMessages into Gemini contents format.

        Returns (contents, system_instruction_text).
        Gemini uses 'user'/'model' roles and handles system instructions separately.
        """
        system_text = None
        contents: list[dict] = []

        for m in messages:
            if m.role == "system":
                system_text = m.content
                continue
            role = ROLE_MAP.get(m.role, "user")
            contents.append({
                "role": role,
                "parts": [{"text": m.content}],
            })

        return contents, system_text

    def _build_body(self, messages: list[ChatMessage]) -> dict:
        contents, system_text = self._build_contents(messages)
        body: dict = {"contents": contents}
        if system_text:
            body["systemInstruction"] = {"parts": [{"text": system_text}]}
        return body

    async def chat(self, messages: list[ChatMessage]) -> ChatResponse:
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        body = self._build_body(messages)

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                url,
                headers={"Content-Type": "application/json"},
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        candidate = data["candidates"][0]
        text = candidate["content"]["parts"][0]["text"]
        usage = data.get("usageMetadata")

        return ChatResponse(
            content=text,
            model=data.get("modelVersion", self.model),
            usage=usage,
        )

    async def chat_stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        url = (
            f"{self.base_url}/models/{self.model}:streamGenerateContent"
            f"?alt=sse&key={self.api_key}"
        )
        body = self._build_body(messages)

        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                url,
                headers={"Content-Type": "application/json"},
                json=body,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    try:
                        chunk = json.loads(payload)
                        candidates = chunk.get("candidates", [])
                        if not candidates:
                            continue
                        parts = candidates[0].get("content", {}).get("parts", [])
                        for part in parts:
                            token = part.get("text")
                            if token:
                                yield token
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    async def test_connection(self) -> bool:
        try:
            test_messages = [ChatMessage(role="user", content="Hi")]
            response = await self.chat(test_messages)
            return bool(response.content)
        except Exception:
            logger.exception("Gemini connection test failed")
            return False
