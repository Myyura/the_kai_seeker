import pytest

from app.repositories.conversation_repo import ConversationRepository
from app.repositories.provider_repo import ProviderRepository
from app.schemas.chat import ChatMessageIn
from app.schemas.provider import ProviderSettingCreate
from app.services.chat_service import ChatService


@pytest.mark.asyncio
async def test_list_sessions_orders_by_latest_activity(db_session) -> None:
    repo = ConversationRepository(db_session)

    first = await repo.create_session(title="First")
    second = await repo.create_session(title="Second")
    initial = [session.id for session in await repo.list_sessions()]
    assert initial[:2] == [second.id, first.id]

    await repo.add_message(first.id, "user", "new activity")
    after_message = [session.id for session in await repo.list_sessions()]
    assert after_message[:2] == [first.id, second.id]

    await repo.create_run(second.id, status="running")
    after_run = [session.id for session in await repo.list_sessions()]
    assert after_run[:2] == [second.id, first.id]


@pytest.mark.asyncio
async def test_chat_non_stream_batches_commits_per_turn(
    db_session,
    monkeypatch,
) -> None:
    provider_repo = ProviderRepository(db_session)
    await provider_repo.create(
        ProviderSettingCreate(
            provider="openai",
            api_key="secret",
            base_url="https://api.openai.com/v1",
            model="gpt-test",
        )
    )

    service = ChatService(db_session)
    commit_count = 0
    original_commit = db_session.commit

    async def counted_commit():  # type: ignore[no-untyped-def]
        nonlocal commit_count
        commit_count += 1
        return await original_commit()

    async def fake_run_agent_loop(  # type: ignore[no-untyped-def]
        provider,
        messages,
        allowed_tool_names=None,
        on_event=None,
    ):
        return (
            "final answer",
            [
                {
                    "tool": "echo",
                    "tool_display_name": "Echo",
                    "tool_activity_label": "Echoing input",
                    "tool_call_id": "tool-1",
                    "args": {"message": "hi"},
                    "result": "Echo: hi",
                    "success": True,
                }
            ],
        )

    monkeypatch.setattr(db_session, "commit", counted_commit)
    monkeypatch.setattr("app.services.chat_service.run_agent_loop", fake_run_agent_loop)

    await service.chat([ChatMessageIn(role="user", content="say hi")])

    assert commit_count == 3


@pytest.mark.asyncio
async def test_chat_stream_flushes_events_in_batches(
    db_session,
    monkeypatch,
) -> None:
    provider_repo = ProviderRepository(db_session)
    await provider_repo.create(
        ProviderSettingCreate(
            provider="openai",
            api_key="secret",
            base_url="https://api.openai.com/v1",
            model="gpt-test",
        )
    )

    service = ChatService(db_session)
    commit_count = 0
    original_commit = db_session.commit

    async def counted_commit():  # type: ignore[no-untyped-def]
        nonlocal commit_count
        commit_count += 1
        return await original_commit()

    async def fake_run_agent_loop(  # type: ignore[no-untyped-def]
        provider,
        messages,
        allowed_tool_names=None,
        on_event=None,
    ):
        if on_event is not None:
            await on_event(
                {
                    "type": "tool.started",
                    "tool_call_id": "tool-1",
                    "tool_name": "echo",
                    "tool_display_name": "Echo",
                    "tool_activity_label": "Echoing input",
                    "args": {"message": "hi"},
                }
            )
            await on_event(
                {
                    "type": "tool.finished",
                    "tool_call_id": "tool-1",
                    "tool_name": "echo",
                    "tool_display_name": "Echo",
                    "tool_activity_label": "Echoing input",
                    "args": {"message": "hi"},
                    "result": "Echo: hi",
                    "success": True,
                }
            )
        return (
            "final answer",
            [
                {
                    "tool": "echo",
                    "tool_display_name": "Echo",
                    "tool_activity_label": "Echoing input",
                    "tool_call_id": "tool-1",
                    "args": {"message": "hi"},
                    "result": "Echo: hi",
                    "success": True,
                }
            ],
        )

    monkeypatch.setattr(db_session, "commit", counted_commit)
    monkeypatch.setattr("app.services.chat_service.run_agent_loop", fake_run_agent_loop)

    event_iter, _sid = await service.chat_stream([ChatMessageIn(role="user", content="say hi")])
    _events = [event async for event in event_iter]

    assert commit_count == 4
