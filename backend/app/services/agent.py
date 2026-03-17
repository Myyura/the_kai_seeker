"""Agent dispatcher for The Kai Seeker (解を求める者).

Orchestrates the LLM ↔ Tool calling loop using a provider-agnostic approach:
- Tool/Skill schemas are injected into the system prompt
- LLM is instructed to emit <tool_call> blocks when it needs a tool
- Agent parses tool calls, executes them, and feeds results back
- Loop continues until LLM produces a final text answer (max N turns)

This file is part of The Kai Seeker, licensed under AGPL-3.0.
Source: https://github.com/Myyura/the_kai_seeker
"""

import json
import logging
import re
from typing import Any

from app.providers.base import BaseLLMProvider, ChatMessage
from app.services.domain_config import domain_config
from app.skills.registry import skill_registry
from app.tools.registry import tool_registry

logger = logging.getLogger(__name__)

import asyncio

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

TOOL_CALL_PATTERN = re.compile(
    r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
    re.DOTALL,
)

TOOL_INSTRUCTIONS = """

## Available Tools

You have access to the following tools. **You should actively use tools** whenever a question involves:
- Looking up real-time or specific web page content
- Fetching official school/program/exam information from URLs
- Any task where accurate, up-to-date information is needed rather than relying on your training data

To use a tool, respond ONLY with a tool_call block (no other text before it):

<tool_call>
{{"name": "tool_name", "arguments": {{"param1": "value1"}}}}
</tool_call>

Important rules:
- Output ONLY the <tool_call> block when you want to use a tool, with no extra text
- You may call ONE tool per response
- After you receive the result in <tool_result>, you can call another tool or give your final answer
- When you have enough information, respond with your final answer as normal text (no tool_call block)
- If the user explicitly asks you to fetch a URL or use a specific tool, you MUST use it

Tools:
{tool_list}"""


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


def build_system_prompt(user_message: str = "") -> str:
    """Build the full system prompt with tools and context-activated skills.

    Args:
        user_message: The latest user message, used to determine which skills to activate.
    """
    prompt = _build_base_prompt()

    active_skills = skill_registry.get_active_skills(user_message)
    if active_skills:
        skill_sections = []
        for skill in active_skills:
            skill_sections.append(
                f"### {skill.name}\n{skill.body}"
            )
        prompt += "\n\n## Domain Knowledge & Guidelines\n\n"
        prompt += "\n\n---\n\n".join(skill_sections)

    tools = tool_registry.list_all()
    if tools:
        tool_descriptions = []
        for t in tools:
            s = t.schema()
            params = s.get("parameters", [])
            params_desc = ""
            if params:
                parts = ", ".join(
                    f'{p["name"]} ({p["type"]}, {"required" if p["required"] else "optional"}): '
                    f'{p["description"]}'
                    for p in params
                )
                params_desc = f"  Parameters: {parts}"
            tool_descriptions.append(f"- **{s['name']}**: {s['description']}\n{params_desc}")

        tool_list = "\n".join(tool_descriptions)
        prompt += TOOL_INSTRUCTIONS.format(tool_list=tool_list)

    return prompt


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
    messages: list[ChatMessage],
    on_tool_call: Any | None = None,
) -> tuple[str, list[dict]]:
    """Run the Agent loop: LLM → parse → execute tool → feed back → repeat.

    Args:
        provider: The LLM provider to use.
        messages: Full message list including system prompt.
        on_tool_call: Optional async callback(tool_name, tool_args, tool_result)
                      for streaming progress to the frontend.

    Returns:
        (final_answer, tool_call_log) where tool_call_log is a list of
        {"tool": name, "args": {...}, "result": "..."} dicts.
    """
    tool_call_log: list[dict] = []

    max_tool_turns = domain_config.max_tool_turns

    for turn in range(max_tool_turns):
        response = await _chat_with_retry(provider, messages)
        text = response.content

        tool_call = parse_tool_call(text)
        if tool_call is None:
            return text, tool_call_log

        tool_name = tool_call.get("name", "")
        tool_args = tool_call.get("arguments", {})

        logger.info("Agent tool call [turn %d]: %s(%s)", turn + 1, tool_name, tool_args)

        result = await tool_registry.execute(tool_name, **tool_args)
        result_text = result.to_text()

        log_entry = {"tool": tool_name, "args": tool_args, "result": result_text}
        tool_call_log.append(log_entry)

        if on_tool_call:
            await on_tool_call(tool_name, tool_args, result_text)

        remaining_text = strip_tool_call(text)
        if remaining_text:
            messages.append(ChatMessage(role="assistant", content=remaining_text))

        messages.append(ChatMessage(
            role="assistant",
            content=f"<tool_call>\n{json.dumps(tool_call, ensure_ascii=False)}\n</tool_call>",
        ))
        messages.append(ChatMessage(
            role="user",
            content=f"<tool_result>\n{result_text}\n</tool_result>",
        ))

    logger.warning("Agent reached max tool turns (%d)", max_tool_turns)
    final = await _chat_with_retry(provider, messages)
    return final.content, tool_call_log


async def _chat_with_retry(provider: BaseLLMProvider, messages: list[ChatMessage]):
    for attempt in range(MAX_RETRIES):
        try:
            return await provider.chat(messages)
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise
            logger.warning("LLM call failed (attempt %d/%d): %s — retrying in %ds",
                           attempt + 1, MAX_RETRIES, e, RETRY_DELAY)
            await asyncio.sleep(RETRY_DELAY)
