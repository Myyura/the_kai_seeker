"""
The Kai Seeker (解を求める者) — Application Entry Point
https://github.com/Myyura/the_kai_seeker
Licensed under AGPL-3.0
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.router import api_router
from app.config.settings import settings
from app.db.base import Base
from app.db.engine import engine
import app.models  # noqa: F401  — register ORM models before create_all

PROJECT_FINGERPRINT = "The Kai Seeker/0.1.0 (AGPL-3.0; github.com/Myyura/the_kai_seeker)"

logger = logging.getLogger(__name__)

STARTUP_BANNER = r"""
  ╔══════════════════════════════════════════════════════╗
  ║       T H E   K A I   S E E K E R                    ║
  ║       Countless questions without, one Kai within.   ║
  ║       AGPL-3.0 · github.com/Myyura/the_kai_seeker    ║
  ╚══════════════════════════════════════════════════════╝
"""


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    print(STARTUP_BANNER)
    logger.info("Starting %s …", settings.app_name)

    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database ready")

    content_path = settings.content_path
    if content_path.exists():
        logger.info("Content directory: %s", content_path)
    else:
        logger.warning("Content directory not found: %s", content_path)

    from app.services.content_index import content_index
    content_index.load()

    from app.services.domain_config import domain_config
    domain_config.load()
    logger.info("Domain: %s (%s), %d sources",
                domain_config.domain_name, domain_config.profile.get("id", "?"),
                len(domain_config.sources))

    from app.tools.builtin import register_builtin_tools
    register_builtin_tools()
    from app.tools.registry import tool_registry
    logger.info("Registered %d tools: %s", len(tool_registry.list_all()),
                [t.name for t in tool_registry.list_all()])

    from pathlib import Path
    from app.extensions import load_all_extensions
    backend_dir = Path(__file__).resolve().parent.parent
    ext_summary = load_all_extensions(backend_dir)
    from app.skills.registry import skill_registry
    logger.info("Registered %d skills: %s", len(skill_registry.list_all()),
                [s.name for s in skill_registry.list_all()])

    yield

    await engine.dispose()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_server_header(request: Request, call_next):  # type: ignore[no-untyped-def]
        response: Response = await call_next(request)
        response.headers["X-Powered-By"] = PROJECT_FINGERPRINT
        return response

    app.include_router(api_router)

    static_path = settings.static_path
    if static_path.exists() and static_path.is_dir():
        app.mount("/", StaticFiles(directory=str(static_path), html=True), name="static")
        logger.info("Serving frontend from %s", static_path)
    else:
        logger.info("No frontend build at %s — API-only mode", static_path)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
