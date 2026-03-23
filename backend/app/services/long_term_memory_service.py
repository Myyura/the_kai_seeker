import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.types import MemoryItem, MemoryPack, StudyTargetMemory
from app.models.long_term_memory import LongTermMemoryRecord
from app.repositories.long_term_memory_repo import LongTermMemoryRepository
from app.repositories.study_target_repo import StudyTargetRepository

DEFAULT_MEMORY_LIMIT = 5
DEFAULT_SESSION_INSIGHT_CONFIDENCE = 0.5


class LongTermMemoryService:
    """Builds memory packs from canonical tables and derived long-term memory records."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.memory_repo = LongTermMemoryRepository(session)
        self.study_target_repo = StudyTargetRepository(session)

    async def build_memory_pack(
        self,
        *,
        session_id: int,
    ) -> MemoryPack:
        study_targets = await self.study_target_repo.list_all(limit=100)
        study_target_ids = [target.id for target in study_targets]
        # TODO: Add request-aware relevance ranking here so MemoryPack selection can
        # prefer only the most relevant global / target-scoped memory for the current turn.
        records = await self.memory_repo.list_for_memory_pack(
            session_id=session_id,
            related_target_ids=study_target_ids,
            limit=100,
        )
        records = self._filter_records_for_memory_pack(records, session_id=session_id)
        grouped = self._group_records(records)
        return MemoryPack(
            study_targets=[
                StudyTargetMemory(
                    id=target.id,
                    school_id=target.school_id,
                    program_id=target.program_id,
                    label=target.label,
                    notes=target.notes,
                )
                for target in study_targets
            ],
            preferences=grouped["preference"][:DEFAULT_MEMORY_LIMIT],
            profile_facts=grouped["profile_fact"][:DEFAULT_MEMORY_LIMIT],
            session_insights=grouped["session_insight"][:DEFAULT_MEMORY_LIMIT],
            strength_signals=grouped["strength_signal"][:DEFAULT_MEMORY_LIMIT],
            weakness_signals=grouped["weakness_signal"][:DEFAULT_MEMORY_LIMIT],
            learning_patterns=grouped["learning_pattern"][:DEFAULT_MEMORY_LIMIT],
            plan_hints=grouped["plan_hint"][:DEFAULT_MEMORY_LIMIT],
        )

    async def write_session_insight(
        self,
        *,
        session_id: int,
        run_id: int | None,
        user_request: str,
        assistant_message: str,
        tool_records: list[dict[str, Any]],
        commit: bool = False,
    ) -> LongTermMemoryRecord | None:
        summary = self._build_session_insight_summary(
            user_request=user_request,
            assistant_message=assistant_message,
            tool_records=tool_records,
        )
        if not summary:
            return None
        # TODO: Replace this placeholder confidence with evidence-based scoring.
        # Suggested future inputs:
        # - whether the user stated the fact explicitly
        # - repetition across sessions / runs
        # - support from tool results or canonical entities
        # - contradiction with existing higher-confidence memory
        return await self.memory_repo.add_record(
            memory_type="session_insight",
            scope=f"session:{session_id}",
            content=summary,
            summary=summary,
            importance=0.6,
            confidence=DEFAULT_SESSION_INSIGHT_CONFIDENCE,
            source_session_id=session_id,
            source_run_id=run_id,
            tags=["chat", "session-insight"],
            commit=commit,
        )

    async def delete_session_records(
        self,
        session_id: int,
        *,
        commit: bool = False,
    ) -> int:
        return await self.memory_repo.delete_for_session(session_id, commit=commit)

    @staticmethod
    def _group_records(records: list[LongTermMemoryRecord]) -> dict[str, list[MemoryItem]]:
        grouped: dict[str, list[MemoryItem]] = {
            "preference": [],
            "profile_fact": [],
            "session_insight": [],
            "strength_signal": [],
            "weakness_signal": [],
            "learning_pattern": [],
            "plan_hint": [],
        }
        for record in records:
            if record.memory_type not in grouped:
                continue
            grouped[record.memory_type].append(
                MemoryItem(
                    id=record.id,
                    memory_type=record.memory_type,
                    content=record.content,
                    summary=record.summary,
                    importance=record.importance,
                    confidence=record.confidence,
                    related_target_id=record.related_target_id,
                    tags=LongTermMemoryService._parse_tags(record.tags),
                )
            )
        return grouped

    @staticmethod
    def _filter_records_for_memory_pack(
        records: list[LongTermMemoryRecord],
        *,
        session_id: int,
    ) -> list[LongTermMemoryRecord]:
        session_scope = f"session:{session_id}"
        filtered: list[LongTermMemoryRecord] = []
        for record in records:
            if record.memory_type == "session_insight":
                if record.scope != session_scope and record.source_session_id != session_id:
                    continue
            filtered.append(record)
        return filtered

    @staticmethod
    def _parse_tags(raw: str) -> list[str]:
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return [str(item) for item in parsed if item]

    @staticmethod
    def _build_session_insight_summary(
        *,
        user_request: str,
        assistant_message: str,
        tool_records: list[dict[str, Any]],
    ) -> str:
        request_text = " ".join(user_request.split())
        answer_text = " ".join(assistant_message.split())
        if not request_text and not answer_text:
            return ""
        tool_names = [record.get("tool") for record in tool_records if record.get("tool")]
        tool_part = f" Tools used: {', '.join(tool_names)}." if tool_names else ""
        request_part = f"User asked: {request_text}." if request_text else ""
        answer_part = f" Outcome: {answer_text[:320]}" if answer_text else ""
        return f"{request_part}{answer_part}{tool_part}".strip()
