from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import settings


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Real-time business operating system for home-service companies.",
)

app.include_router(health_router)


@app.get("/", tags=["System"])
async def root() -> dict[str, str]:
    return {
        "application": settings.app_name,
        "version": settings.app_version,
        "message": "ACP Enterprise is online.",
    }
