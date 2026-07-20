from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.analytics.router import router as analytics_router

from app.api.health import router as health_router
from app.core.config import settings
from app.customers.router import router as customers_router
from app.database.session import AsyncSessionFactory, engine
from app.events.router import router as events_router
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.auth.router import router as auth_router
from app.platform.company.admin_router import router as company_admin_router
from app.platform.permissions.catalog import permission_catalog
from app.platform.security.middleware import (
    SecurityHeadersMiddleware,
    TrustedProxyMiddleware,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    permission_catalog.validate()
    async with AsyncSessionFactory() as session:
        await BusinessEventService.publish(
            session=session,
            event_data=BusinessEventCreate(
                event_type=EventType.SYSTEM_STARTED,
                entity_type="system",
                payload={
                    "application": settings.app_name,
                    "version": settings.app_version,
                    "environment": settings.environment,
                },
            ),
        )

    yield

    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=("Real-time business operating system for home-service companies."),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TrustedProxyMiddleware, configuration=settings)
app.add_middleware(SecurityHeadersMiddleware, configuration=settings)

app.include_router(health_router)
app.include_router(events_router)
app.include_router(analytics_router)
app.include_router(customers_router)
app.include_router(auth_router)
app.include_router(company_admin_router)


@app.get("/", tags=["System"])
async def root() -> dict[str, str]:
    return {
        "application": settings.app_name,
        "version": settings.app_version,
        "message": "ACP Enterprise is online.",
    }
