import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.types import AgentRuntimeLink as AgentRuntimeLinkData
from app.agent_runtime.types import AgentRuntimeSnapshot
from app.models.agent_runtime import AgentRuntimeLink, AgentRuntimeSnapshotRecord


class AgentRuntimeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_link_by_session_id(self, chat_session_id: int) -> AgentRuntimeLink | None:
        stmt = select(AgentRuntimeLink).where(AgentRuntimeLink.chat_session_id == chat_session_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def save_link(
        self,
        chat_session_id: int,
        link: AgentRuntimeLinkData,
        *,
        commit: bool = True,
    ) -> AgentRuntimeLink:
        record = await self.get_link_by_session_id(chat_session_id)
        metadata = json.dumps(link.metadata, ensure_ascii=False)
        if record is None:
            record = AgentRuntimeLink(
                chat_session_id=chat_session_id,
                runtime_name=link.runtime_name,
                runtime_session_id=link.runtime_session_id,
                runtime_conversation_id=link.runtime_conversation_id,
                base_system_prompt=link.base_system_prompt,
                status=link.status,
                metadata_json=metadata,
            )
            self.session.add(record)
        else:
            record.runtime_name = link.runtime_name
            record.runtime_session_id = link.runtime_session_id
            record.runtime_conversation_id = link.runtime_conversation_id
            record.base_system_prompt = link.base_system_prompt
            record.status = link.status
            record.metadata_json = metadata

        await self.session.flush()
        if commit:
            await self.session.commit()
            await self.session.refresh(record)
        return record

    async def save_snapshot(
        self,
        chat_session_id: int,
        snapshot: AgentRuntimeSnapshot,
        *,
        run_id: int | None = None,
        commit: bool = True,
    ) -> AgentRuntimeSnapshotRecord:
        record = AgentRuntimeSnapshotRecord(
            chat_session_id=chat_session_id,
            run_id=run_id,
            runtime_name=snapshot.runtime_name,
            runtime_session_id=snapshot.runtime_session_id,
            snapshot_payload=snapshot.model_dump_json(),
        )
        self.session.add(record)
        await self.session.flush()
        if commit:
            await self.session.commit()
            await self.session.refresh(record)
        return record

    @staticmethod
    def to_data(record: AgentRuntimeLink) -> AgentRuntimeLinkData:
        metadata: dict[str, Any] = {}
        if record.metadata_json:
            try:
                parsed = json.loads(record.metadata_json)
            except json.JSONDecodeError:
                parsed = {}
            if isinstance(parsed, dict):
                metadata = parsed
        return AgentRuntimeLinkData(
            id=record.id,
            chat_session_id=record.chat_session_id,
            runtime_name=record.runtime_name,
            runtime_session_id=record.runtime_session_id,
            runtime_conversation_id=record.runtime_conversation_id,
            base_system_prompt=record.base_system_prompt,
            status=record.status,
            metadata=metadata,
        )
