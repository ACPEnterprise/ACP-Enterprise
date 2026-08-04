import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.analytics.router import router as analytics_router
from app.api.health import router as health_router
from app.beacon.router import router as beacon_router
from app.core.config import settings
from app.customers.router import router as customers_router
from app.database.session import AsyncSessionFactory, engine
from app.dispatch.router import router as dispatch_router
from app.engineering_capacity.router import router as engineering_capacity_router
from app.engineering_control.mobile.router import router as mobile_engineering_router
from app.engineering_control.repository_authorization.router import (
    router as repository_authorizations_router,
)
from app.engineering_control.repository_operation.router import (
    router as repository_operations_router,
)
from app.engineering_control.review.router import router as engineering_reviews_router
from app.engineering_control.router import router as engineering_commands_router
from app.engineering_execution.controlled.router import (
    router as controlled_execution_router,
)
from app.engineering_execution.status.router import router as execution_status_router
from app.events.router import router as events_router
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.jobs.router import router as jobs_router
from app.platform.auth.router import router as auth_router
from app.platform.company.admin_router import router as company_admin_router
from app.platform.contracts.manifest import platform_contract_manifest
from app.platform.contracts.persistence import validate_persisted_permission_contract
from app.platform.contracts.router import (
    engineering_router as engineering_platform_contracts_router,
)
from app.platform.contracts.router import router as platform_contracts_router
from app.platform.permissions.catalog import permission_catalog
from app.platform.permissions.router import router as authorization_router
from app.platform.security.middleware import (
    SecurityHeadersMiddleware,
    TrustedProxyMiddleware,
)
from app.platform.users.identity_router import (
    administration_router as identity_administration_router,
)
from app.platform.users.identity_router import (
    self_service_router as identity_self_service_router,
)
from app.price_book.router import router as price_book_router
from app.scheduling.router import router as scheduling_router
from app.worker_control.transport.http.router import router as worker_transport_router

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    permission_catalog.validate()
    platform_contract_manifest.assert_expected(
        settings.platform_contract_expected_fingerprint
    )
    async with AsyncSessionFactory() as session:
        if settings.environment in {"preview", "production"}:
            reconciliation = await validate_persisted_permission_contract(session)
            if reconciliation.unknown_company_codes:
                logging.getLogger(__name__).warning(
                    "Unknown persisted Company permissions require reconciliation: %s",
                    ", ".join(reconciliation.unknown_company_codes),
                )
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
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
app.add_middleware(TrustedProxyMiddleware, configuration=settings)
app.add_middleware(SecurityHeadersMiddleware, configuration=settings)

app.include_router(health_router)
app.include_router(events_router)
app.include_router(analytics_router)
app.include_router(beacon_router)
app.include_router(customers_router)
app.include_router(auth_router)
app.include_router(authorization_router)
app.include_router(platform_contracts_router)
app.include_router(engineering_platform_contracts_router)
app.include_router(company_admin_router)
app.include_router(identity_self_service_router)
app.include_router(identity_administration_router)
app.include_router(scheduling_router)
app.include_router(jobs_router)
app.include_router(dispatch_router)
app.include_router(price_book_router)
app.include_router(engineering_commands_router)
app.include_router(engineering_reviews_router)
app.include_router(repository_authorizations_router)
app.include_router(repository_operations_router)
app.include_router(mobile_engineering_router)
app.include_router(engineering_capacity_router)
app.include_router(execution_status_router)
app.include_router(controlled_execution_router)
app.include_router(worker_transport_router)


@app.get("/", tags=["System"])
async def root() -> dict[str, str]:
    return {
        "application": settings.app_name,
        "version": settings.app_version,
        "message": "ACP Enterprise is online.",
    }
