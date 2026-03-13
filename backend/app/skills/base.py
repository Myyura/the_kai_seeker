"""Markdown-based skill system for The Kai Seeker (解を求める者).

A Skill is a set of instructions/knowledge that gets injected into the LLM's
system prompt when relevant. Unlike Tools (which execute code), Skills guide
the LLM's reasoning and response patterns.

This file is part of The Kai Seeker, licensed under AGPL-3.0.
Source: https://github.com/Myyura/the_kai_seeker

Format follows the SKILL.md open standard (agentskills.io) with our own extensions:

---
name: skill-name
description: What this skill does and when to activate it.
trigger: Keywords or conditions that activate this skill.
allowed-tools: search_questions fetch_question web_fetch
metadata:
  author: the-kai-seeker
  version: "1.0"
  tags: [admission, planning]
---

# Skill Title

Instructions in Markdown...
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)", re.DOTALL)


@dataclass
class Skill:
    name: str
    description: str
    body: str
    trigger: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    source: str = ""  # "builtin" or "user"
    source_path: str = ""

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "trigger": self.trigger,
            "allowed_tools": self.allowed_tools,
            "source": self.source,
        }

    def matches(self, user_message: str) -> bool:
        """Check if this skill should activate for the given user message."""
        if not self.trigger:
            return True  # always-on skill

        msg_lower = user_message.lower()
        triggers = [t.strip().lower() for t in self.trigger.split(",") if t.strip()]
        return any(t in msg_lower for t in triggers)


def _parse_yaml_simple(text: str) -> dict:
    """Minimal YAML parser for skill frontmatter (no PyYAML dependency)."""
    result: dict = {}
    current_key = None
    current_is_list = False
    current_is_map = False
    map_data: dict = {}

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())

        if indent > 0 and current_key:
            if stripped.startswith("-"):
                item = stripped.lstrip("-").strip().strip("'\"")
                if current_is_list:
                    result[current_key].append(item)
                else:
                    result[current_key] = [item]
                    current_is_list = True
                continue
            if ":" in stripped:
                k, _, v = stripped.partition(":")
                map_data[k.strip()] = v.strip().strip("'\"")
                if not current_is_map:
                    current_is_map = True
                    result[current_key] = map_data
                continue

        if ":" in stripped and not stripped.startswith("-"):
            if current_is_map and current_key:
                result[current_key] = map_data
                map_data = {}
                current_is_map = False

            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip().strip("'\"")
            current_key = key
            current_is_list = False
            current_is_map = False
            map_data = {}

            if value.startswith("[") and value.endswith("]"):
                items = [v.strip().strip("'\"") for v in value[1:-1].split(",") if v.strip()]
                result[key] = items
            elif value:
                result[key] = value
            else:
                result[key] = None

    if current_is_map and current_key:
        result[current_key] = map_data

    return result


def parse_skill_file(path: Path, source: str = "builtin") -> Skill | None:
    """Parse a SKILL.md file into a Skill object."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("Failed to read skill file %s: %s", path, e)
        return None

    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        logger.warning("No frontmatter found in %s", path)
        return None

    fm_text = match.group(1)
    body = match.group(2).strip()

    fm = _parse_yaml_simple(fm_text)

    name = fm.get("name")
    description = fm.get("description")
    if not name or not description:
        logger.warning("Skill in %s missing required 'name' or 'description'", path)
        return None

    allowed_tools_raw = fm.get("allowed-tools") or fm.get("allowed_tools", "")
    if isinstance(allowed_tools_raw, str):
        allowed_tools = [t.strip() for t in allowed_tools_raw.split() if t.strip()]
    elif isinstance(allowed_tools_raw, list):
        allowed_tools = allowed_tools_raw
    else:
        allowed_tools = []

    trigger = fm.get("trigger", "")
    metadata = fm.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    return Skill(
        name=name,
        description=description,
        body=body,
        trigger=trigger,
        allowed_tools=allowed_tools,
        metadata=metadata,
        source=source,
        source_path=str(path),
    )
