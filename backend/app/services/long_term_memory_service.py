import json
import re
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
        turn_summary: str | None,
        tool_calls: list[dict[str, Any]],
        commit: bool = False,
    ) -> LongTermMemoryRecord | None:
        content = self._build_session_insight_content(
            user_request=user_request,
            assistant_message=assistant_message,
            turn_summary=turn_summary,
            tool_calls=tool_calls,
        )
        summary = self._build_session_insight_summary(
            user_request=user_request,
            assistant_message=assistant_message,
            turn_summary=turn_summary,
            tool_calls=tool_calls,
        )
        if not content and not summary:
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
            content=content,
            summary=summary or None,
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
    def _build_session_insight_content(
        *,
        user_request: str,
        assistant_message: str,
        turn_summary: str | None,
        tool_calls: list[dict[str, Any]],
    ) -> str:
        tool_names = LongTermMemoryService._collect_tool_names(tool_calls)
        artifact_lines = LongTermMemoryService._collect_artifact_lines(tool_calls)

        sections = []
        if user_request:
            sections.append(f"User request:\n{user_request}")
        if assistant_message:
            sections.append(f"Assistant outcome:\n{assistant_message}")
        if turn_summary:
            sections.append(f"Turn summary:\n{turn_summary}")
        if tool_names:
            sections.append("Tools used:\n" + ", ".join(tool_names))
        if artifact_lines:
            sections.append("Artifacts:\n" + "\n".join(f"- {line}" for line in artifact_lines))
        return "\n\n".join(section for section in sections if section).strip()

    @staticmethod
    def _build_session_insight_summary(
        *,
        user_request: str,
        assistant_message: str,
        turn_summary: str | None,
        tool_calls: list[dict[str, Any]],
    ) -> str:
        answer_text = LongTermMemoryService._normalize_text(assistant_message)
        tool_names = LongTermMemoryService._collect_tool_names(tool_calls)
        normalized_turn_summary = LongTermMemoryService._normalize_text(turn_summary or "")
        if not user_request and not answer_text and not normalized_turn_summary:
            return ""
        parts = []
        if user_request:
            parts.append(user_request)
        if tool_names:
            parts.append(f"Tools: {', '.join(tool_names[:3])}")
        if normalized_turn_summary:
            parts.append(f"Outcome: {LongTermMemoryService._preview(normalized_turn_summary, limit=160)}")
        elif answer_text:
            parts.append(
                "Outcome: "
                + LongTermMemoryService._build_outcome_summary(answer_text, limit=96)
            )
        return " | ".join(part for part in parts if part).strip()

    @staticmethod
    def _collect_tool_names(tool_calls: list[dict[str, Any]]) -> list[str]:
        tool_names: list[str] = []
        for record in tool_calls:
            tool_name = record.get("tool_name") or record.get("tool")
            if tool_name and tool_name not in tool_names:
                tool_names.append(str(tool_name))
        return tool_names

    @staticmethod
    def _collect_artifact_lines(tool_calls: list[dict[str, Any]]) -> list[str]:
        lines: list[str] = []
        for tool_call in tool_calls:
            tool_name = str(tool_call.get("tool_name") or tool_call.get("tool") or "tool")
            artifacts = tool_call.get("artifacts")
            if not isinstance(artifacts, list):
                continue
            for artifact in artifacts[:3]:
                if not isinstance(artifact, dict):
                    continue
                label = artifact.get("label") or artifact.get("kind") or "artifact"
                summary = artifact.get("summary")
                line = f"{tool_name}: {label}"
                if isinstance(summary, str) and summary.strip():
                    line += f" | {LongTermMemoryService._preview(summary, limit=140)}"
                lines.append(line)
                if len(lines) >= 6:
                    return lines
        return lines

    @staticmethod
    def _preview(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 1] + "…"

    @staticmethod
    def _normalize_text(text: str) -> str:
        return " ".join(text.split())

    @staticmethod
    def _build_outcome_summary(text: str, limit: int) -> str:
        cleaned = LongTermMemoryService._strip_leading_filler(text)
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[。！？!?])\s+|\n+", cleaned)
            if sentence.strip()
        ]
        if not sentences:
            return LongTermMemoryService._preview(cleaned, limit)

        summary_parts: list[str] = []
        used = 0
        for sentence in sentences:
            if not summary_parts and len(sentence) >= limit:
                return LongTermMemoryService._preview(sentence, limit)
            projected = used + len(sentence) + (1 if summary_parts else 0)
            if projected > limit:
                break
            summary_parts.append(sentence)
            used = projected
            if used >= int(limit * 0.7):
                break

        summary = " ".join(summary_parts).strip()
        if not summary:
            summary = sentences[0]
        return LongTermMemoryService._preview(summary, limit)

    @staticmethod
    def _strip_leading_filler(text: str) -> str:
        cleaned = text.strip()
        patterns = [
            r"^(好的|好|当然|可以|嗯|是的|没问题)[，,\s]*",
            r"^我已经[^，。]*[，,\s]*",
        ]
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned)
        return cleaned.strip()
