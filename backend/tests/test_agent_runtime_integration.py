import json

import pytest
from sqlalchemy import select

from app.models.long_term_memory import LongTermMemoryRecord
from app.models.pdf_document import PdfDocument
from app.models.study_target import StudyTarget
from app.repositories.agent_runtime_repo import AgentRuntimeRepository
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.long_term_memory_repo import LongTermMemoryRepository
from app.repositories.provider_repo import ProviderRepository
from app.schemas.chat import ChatMessageIn
from app.schemas.provider import ProviderSettingCreate
from app.services.conversation_service import ConversationService
from app.services.long_term_memory_service import LongTermMemoryService


@pytest.mark.asyncio
async def test_runtime_link_keeps_first_base_system_prompt(db_session, monkeypatch) -> None:
    provider_repo = ProviderRepository(db_session)
    await provider_repo.create(
        ProviderSettingCreate(
            provider="openai",
            api_key="secret",
            base_url="https://api.openai.com/v1",
            model="gpt-test",
        )
    )

    async def fake_run_agent_loop(provider, messages, allowed_tool_names=None, on_event=None):  # type: ignore[no-untyped-def]
        return "first answer", []

    service = ConversationService(db_session, tool_loop_runner=fake_run_agent_loop)
    _content, _model, sid, _log = await service.chat([ChatMessageIn(role="user", content="hello")])

    repo = AgentRuntimeRepository(db_session)
    first_link = await repo.get_link_by_session_id(sid)
    assert first_link is not None
    first_prompt = first_link.base_system_prompt
    assert "You are" in first_prompt

    changed_service = ConversationService(
        db_session,
        tool_loop_runner=fake_run_agent_loop,
        base_system_prompt_builder=lambda: "changed",
    )
    await changed_service.chat([ChatMessageIn(role="user", content="hello again")], session_id=sid)

    second_link = await repo.get_link_by_session_id(sid)
    assert second_link is not None
    assert second_link.runtime_name == "native"
    assert second_link.base_system_prompt == first_prompt
    assert second_link.base_system_prompt != "changed"


@pytest.mark.asyncio
async def test_resource_handles_separate_session_and_transient(db_session, monkeypatch) -> None:
    provider_repo = ProviderRepository(db_session)
    await provider_repo.create(
        ProviderSettingCreate(
            provider="openai",
            api_key="secret",
            base_url="https://api.openai.com/v1",
            model="gpt-test",
        )
    )
    pdf = PdfDocument(filename="guide.pdf", storage_path="/tmp/guide.pdf", status="uploaded")
    db_session.add(pdf)
    await db_session.commit()
    await db_session.refresh(pdf)

    captured_turns: list[list[str]] = []

    async def fake_run_agent_loop(provider, messages, allowed_tool_names=None, on_event=None):  # type: ignore[no-untyped-def]
        captured_turns.append([message.content for message in messages])
        return "ok", []

    service = ConversationService(db_session, tool_loop_runner=fake_run_agent_loop)
    _content, _model, sid, _log = await service.chat(
        [ChatMessageIn(role="user", content="Use this pdf.")],
        pdf_ids=[pdf.id],
    )
    await service.chat([ChatMessageIn(role="user", content="Continue.")], session_id=sid)

    first_context = captured_turns[0][1]
    second_context = captured_turns[1][1]

    assert "### Session Resources\n- None." in first_context
    assert f"### Turn Resources\n- pdf:{pdf.id}" in first_context

    assert f"### Session Resources\n- pdf:{pdf.id}" in second_context
    assert "### Turn Resources\n- None." in second_context


@pytest.mark.asyncio
async def test_memory_pack_uses_study_targets_without_copying_them(db_session, monkeypatch) -> None:
    provider_repo = ProviderRepository(db_session)
    await provider_repo.create(
        ProviderSettingCreate(
            provider="openai",
            api_key="secret",
            base_url="https://api.openai.com/v1",
            model="gpt-test",
        )
    )
    db_session.add(
        StudyTarget(
            school_id="tokyo-university",
            program_id="cs",
            label="东京大学 CS",
            notes="Focus on algorithms",
        )
    )
    await db_session.commit()

    async def fake_run_agent_loop(provider, messages, allowed_tool_names=None, on_event=None):  # type: ignore[no-untyped-def]
        return "We should focus on algorithms.", []

    service = ConversationService(db_session, tool_loop_runner=fake_run_agent_loop)
    await service.chat([ChatMessageIn(role="user", content="Give me a summary.")])

    memory_pack = await LongTermMemoryService(db_session).build_memory_pack(session_id=1)
    assert len(memory_pack.study_targets) == 1
    assert memory_pack.study_targets[0].school_id == "tokyo-university"

    records = list((await db_session.execute(select(LongTermMemoryRecord))).scalars().all())
    assert any(record.memory_type == "session_insight" for record in records)
    assert not any(record.memory_type == "study_target" for record in records)


@pytest.mark.asyncio
async def test_run_debug_payload_persists_runtime_inputs_and_outputs(db_session) -> None:
    provider_repo = ProviderRepository(db_session)
    await provider_repo.create(
        ProviderSettingCreate(
            provider="openai",
            api_key="secret",
            base_url="https://api.openai.com/v1",
            model="gpt-test",
        )
    )
    pdf = PdfDocument(filename="notes.pdf", storage_path="/tmp/notes.pdf", status="uploaded")
    db_session.add(pdf)
    db_session.add(
        StudyTarget(
            school_id="kyoto-university",
            program_id="ml",
            label="京都大学 ML",
            notes="Focus on math",
        )
    )
    await db_session.commit()
    await db_session.refresh(pdf)

    async def fake_run_agent_loop(provider, messages, allowed_tool_names=None, on_event=None):  # type: ignore[no-untyped-def]
        return "Use the math-heavy plan.", []

    service = ConversationService(db_session, tool_loop_runner=fake_run_agent_loop)
    _content, _model, sid, _log = await service.chat(
        [ChatMessageIn(role="user", content="Plan my preparation.")],
        pdf_ids=[pdf.id],
    )

    conversation = await ConversationRepository(db_session).get_session(sid)
    assert conversation is not None
    run = conversation.runs[-1]
    assert run.debug_payload is not None

    payload = json.loads(run.debug_payload.payload)
    assert payload["status"] == "completed"
    assert payload["runtime_link"]["runtime_name"] == "native"
    assert payload["context_sync"]["context_version"] == payload["host_context_state"]["context_version"]
    assert payload["host_context_state"]["memory_pack"]["study_targets"][0]["school_id"] == "kyoto-university"
    assert payload["turn_input"]["transient_resource_handles"][0]["resource_id"] == str(pdf.id)
    assert payload["runtime_snapshot"]["short_term_memory"]["progress"]["last_assistant_summary"]
    assert payload["long_term_memory_writes"]
    assert payload["assistant_text"] == "Use the math-heavy plan."


@pytest.mark.asyncio
async def test_failed_run_persists_debug_payload(db_session) -> None:
    provider_repo = ProviderRepository(db_session)
    await provider_repo.create(
        ProviderSettingCreate(
            provider="openai",
            api_key="secret",
            base_url="https://api.openai.com/v1",
            model="gpt-test",
        )
    )

    async def fake_run_agent_loop(provider, messages, allowed_tool_names=None, on_event=None):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    service = ConversationService(db_session, tool_loop_runner=fake_run_agent_loop)

    with pytest.raises(RuntimeError, match="boom"):
        await service.chat([ChatMessageIn(role="user", content="Trigger a failure.")])

    sessions = await ConversationRepository(db_session).list_sessions()
    assert sessions
    conversation = await ConversationRepository(db_session).get_session(sessions[0].id)
    assert conversation is not None
    run = conversation.runs[-1]
    assert run.debug_payload is not None

    payload = json.loads(run.debug_payload.payload)
    assert payload["status"] == "failed"
    assert payload["assistant_text"] is None
    assert payload["tool_records"] == []
    assert payload["error"]["type"] == "RuntimeError"
    assert payload["error"]["message"] == "boom"


@pytest.mark.asyncio
async def test_memory_pack_excludes_session_insights_from_other_sessions(db_session) -> None:
    memory_repo = LongTermMemoryRepository(db_session)
    await memory_repo.add_record(
        memory_type="session_insight",
        scope="session:1",
        content="session one insight",
        source_session_id=1,
        confidence=0.5,
        commit=False,
    )
    await memory_repo.add_record(
        memory_type="session_insight",
        scope="session:2",
        content="session two insight",
        source_session_id=2,
        confidence=0.5,
        commit=False,
    )
    await memory_repo.add_record(
        memory_type="preference",
        scope="global",
        content="Prefer mathematically rigorous explanations.",
        source_session_id=2,
        confidence=0.5,
        commit=False,
    )
    await db_session.commit()

    memory_pack = await LongTermMemoryService(db_session).build_memory_pack(session_id=1)

    session_insights = [item.content for item in memory_pack.session_insights]
    preferences = [item.content for item in memory_pack.preferences]
    assert "session one insight" in session_insights
    assert "session two insight" not in session_insights
    assert "Prefer mathematically rigorous explanations." in preferences


@pytest.mark.asyncio
async def test_delete_session_removes_derived_long_term_memory(db_session) -> None:
    provider_repo = ProviderRepository(db_session)
    await provider_repo.create(
        ProviderSettingCreate(
            provider="openai",
            api_key="secret",
            base_url="https://api.openai.com/v1",
            model="gpt-test",
        )
    )

    async def fake_run_agent_loop(provider, messages, allowed_tool_names=None, on_event=None):  # type: ignore[no-untyped-def]
        return "A focused answer.", []

    service = ConversationService(db_session, tool_loop_runner=fake_run_agent_loop)
    _content, _model, sid, _log = await service.chat([ChatMessageIn(role="user", content="Remember this.")])

    records_before = await LongTermMemoryRepository(db_session).list_by_source_session(sid)
    assert records_before

    deleted = await service.delete_session(sid)
    assert deleted is True

    records_after = await LongTermMemoryRepository(db_session).list_by_source_session(sid)
    assert records_after == []
