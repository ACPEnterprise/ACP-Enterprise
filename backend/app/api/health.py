from typing import Any

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


@router.get("/health/ready", response_model=SystemReadiness)
async def readiness_check(response: Response) -> SystemReadiness:
    result = await PlatformHealthService(configuration=settings, engine=engine).inspect()
    if result.state is not HealthState.HEALTHY:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result


@router.get("/health")
async def health_check(response: Response) -> dict[str, Any]:
    """Preserve the accepted compact health contract for existing consumers."""
    result = await PlatformHealthService(configuration=settings, engine=engine).inspect()
    by_name = {component.component: component for component in result.components}
    if result.state is not HealthState.HEALTHY:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "healthy" if result.state is HealthState.HEALTHY else "degraded",
        "application": result.application,
        "version": result.version,
        "environment": result.environment,
        "database": (
            "connected"
            if by_name["database"].state is HealthState.HEALTHY
            else "disconnected"
        ),
        "redis": (
            "connected"
            if by_name["redis"].state is HealthState.HEALTHY
            else "disconnected"
        ),
    }
