from fastapi import APIRouter, Response, status

from app.core.config import settings
from app.database.session import engine
from app.platform.health.contracts import HealthState, SystemReadiness
from app.platform.health.service import PlatformHealthService

router = APIRouter(tags=["System"])


@router.get("/health/live")
async def liveness_check() -> dict[str, str]:
    return {
        "status": "alive",
        "application": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }


@router.get("/health", response_model=SystemReadiness)
@router.get("/health/ready", response_model=SystemReadiness)
async def health_check(response: Response) -> SystemReadiness:
    result = await PlatformHealthService(configuration=settings, engine=engine).inspect()
    if result.state is not HealthState.HEALTHY:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
