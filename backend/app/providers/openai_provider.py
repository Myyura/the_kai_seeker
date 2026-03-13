import json
import logging
from typing import AsyncIterator

import httpx

from app.providers.base import BaseLLMProvider, ChatMessage, ChatResponse

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIProvider(BaseLLMProvider):
    """OpenAI-compatible LLM provider. Works with OpenAI, DeepSeek, local proxies, etc."""

    def __init__(self, api_key: str, base_url: str | None = None, model: str | None = None):
        super().__init__(api_key, base_url, model)
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or DEFAULT_MODEL

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_body(self, messages: list[ChatMessage], stream: bool = False) -> dict:
        return {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": stream,
        }

    async def chat(self, messages: list[ChatMessage]) -> ChatResponse:
        url = f"{self.base_url}/chat/completions"
        body = self._build_body(messages, stream=False)

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, headers=self._headers(), json=body)
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        return ChatResponse(
            content=choice["message"]["content"],
            model=data.get("model", self.model),
            usage=data.get("usage"),
        )

    async def chat_stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        url = f"{self.base_url}/chat/completions"
        body = self._build_body(messages, stream=True)

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST", url, headers=self._headers(), json=body
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        payload = line[6:]
                        if payload.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(payload)
                            delta = chunk["choices"][0].get("delta", {})
                            token = delta.get("content")
                            if token:
                                yield token
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except httpx.HTTPStatusError:
            logger.warning("Streaming not supported by provider, falling back to non-stream")
            response = await self.chat(messages)
            yield response.content

    async def test_connection(self) -> bool:
        try:
            test_messages = [ChatMessage(role="user", content="Hi")]
            response = await self.chat(test_messages)
            return bool(response.content)
        except Exception:
            logger.exception("Provider connection test failed")
            return False
