"""In-memory content index loaded from schools.json + questions.json.

Provides lightweight search over school/department/program/question metadata
without any vector database. Designed to be queried by LLM tools.
"""

import json
import logging
from pathlib import Path

from app.config.settings import settings

logger = logging.getLogger(__name__)


class ContentIndex:
    """Singleton that holds the loaded index data and provides query methods."""

    _instance: "ContentIndex | None" = None

    def __init__(self) -> None:
        self.schools: list[dict] = []
        self.questions: list[dict] = []
        self._loaded = False

    @classmethod
    def get(cls) -> "ContentIndex":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load(self, content_dir: Path | None = None) -> None:
        content_dir = content_dir or settings.content_path
        schools_file = content_dir / "schools.json"
        questions_file = content_dir / "questions.json"

        if schools_file.exists():
            self.schools = json.loads(schools_file.read_text(encoding="utf-8"))
            logger.info("Loaded %d schools from %s", len(self.schools), schools_file)
        else:
            logger.warning("schools.json not found at %s", schools_file)

        if questions_file.exists():
            self.questions = json.loads(questions_file.read_text(encoding="utf-8"))
            logger.info("Loaded %d questions from %s", len(self.questions), questions_file)
        else:
            logger.warning("questions.json not found at %s", questions_file)

        self._loaded = True

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def search_schools(
        self,
        query: str | None = None,
    ) -> list[dict]:
        """Search schools by name (fuzzy substring match on id and name_ja)."""
        results = []
        for school in self.schools:
            if query:
                q = query.lower()
                if not (
                    q in school["id"].lower()
                    or q in school.get("name_ja", "").lower()
                    or any(
                        q in d.get("name_ja", "").lower() or q in d["id"].lower()
                        for d in school.get("departments", [])
                    )
                ):
                    continue
            results.append(self._summarize_school(school))
        return results

    def search_questions(
        self,
        school_id: str | None = None,
        department_id: str | None = None,
        program_id: str | None = None,
        year: int | None = None,
        tags: list[str] | None = None,
        keyword: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Filter questions by structured fields and/or keyword."""
        results = []
        for q in self.questions:
            if school_id and school_id.lower() != q["school_id"].lower():
                continue
            if department_id and department_id.lower() != q["department_id"].lower():
                continue
            if program_id:
                question_program_id = q.get("program_id")
                if not question_program_id or program_id.lower() != question_program_id.lower():
                    continue
            if year and year != q["year"]:
                continue
            if tags:
                q_tags_lower = {t.lower() for t in q.get("tags", [])}
                if not any(t.lower() in q_tags_lower for t in tags):
                    continue
            if keyword:
                kw = keyword.lower()
                searchable = " ".join(
                    [
                        q.get("title", ""),
                        q.get("sidebar_label", "") or "",
                        q.get("filename", ""),
                        " ".join(q.get("tags", [])),
                    ]
                ).lower()
                if kw not in searchable:
                    continue
            results.append(q)
            if len(results) >= limit:
                break
        return results

    def get_question(self, question_id: str) -> dict | None:
        for q in self.questions:
            if q["id"] == question_id:
                return q
        return None

    @staticmethod
    def _summarize_school(school: dict) -> dict:
        """Return a concise summary of a school for LLM consumption."""
        departments = []
        for dept in school.get("departments", []):
            programs = [
                {"id": p["id"], "name_ja": p.get("name_ja", p["id"])}
                for p in dept.get("programs", [])
            ]
            departments.append(
                {
                    "id": dept["id"],
                    "name_ja": dept.get("name_ja", dept["id"]),
                    "programs": programs,
                }
            )
        return {
            "id": school["id"],
            "name_ja": school.get("name_ja", school["id"]),
            "departments": departments,
        }


content_index = ContentIndex.get()
