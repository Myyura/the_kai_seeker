import pytest

from app.agent_runtime.types import ToolLoopResult
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.provider_repo import ProviderRepository
from app.schemas.chat import ChatMessageIn
from app.schemas.provider import ProviderSettingCreate
from app.services.conversation_service import ConversationService


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
        return ToolLoopResult(
            assistant_text="final answer",
            turn_summary="Echoed the requested message.",
            tool_calls=[
                {
                    "tool_name": "echo",
                    "display_name": "Echo",
                    "activity_label": "Echoing input",
                    "call_id": "tool-1",
                    "arguments": {"message": "hi"},
                    "output": {
                        "ok": True,
                        "call_id": "tool-1",
                        "tool_name": "echo",
                        "artifacts": [
                            {
                                "kind": "tool_output_text",
                                "label": "echo",
                                "summary": "Echo: hi",
                                "locator": {"tool_name": "echo"},
                                "replay": {"tool_name": "echo", "arguments": {"message": "hi"}},
                            }
                        ],
                    },
                    "success": True,
                    "status": "completed",
                    "error_text": None,
                    "artifacts": [
                        {
                            "kind": "tool_output_text",
                            "label": "echo",
                            "summary": "Echo: hi",
                            "summary_format": "text",
                            "body_text": "Echo: hi",
                            "body_json": None,
                            "locator": {"tool_name": "echo"},
                            "replay": {"tool_name": "echo", "arguments": {"message": "hi"}},
                            "search_text": "echo Echo: hi",
                            "is_primary": True,
                        }
                    ],
                }
            ],
        )

    service = ConversationService(db_session, tool_loop_runner=fake_run_agent_loop)
    monkeypatch.setattr(db_session, "commit", counted_commit)

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
        return ToolLoopResult(
            assistant_text="final answer",
            turn_summary="Echoed the requested message.",
            tool_calls=[
                {
                    "tool_name": "echo",
                    "display_name": "Echo",
                    "activity_label": "Echoing input",
                    "call_id": "tool-1",
                    "arguments": {"message": "hi"},
                    "output": {
                        "ok": True,
                        "call_id": "tool-1",
                        "tool_name": "echo",
                        "artifacts": [
                            {
                                "kind": "tool_output_text",
                                "label": "echo",
                                "summary": "Echo: hi",
                                "locator": {"tool_name": "echo"},
                                "replay": {"tool_name": "echo", "arguments": {"message": "hi"}},
                            }
                        ],
                    },
                    "success": True,
                    "status": "completed",
                    "error_text": None,
                    "artifacts": [
                        {
                            "kind": "tool_output_text",
                            "label": "echo",
                            "summary": "Echo: hi",
                            "summary_format": "text",
                            "body_text": "Echo: hi",
                            "body_json": None,
                            "locator": {"tool_name": "echo"},
                            "replay": {"tool_name": "echo", "arguments": {"message": "hi"}},
                            "search_text": "echo Echo: hi",
                            "is_primary": True,
                        }
                    ],
                }
            ],
        )

    service = ConversationService(db_session, tool_loop_runner=fake_run_agent_loop)
    monkeypatch.setattr(db_session, "commit", counted_commit)

    event_iter, _sid = await service.chat_stream([ChatMessageIn(role="user", content="say hi")])
    _events = [event async for event in event_iter]

    assert commit_count == 3
