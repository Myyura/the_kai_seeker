"""Agent dispatcher for The Kai Seeker (解を求める者).

Orchestrates the LLM ↔ Tool calling loop using a provider-agnostic approach:
- Tool/Skill schemas are injected into the system prompt
- LLM is instructed to emit <tool_call> blocks when it needs a tool
- Agent parses tool calls, executes them, and feeds results back
- Loop continues until LLM produces a final text answer (max N turns)

This file is part of The Kai Seeker, licensed under AGPL-3.0.
Source: https://github.com/Myyura/the_kai_seeker
"""

import asyncio
import json
import logging
import re
from typing import Any, Awaitable, Callable

from app.config.agent_policy import build_tool_policy
from app.providers.base import BaseLLMProvider, ProviderMessage
from app.services.domain_config import domain_config
from app.skills.base import Skill
from app.skills.registry import skill_registry
from app.tools.registry import tool_registry

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

TOOL_CALL_PATTERN = re.compile(
    r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
    re.DOTALL,
)


def _build_base_prompt() -> str:
    """Assemble the base system prompt dynamically from the domain config."""
    dc = domain_config

    agent_label = f'"{dc.agent_name}" ({dc.agent_name_ja})'
    lang_list = ", ".join(dc.languages)

    role_lines = "\n".join(f"- {r}" for r in dc.role_description) if dc.role_description else ""

    kb = dc.knowledge_base
    kb_section = ""
    if kb.get("name"):
        kb_section = (
            f"\nYou have access to a content database from {kb['name']}"
            + (f" ({kb['url']})" if kb.get("url") else "")
            + (f", {kb['description']}" if kb.get("description") else "")
            + ". When users ask about specific content, use the search tools to find accurate "
            "information rather than relying on your training data."
        )

    workflow = ""
    if dc.workflow_hints:
        steps = "\n".join(f"{i+1}. {h}" for i, h in enumerate(dc.workflow_hints))
        workflow = f"\n\nTypical workflow:\n{steps}"

    return (
        f"You are {agent_label}, a knowledgeable and supportive study assistant "
        f"specializing in {dc.domain_name} ({dc.domain_name_en}).\n\n"
        f"Your role:\n{role_lines}\n"
        f"- Support {lang_list} — respond in the user's language"
        f"{kb_section}{workflow}\n\n"
        "You are warm, patient, and focused on helping users find their own path to understanding."
    )


def _resolve_allowed_tool_names(active_skills: list[Skill]) -> set[str] | None:
    restricted_skills = [skill for skill in active_skills if skill.allowed_tools]
    if not restricted_skills:
        return None

    allowed_tool_names: set[str] = set()
    for skill in restricted_skills:
        allowed_tool_names.update(skill.allowed_tools)
    return allowed_tool_names


def build_prompt_context(user_message: str = "") -> tuple[str, set[str] | None]:
    """Build the full system prompt and effective tool allowance for a request.

    Args:
        user_message: The latest user message, used to determine which skills to activate.
    """
    prompt = _build_base_prompt()

    active_skills = skill_registry.get_active_skills(user_message)
    allowed_tool_names = _resolve_allowed_tool_names(active_skills)
    if active_skills:
        skill_sections = []
        for skill in active_skills:
            skill_sections.append(
                f"### {skill.name}\n{skill.body}"
            )
        prompt += "\n\n## Domain Knowledge & Guidelines\n\n"
        prompt += "\n\n---\n\n".join(skill_sections)

    tools = tool_registry.list_all(allowed_tool_names)
    if tools:
        prompt += build_tool_policy(t.schema() for t in tools)
    if allowed_tool_names is not None:
        prompt += (
            "\n\n## Tool Access\n"
            "For this request, you may only use these tools: "
            f"{', '.join(sorted(allowed_tool_names))}."
        )

    return prompt, allowed_tool_names


def build_system_prompt(user_message: str = "") -> str:
    return build_prompt_context(user_message)[0]


def parse_tool_call(text: str) -> dict[str, Any] | None:
    """Extract the first <tool_call> block from LLM output. Returns parsed dict or None."""
    match = TOOL_CALL_PATTERN.search(text)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        logger.warning("Failed to parse tool_call JSON: %s", match.group(1))
        return None


def strip_tool_call(text: str) -> str:
    """Remove <tool_call> blocks from text, returning any remaining text."""
    return TOOL_CALL_PATTERN.sub("", text).strip()


async def run_agent_loop(
    provider: BaseLLMProvider,
    messages: list[ProviderMessage],
    allowed_tool_names: set[str] | None = None,
    on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> tuple[str, list[dict]]:
    """Run the Agent loop: LLM → parse → execute tool → feed back → repeat.

    Args:
        provider: The LLM provider to use.
        messages: Full message list including system prompt.
        on_event: Optional async callback(event_dict) for streaming progress.

    Returns:
        (final_answer, tool_call_log) where tool_call_log is a list of
        {"tool": name, "args": {...}, "result": "..."} dicts.
    """
    tool_call_log: list[dict] = []

    max_tool_turns = domain_config.max_tool_turns

    for turn in range(max_tool_turns):
        if on_event:
            await on_event({
                "type": "status",
                "status": "thinking",
                "label": "Thinking",
                "detail": "Planning the next step",
            })
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
            await on_event({
                "type": "tool.started",
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "tool_display_name": tool_display_name,
                "tool_activity_label": tool_activity_label,
                "args": tool_args,
            })

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
            await on_event({
                "type": "tool.finished",
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "tool_display_name": tool_display_name,
                "tool_activity_label": tool_activity_label,
                "args": tool_args,
                "result": result_text,
                "success": result.success,
            })

        remaining_text = strip_tool_call(text)
        if remaining_text:
            messages.append(ProviderMessage(role="assistant", content=remaining_text))

        messages.append(ProviderMessage(
            role="assistant",
            content=f"<tool_call>\n{json.dumps(tool_call, ensure_ascii=False)}\n</tool_call>",
        ))
        messages.append(ProviderMessage(
            role="user",
            content=f"<tool_result>\n{result_text}\n</tool_result>",
        ))

    logger.warning("Agent reached max tool turns (%d)", max_tool_turns)
    final = await _chat_with_retry(provider, messages)
    return final.content, tool_call_log


async def _chat_with_retry(provider: BaseLLMProvider, messages: list[ProviderMessage]):
    for attempt in range(MAX_RETRIES):
        try:
            return await provider.chat(messages)
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise
            logger.warning("LLM call failed (attempt %d/%d): %s — retrying in %ds",
                           attempt + 1, MAX_RETRIES, e, RETRY_DELAY)
            await asyncio.sleep(RETRY_DELAY)
