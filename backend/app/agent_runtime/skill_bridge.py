from app.agent_runtime.types import SkillDefinition
from app.skills.base import Skill


class SkillBridge:
    """Converts runtime-agnostic skill registry objects into runtime definitions."""

    @staticmethod
    def build_definitions(skills: list[Skill]) -> list[SkillDefinition]:
        definitions: list[SkillDefinition] = []
        for index, skill in enumerate(skills):
            trigger_rules = [item.strip() for item in skill.trigger.split(",") if item.strip()]
            tags = skill.metadata.get("tags", []) if isinstance(skill.metadata, dict) else []
            if not isinstance(tags, list):
                tags = []
            definitions.append(
                SkillDefinition(
                    name=skill.name,
                    description=skill.description,
                    trigger_rules=trigger_rules,
                    prompt_block=skill.body,
                    allowed_tools=list(skill.allowed_tools),
                    priority=max(0, len(skills) - index),
                    tags=[str(tag) for tag in tags],
                )
            )
        return definitions
