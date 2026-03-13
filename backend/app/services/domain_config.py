"""Domain configuration service.

Loads domain.json and sources.json to provide domain-specific context for
the system prompt, skills, and tools. This abstraction allows the project
to support different learning domains beyond Japanese graduate entrance exams.
"""

import json
import logging
from pathlib import Path
from typing import Any

from app.config.settings import settings

logger = logging.getLogger(__name__)


class DomainConfig:
    """Singleton that holds the active domain profile and its source directory."""

    _instance: "DomainConfig | None" = None

    def __init__(self) -> None:
        self.profile: dict[str, Any] = {}
        self.sources: list[dict[str, Any]] = []
        self._loaded = False

    @classmethod
    def get(cls) -> "DomainConfig":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load(self, content_dir: Path | None = None) -> None:
        content_dir = content_dir or settings.content_path

        domain_file = content_dir / "domain.json"
        if domain_file.exists():
            self.profile = json.loads(domain_file.read_text(encoding="utf-8"))
            logger.info("Loaded domain profile: %s", self.profile.get("id", "unknown"))
        else:
            self.profile = self._default_profile()
            logger.warning("domain.json not found at %s, using defaults", domain_file)

        sources_file = content_dir / "sources.json"
        if sources_file.exists():
            data = json.loads(sources_file.read_text(encoding="utf-8"))
            self.sources = data.get("sources", [])
            logger.info("Loaded %d predefined sources", len(self.sources))
        else:
            self.sources = []
            logger.info("sources.json not found at %s, no predefined sources", sources_file)

        self._loaded = True

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def agent_name(self) -> str:
        return self.profile.get("agent_name", "The Kai Seeker")

    @property
    def agent_name_ja(self) -> str:
        return self.profile.get("agent_name_ja", "解を求める者")

    @property
    def domain_name(self) -> str:
        return self.profile.get("name", "学習")

    @property
    def domain_name_en(self) -> str:
        return self.profile.get("name_en", "Study")

    @property
    def domain_description(self) -> str:
        return self.profile.get("description", "A study assistant.")

    @property
    def role_description(self) -> list[str]:
        return self.profile.get("role_description", [])

    @property
    def languages(self) -> list[str]:
        return self.profile.get("languages", ["English"])

    @property
    def knowledge_base(self) -> dict[str, str]:
        return self.profile.get("knowledge_base", {})

    @property
    def workflow_hints(self) -> list[str]:
        return self.profile.get("workflow_hints", [])

    def search_sources(
        self,
        query: str | None = None,
        school_id: str | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        results = []
        for src in self.sources:
            if school_id and src.get("school_id") != school_id:
                continue
            if category and src.get("category") != category:
                continue
            if query:
                q = query.lower()
                searchable = " ".join([
                    src.get("id", ""),
                    src.get("name", ""),
                    src.get("school_id") or "",
                    src.get("category", ""),
                ]).lower()
                if q not in searchable:
                    continue
            results.append(src)
        return results

    @staticmethod
    def _default_profile() -> dict[str, Any]:
        return {
            "id": "default",
            "name": "学習",
            "name_en": "Study",
            "description": "A general-purpose study assistant.",
            "agent_name": "The Kai Seeker",
            "agent_name_ja": "解を求める者",
            "role_description": [
                "Help users study and learn effectively",
            ],
            "languages": ["Chinese", "Japanese", "English"],
            "knowledge_base": {},
            "workflow_hints": [],
        }


domain_config = DomainConfig.get()
