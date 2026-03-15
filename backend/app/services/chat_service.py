"""Chat orchestration service for The Kai Seeker (解を求める者).

This file is part of The Kai Seeker, licensed under AGPL-3.0.
Source: https://github.com/Myyura/the_kai_seeker
"""

import json
import logging
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.providers.base import ChatMessage
from app.providers.factory import create_provider
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.provider_repo import ProviderRepository
from app.schemas.chat import ChatMessageIn
from app.services.agent import build_system_prompt, run_agent_loop
from app.services.request_context import set_active_pdf_ids

logger = logging.getLogger(__name__)

MAX_TITLE_LENGTH = 60


class ChatService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.provider_repo = ProviderRepository(session)
        self.conversation_repo = ConversationRepository(session)

    async def _get_provider(self):
        setting = await self.provider_repo.get_active()
        if setting is None:
            raise ValueError("No active LLM provider configured. Please add one in Settings.")
        return create_provider(setting)

    def _build_messages(self, user_messages: list[ChatMessageIn], pdf_ids: list[int] | None = None) -> list[ChatMessage]:
        last_user_text = user_messages[-1].content if user_messages else ""
        system_prompt = build_system_prompt(user_message=last_user_text)
        if pdf_ids:
            system_prompt += (
                "\n\n## Active Uploaded PDFs\n"
                f"Use these pdf_ids when calling PDF tools: {pdf_ids}. "
                "If the user asks about the uploaded document and does not specify one, use the first id."
            )
        messages = [ChatMessage(role="system", content=system_prompt)]
        for m in user_messages:
            messages.append(ChatMessage(role=m.role, content=m.content))
        return messages

    async def _ensure_session(self, session_id: int | None, first_message: str) -> int:
        if session_id is not None:
            existing = await self.conversation_repo.get_session(session_id)
            if existing is not None:
                return existing.id

        title = first_message[:MAX_TITLE_LENGTH].strip()
        if len(first_message) > MAX_TITLE_LENGTH:
            title += "…"
        chat_session = await self.conversation_repo.create_session(title=title)
        return chat_session.id

    async def chat(
        self,
        user_messages: list[ChatMessageIn],
        session_id: int | None = None,
        pdf_ids: list[int] | None = None,
    ) -> tuple[str, str | None, int, list[dict]]:
        """Returns (content, model_name, session_id, tool_call_log)."""
        sid = await self._ensure_session(
            session_id, user_messages[-1].content if user_messages else "New Chat"
        )

        last_user_msg = user_messages[-1] if user_messages else None
        if last_user_msg:
            await self.conversation_repo.add_message(sid, last_user_msg.role, last_user_msg.content)

        provider = await self._get_provider()
        messages = self._build_messages(user_messages, pdf_ids=pdf_ids)

        with set_active_pdf_ids(pdf_ids or []):
            final_answer, tool_call_log = await run_agent_loop(provider, messages)

        await self.conversation_repo.add_message(sid, "assistant", final_answer)

        return final_answer, provider.model, sid, tool_call_log

    async def chat_stream(
        self,
        user_messages: list[ChatMessageIn],
        session_id: int | None = None,
        pdf_ids: list[int] | None = None,
    ) -> tuple[AsyncIterator[dict], int]:
        """Returns (event_iterator, session_id).

        Each yielded event is a dict, one of:
        - {"tool_call": name, "args": {...}}
        - {"tool_result": name, "result": "..."}
        - {"token": "..."}
        """
        sid = await self._ensure_session(
            session_id, user_messages[-1].content if user_messages else "New Chat"
        )

        last_user_msg = user_messages[-1] if user_messages else None
        if last_user_msg:
            await self.conversation_repo.add_message(sid, last_user_msg.role, last_user_msg.content)

        provider = await self._get_provider()
        messages = self._build_messages(user_messages, pdf_ids=pdf_ids)

        async def _generate() -> AsyncIterator[dict]:
            tool_events: list[dict] = []

            async def on_tool_call(name: str, args: dict, result: str) -> None:
                tool_events.append({"tool_call": name, "args": args})
                tool_events.append({"tool_result": name, "result": result[:500]})

            with set_active_pdf_ids(pdf_ids or []):
                final_answer, _ = await run_agent_loop(
                    provider, messages, on_tool_call=on_tool_call
                )

            for event in tool_events:
                yield event

            await self.conversation_repo.add_message(sid, "assistant", final_answer)

            for chunk in _chunk_text(final_answer, 20):
                yield {"token": chunk}

        return _generate(), sid


def _chunk_text(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]
