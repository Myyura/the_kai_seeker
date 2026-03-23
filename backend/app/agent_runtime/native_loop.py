"""Native AgentRuntime tool loop internals."""

import asyncio
import json
import logging
import re
from typing import Any, Awaitable, Callable

from app.providers.base import BaseLLMProvider, ProviderMessage
from app.services.domain_config import domain_config
from app.tools.registry import tool_registry

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 2

TOOL_CALL_PATTERN = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


def parse_tool_call(text: str) -> dict[str, Any] | None:
    match = TOOL_CALL_PATTERN.search(text)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        logger.warning("Failed to parse tool_call JSON: %s", match.group(1))
        return None


def strip_tool_call(text: str) -> str:
    return TOOL_CALL_PATTERN.sub("", text).strip()


async def run_native_agent_loop(
    provider: BaseLLMProvider,
    messages: list[ProviderMessage],
    allowed_tool_names: set[str] | None = None,
    on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    tool_call_log: list[dict[str, Any]] = []
    max_tool_turns = domain_config.max_tool_turns

    for turn in range(max_tool_turns):
        if on_event:
            await on_event(
                {
                    "type": "status",
                    "status": "thinking",
                    "label": "Thinking",
                    "detail": "Planning the next step",
                }
            )
        response = await _chat_with_retry(provider, messages)
        text = response.content

        tool_call = parse_tool_call(text)
        if tool_call is None:
            return text, tool_call_log

        tool_name = tool_call.get("name", "")
        tool_args = tool_call.get("arguments", {})
        tool = tool_registry.get(tool_name)
        tool_display_name = tool.display_name if tool else tool_name
        tool_activity_label = tool.activity_label if tool else tool_display_name
        tool_call_id = f"tool-{turn + 1}"

        logger.info("Agent tool call [turn %d]: %s(%s)", turn + 1, tool_name, tool_args)

        if on_event:
            await on_event(
                {
                    "type": "tool.started",
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "tool_display_name": tool_display_name,
                    "tool_activity_label": tool_activity_label,
                    "args": tool_args,
                }
            )

        result = await tool_registry.execute(
            tool_name,
            allowed_names=allowed_tool_names,
            **tool_args,
        )
        result_text = result.to_text()

        log_entry = {
            "tool": tool_name,
            "tool_display_name": tool_display_name,
            "tool_activity_label": tool_activity_label,
            "tool_call_id": tool_call_id,
            "args": tool_args,
            "result": result_text,
            "success": result.success,
        }
        tool_call_log.append(log_entry)

        if on_event:
            await on_event(
                {
                    "type": "tool.finished",
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "tool_display_name": tool_display_name,
                    "tool_activity_label": tool_activity_label,
                    "args": tool_args,
                    "result": result_text,
                    "success": result.success,
                }
            )

        remaining_text = strip_tool_call(text)
        if remaining_text:
            messages.append(ProviderMessage(role="assistant", content=remaining_text))

        messages.append(
            ProviderMessage(
                role="assistant",
                content=f"<tool_call>\n{json.dumps(tool_call, ensure_ascii=False)}\n</tool_call>",
            )
        )
        messages.append(
            ProviderMessage(
                role="user",
                content=f"<tool_result>\n{result_text}\n</tool_result>",
            )
        )

    logger.warning("Agent reached max tool turns (%d)", max_tool_turns)
    final = await _chat_with_retry(provider, messages)
    return final.content, tool_call_log


async def _chat_with_retry(provider: BaseLLMProvider, messages: list[ProviderMessage]):
    for attempt in range(MAX_RETRIES):
        try:
            return await provider.chat(messages)
        except Exception as exc:
            if attempt == MAX_RETRIES - 1:
                raise
            logger.warning(
                "LLM call failed (attempt %d/%d): %s — retrying in %ds",
                attempt + 1,
                MAX_RETRIES,
                exc,
                RETRY_DELAY,
            )
            await asyncio.sleep(RETRY_DELAY)
