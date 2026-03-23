import logging
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy import text

from app.db.base import Base
from app.db.engine import engine

logger = logging.getLogger(__name__)


async def initialize_runtime_environment(*, ensure_db: bool = False) -> None:
    if ensure_db:
        async with engine.begin() as conn:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.run_sync(Base.metadata.create_all)
            await _migrate_legacy_short_term_memory(conn)

    from app.services.content_index import content_index

    content_index.load()

    from app.services.domain_config import domain_config

    domain_config.load()

    from app.tools.builtin import register_builtin_tools

    register_builtin_tools()

    from app.extensions import load_all_extensions

    backend_dir = Path(__file__).resolve().parent.parent
    load_all_extensions(backend_dir)

    from app.skills.registry import skill_registry
    from app.tools.registry import tool_registry

    logger.info(
        "Bootstrap complete with %d tools and %d skills",
        len(tool_registry.list_all()),
        len(skill_registry.list_all()),
    )


async def _migrate_legacy_short_term_memory(conn) -> None:  # type: ignore[no-untyped-def]
    table_names = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
    legacy_table = "chat_session_states"
    current_table = "chat_session_short_term_memories"
    if legacy_table not in table_names or current_table not in table_names:
        return

    result = await conn.execute(
        text(
            f"""
            INSERT INTO {current_table} (session_id, payload, created_at, updated_at)
            SELECT legacy.session_id, legacy.payload, legacy.created_at, legacy.updated_at
            FROM {legacy_table} AS legacy
            LEFT JOIN {current_table} AS current
              ON current.session_id = legacy.session_id
            WHERE current.session_id IS NULL
            """
        )
    )
    copied = result.rowcount or 0
    if copied > 0:
        logger.info("Copied %d legacy short-term memory rows into %s", copied, current_table)
