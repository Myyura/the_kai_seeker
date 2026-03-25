import json

import pytest

from app.repositories.conversation_repo import ConversationRepository
from app.repositories.provider_repo import ProviderRepository
from app.agent_runtime.types import ToolLoopResult
from app.schemas.chat import ChatMessageIn
from app.schemas.provider import ProviderSettingCreate
from app.services.conversation_service import ConversationService
from app.services.domain_config import domain_config


@pytest.mark.asyncio
async def test_existing_session_uses_persisted_history_as_source_of_truth(
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

    conversation_repo = ConversationRepository(db_session)
    chat_session = await conversation_repo.create_session(title="Existing Session")
    await conversation_repo.add_message(chat_session.id, "user", "persisted user")
    await conversation_repo.add_message(chat_session.id, "assistant", "persisted assistant")

    captured_messages = []

    async def fake_run_agent_loop(  # type: ignore[no-untyped-def]
        provider,
        messages,
        allowed_tool_names=None,
        on_event=None,
    ):
        captured_messages.extend(messages)
        return ToolLoopResult(assistant_text="final answer", turn_summary="final answer", tool_calls=[])

    service = ConversationService(db_session, tool_loop_runner=fake_run_agent_loop)
    content, _model, sid, tool_log = await service.chat(
        [
            ChatMessageIn(role="assistant", content="tampered assistant"),
            ChatMessageIn(role="user", content="latest user"),
        ],
        session_id=chat_session.id,
    )

    assert content == "final answer"
    assert sid == chat_session.id
    assert tool_log == []
    assert captured_messages[0].role == "system"
    assert "You are" in captured_messages[0].content
    assert captured_messages[1].role == "system"
    assert "## Response Format" in captured_messages[1].content
    assert captured_messages[2].role == "system"
    assert "## Session State" in captured_messages[2].content
    assert captured_messages[3].role == "system"
    assert "## Relevant Tool Artifacts" in captured_messages[3].content
    assert [(message.role, message.content) for message in captured_messages[4:6]] == [
        ("user", "persisted user"),
        ("assistant", "persisted assistant"),
    ]
    assert captured_messages[-1].role == "user"
    assert captured_messages[-1].content == "latest user"
    assert all("tampered assistant" not in message.content for message in captured_messages)

    stored_messages = await conversation_repo.get_messages(chat_session.id)
    assert [(message.role, message.content) for message in stored_messages] == [
        ("user", "persisted user"),
        ("assistant", "persisted assistant"),
        ("user", "latest user"),
        ("assistant", "final answer"),
    ]


@pytest.mark.asyncio
async def test_existing_session_builds_prompt_from_state_and_aggregated_tool_results(
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setitem(domain_config.profile, "recent_message_window", 1)

    provider_repo = ProviderRepository(db_session)
    await provider_repo.create(
        ProviderSettingCreate(
            provider="openai",
            api_key="secret",
            base_url="https://api.openai.com/v1",
            model="gpt-test",
        )
    )

    service = ConversationService(db_session)
    captured_turns: list[list[tuple[str, str]]] = []

    async def fake_run_agent_loop(  # type: ignore[no-untyped-def]
        provider,
        messages,
        allowed_tool_names=None,
        on_event=None,
    ):
        captured_turns.append([(message.role, message.content) for message in messages])
        if len(captured_turns) == 1:
            return ToolLoopResult(
                assistant_text="I found an official page.",
                turn_summary="Found an official source page.",
                tool_calls=[
                    {
                        "tool_name": "lookup_source",
                        "display_name": "Lookup Sources",
                        "activity_label": "Looking up official sources",
                        "call_id": "tool-1",
                        "arguments": {"query": "tokyo"},
                        "output": {
                            "ok": True,
                            "call_id": "tool-1",
                            "tool_name": "lookup_source",
                            "artifacts": [
                                {
                                    "kind": "source_lookup",
                                    "label": "Official source lookup for tokyo",
                                    "summary": "Matched sources: Official",
                                    "locator": {"query": "tokyo"},
                                    "replay": {
                                        "tool_name": "lookup_source",
                                        "arguments": {"query": "tokyo"},
                                    },
                                }
                            ],
                        },
                        "success": True,
                        "status": "completed",
                        "error_text": None,
                        "artifacts": [
                            {
                                "kind": "source_lookup",
                                "label": "Official source lookup for tokyo",
                                "summary": "Matched sources: Official",
                                "summary_format": "text",
                                "body_json": [
                                    {
                                        "id": "official",
                                        "name": "Official",
                                        "category": "admission",
                                        "urls": {"official": "https://example.com/official"},
                                    }
                                ],
                                "locator": {"query": "tokyo"},
                                "replay": {
                                    "tool_name": "lookup_source",
                                    "arguments": {"query": "tokyo"},
                                },
                                "search_text": "Official tokyo https://example.com/official",
                                "is_primary": True,
                            }
                        ],
                    }
                ],
            )
        return ToolLoopResult(
            assistant_text="Using the same official page as before.",
            turn_summary="Continued from the same official page.",
            tool_calls=[],
        )

    service = ConversationService(db_session, tool_loop_runner=fake_run_agent_loop)

    _content, _model, sid, _tool_log = await service.chat(
        [ChatMessageIn(role="user", content="Find the official source.")],
    )
    await service.chat(
        [ChatMessageIn(role="user", content="Open that official source and continue.")],
        session_id=sid,
    )

    assert len(captured_turns) == 2
    second_turn = captured_turns[1]
    assert second_turn[0][0] == "system"
    assert "You are" in second_turn[0][1]
    assert second_turn[1][0] == "system"
    assert "## Response Format" in second_turn[1][1]
    assert second_turn[2][0] == "system"
    assert "## Session State" in second_turn[2][1]
    assert "Find the official source." in second_turn[2][1]
    assert "Looked up official sources for query=tokyo." in second_turn[2][1]
    assert second_turn[3][0] == "system"
    assert "## Relevant Tool Artifacts" in second_turn[3][1]
    assert second_turn[4] == ("assistant", "I found an official page.")
    assert second_turn[-1] == ("user", "Open that official source and continue.")
    assert all(
        "<tool_call>" not in content and "<tool_result>" not in content
        for _, content in second_turn
    )
    assert any(
        role == "system"
        and "## Relevant Tool Artifacts" in content
        and "Official source lookup for tokyo" in content
        and "https://example.com/official" in content
        for role, content in second_turn
    )

    chat_session = await ConversationRepository(db_session).get_session(sid)
    assert chat_session is not None
    assert chat_session.short_term_memory is not None
    short_term_memory = json.loads(chat_session.short_term_memory.payload)
    assert short_term_memory["goal"]["core_user_need"] == "Find the official source."
    assert short_term_memory["goal"]["current_focus"] == "Open that official source and continue."
    assert short_term_memory["progress"]["pending_actions"] == []
    assert any(
        source.get("urls", {}).get("official") == "https://example.com/official"
        for source in short_term_memory["artifacts"]["sources"]
    )
