from typing import Any

from fastapi import APIRouter
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import settings
from app.database.session import engine

router = APIRouter(tags=["System"])


@router.get("/health")
async def health_check() -> dict[str, Any]:
    database_status = "disconnected"
    redis_status = "disconnected"

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        database_status = "connected"
    except Exception:
        database_status = "disconnected"

    redis_client = Redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )

    try:
        await redis_client.ping()
        redis_status = "connected"
    except Exception:
        redis_status = "disconnected"
    finally:
        await redis_client.aclose()

    healthy = database_status == "connected" and redis_status == "connected"

    return {
        "status": "healthy" if healthy else "degraded",
        "application": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "database": database_status,
        "redis": redis_status,
    }
