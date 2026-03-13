import logging
from pathlib import Path

from app.skills.base import Skill, parse_skill_file

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Registry for Markdown-based skills."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill
        logger.info("Registered skill: %s [%s]", skill.name, skill.source)

    def clear(self) -> None:
        self._skills.clear()

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def list_all(self) -> list[Skill]:
        return list(self._skills.values())

    def list_schemas(self) -> list[dict]:
        return [s.schema() for s in self._skills.values()]

    def get_active_skills(self, user_message: str) -> list[Skill]:
        """Return skills whose triggers match the user message."""
        return [s for s in self._skills.values() if s.matches(user_message)]

    def load_directory(self, directory: Path, source: str = "builtin") -> int:
        """Load all SKILL.md files from a directory (non-recursive).

        Also supports flat .md files (each treated as a skill).
        Returns the number of skills loaded.
        """
        if not directory.exists():
            return 0

        count = 0

        # Pattern 1: subdirectories with SKILL.md
        for subdir in sorted(directory.iterdir()):
            if subdir.is_dir():
                skill_file = subdir / "SKILL.md"
                if skill_file.exists():
                    skill = parse_skill_file(skill_file, source=source)
                    if skill:
                        self.register(skill)
                        count += 1

        # Pattern 2: flat .md files directly in the directory
        for md_file in sorted(directory.glob("*.md")):
            if md_file.name.startswith("_") or md_file.name == "README.md":
                continue
            skill = parse_skill_file(md_file, source=source)
            if skill:
                if skill.name not in self._skills:
                    self.register(skill)
                    count += 1

        return count


skill_registry = SkillRegistry()
