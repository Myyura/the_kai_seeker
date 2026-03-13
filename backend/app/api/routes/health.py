from fastapi import APIRouter

from app.config.settings import settings
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(app_name=settings.app_name)
