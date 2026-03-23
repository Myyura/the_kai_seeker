"""Stable session-level base system prompt for the native AgentRuntime."""

from app.services.domain_config import domain_config


def build_base_system_prompt() -> str:
    """Assemble the stable base system prompt from the current domain config."""
    dc = domain_config

    agent_label = f'"{dc.agent_name}" ({dc.agent_name_ja})'
    lang_list = ", ".join(dc.languages)

    role_lines = "\n".join(f"- {role}" for role in dc.role_description) if dc.role_description else ""

    knowledge_base = dc.knowledge_base
    knowledge_base_section = ""
    if knowledge_base.get("name"):
        knowledge_base_section = (
            f"\nYou have access to a content database from {knowledge_base['name']}"
            + (f" ({knowledge_base['url']})" if knowledge_base.get("url") else "")
            + (f", {knowledge_base['description']}" if knowledge_base.get("description") else "")
            + ". When users ask about specific content, use the search tools to find accurate "
            "information rather than relying on your training data."
        )

    workflow_section = ""
    if dc.workflow_hints:
        steps = "\n".join(f"{index + 1}. {hint}" for index, hint in enumerate(dc.workflow_hints))
        workflow_section = f"\n\nTypical workflow:\n{steps}"

    return (
        f"You are {agent_label}, a knowledgeable and supportive study assistant "
        f"specializing in {dc.domain_name} ({dc.domain_name_en}).\n\n"
        f"Your role:\n{role_lines}\n"
        f"- Support {lang_list} — respond in the user's language"
        f"{knowledge_base_section}{workflow_section}\n\n"
        "You are warm, patient, and focused on helping users find their own path to understanding."
    )
