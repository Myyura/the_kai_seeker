"""LLM provider abstraction for The Kai Seeker (解を求める者).

This file is part of The Kai Seeker, licensed under AGPL-3.0.
Source: https://github.com/Myyura/the_kai_seeker
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class ProviderMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class ChatResponse:
    content: str
    model: str
    usage: dict | None = None


class BaseLLMProvider(ABC):
    """Abstract base class for LLM provider adapters."""

    def __init__(self, api_key: str, base_url: str | None = None, model: str | None = None):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    @abstractmethod
    async def chat(self, messages: list[ProviderMessage]) -> ChatResponse:
        """Send messages and get a complete response."""

    async def chat_json(self, messages: list[ProviderMessage]) -> ChatResponse:
        """Send messages and prefer a structured JSON response when supported."""
        return await self.chat(messages)

    @abstractmethod
    async def chat_stream(self, messages: list[ProviderMessage]) -> AsyncIterator[str]:
        """Send messages and stream the response token by token."""

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test if the provider is reachable with the given credentials."""
