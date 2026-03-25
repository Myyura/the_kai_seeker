import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

import app.models  # noqa: F401
from app.bootstrap import _drop_deprecated_tables, _migrate_legacy_short_term_memory
from app.db.base import Base


@pytest.mark.asyncio
async def test_bootstrap_migrates_legacy_short_term_memory_rows() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    CREATE TABLE chat_session_states (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id INTEGER NOT NULL UNIQUE,
                        payload TEXT NOT NULL DEFAULT '{}',
                        created_at DATETIME,
                        updated_at DATETIME
                    )
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO chat_session_states (session_id, payload, created_at, updated_at)
                    VALUES (1, '{"goal":{"core_user_need":"legacy"}}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                )
            )
            await conn.run_sync(Base.metadata.create_all)

            await _migrate_legacy_short_term_memory(conn)

            rows = (
                await conn.execute(
                    text(
                        """
                        SELECT session_id, payload
                        FROM chat_session_short_term_memories
                        ORDER BY session_id
                        """
                    )
                )
            ).all()

        assert rows == [(1, '{"goal":{"core_user_need":"legacy"}}')]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_bootstrap_drops_deprecated_runtime_tables() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE chat_run_events (id INTEGER PRIMARY KEY)"))
            await conn.execute(text("CREATE TABLE chat_run_debug_payloads (id INTEGER PRIMARY KEY)"))
            await conn.execute(text("CREATE TABLE chat_session_states (id INTEGER PRIMARY KEY)"))

            await _drop_deprecated_tables(conn)

            rows = (
                await conn.execute(
                    text(
                        """
                        SELECT name
                        FROM sqlite_master
                        WHERE type = 'table'
                          AND name IN ('chat_run_events', 'chat_run_debug_payloads', 'chat_session_states')
                        ORDER BY name
                        """
                    )
                )
            ).all()

        assert rows == []
    finally:
        await engine.dispose()
