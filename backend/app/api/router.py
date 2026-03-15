from fastapi import APIRouter

from app.api.routes import chat, content, files, health, pdf, providers, settings

api_router = APIRouter(prefix="/api")

api_router.include_router(health.router, tags=["health"])
api_router.include_router(providers.router, prefix="/providers", tags=["providers"])
api_router.include_router(content.router, prefix="/content", tags=["content"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])

api_router.include_router(files.router, prefix="/files", tags=["files"])
api_router.include_router(pdf.router, prefix="/pdf", tags=["pdf"])
