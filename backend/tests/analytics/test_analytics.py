from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.analytics.router import router as analytics_router
from app.analytics.service import AnalyticsService
from app.core.config import settings
from app.database.session import get_database_session
from app.events.models import BusinessEvent
from app.platform.auth.access_tokens import AccessTokenClaims
from app.platform.auth.dependencies import get_authenticated_context
from app.platform.auth.models import AuthenticationSession
from app.platform.auth.services import AuthenticatedContext, utc_now
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.permissions.codes import AnalyticsPermission
from app.platform.permissions.models import (
    MembershipRole,
    Permission,
    Role,
    RolePermission,
)
from app.platform.users.models import User, UserCredential


@dataclass(frozen=True)
class AnalyticsFixture:
    authenticated: AuthenticatedContext
    company_a_id: UUID
    company_b_id: UUID
    missing_permission_company_id: UUID
    suspended_company_id: UUID


@pytest_asyncio.fixture
async def analytics_database() -> AsyncIterator[
    tuple[AsyncEngine, async_sessionmaker[AsyncSession]]
]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield engine, factory
    finally:
        await engine.dispose()


async def seed_analytics_fixture(
    factory: async_sessionmaker[AsyncSession],
) -> AnalyticsFixture:
    suffix = uuid4().hex[:8].upper()
    now = utc_now()
    user = User(
        normalized_email=f"analytics-{suffix.lower()}@example.com",
        first_name="Analytics",
        last_name="Reader",
        display_name="Analytics Reader",
        status="active",
        authorization_version=1,
    )
    companies = [
        Company(
            name=f"Analytics {label}",
            code=f"AN{label}{suffix}",
            status="active",
            timezone=settings.business_timezone,
        )
        for label in ("A", "B", "NO", "SUSP")
    ]
    company_a, company_b, missing_permission_company, suspended_company = companies
    async with factory() as session, session.begin():
        session.add(user)
        await session.flush()
        credential = UserCredential(
            user_id=user.id,
            password_hash="$argon2id$analytics-test-only",
            credential_version=1,
        )
        authentication_session = AuthenticationSession(
            user_id=user.id,
            status="active",
            created_at=now,
            last_seen_at=now,
            absolute_expires_at=now + timedelta(days=30),
            idle_expires_at=now + timedelta(days=7),
            authentication_method="password",
            credential_version=1,
            authorization_version=1,
        )
        session.add_all([credential, authentication_session, *companies])
        await session.flush()
        memberships = [
            Membership(
                user_id=user.id,
                company_id=company.id,
                status="suspended" if company is suspended_company else "active",
                has_all_branch_access=False,
            )
            for company in companies
        ]
        session.add_all(memberships)
        permission = await session.scalar(
            select(Permission).where(Permission.code == AnalyticsPermission.READ)
        )
        if permission is None:
            permission = Permission(
                code=AnalyticsPermission.READ,
                name="Company Analytics Read",
                resource="analytics",
                action="read",
                status="active",
            )
            session.add(permission)
            await session.flush()
        for company, membership in zip(
            (company_a, company_b), memberships[:2], strict=True
        ):
            role = Role(
                company_id=company.id,
                code="ANALYTICS_READER",
                name="Analytics Reader",
                status="active",
                is_system=False,
            )
            session.add(role)
            await session.flush()
            session.add_all(
                [
                    RolePermission(
                        role_id=role.id,
                        permission_id=permission.id,
                        assigned_at=now,
                    ),
                    MembershipRole(
                        company_id=company.id,
                        membership_id=membership.id,
                        role_id=role.id,
                        assigned_at=now,
                    ),
                ]
            )

    claims = AccessTokenClaims(
        user_id=user.id,
        session_id=authentication_session.id,
        credential_version=1,
        authorization_version=1,
        issued_at=now,
        expires_at=now + timedelta(minutes=15),
        token_id=uuid4(),
    )
    return AnalyticsFixture(
        authenticated=AuthenticatedContext(user, authentication_session, claims),
        company_a_id=company_a.id,
        company_b_id=company_b.id,
        missing_permission_company_id=missing_permission_company.id,
        suspended_company_id=suspended_company.id,
    )


def event(
    *,
    company_id: UUID | None,
    event_type: str,
    occurred_at: datetime,
    payload: dict[str, object] | None = None,
) -> BusinessEvent:
    return BusinessEvent(
        event_type=event_type,
        entity_type="analytics_test",
        company_id=company_id,
        payload=payload or {},
        occurred_at=occurred_at,
    )


async def seed_events(
    factory: async_sessionmaker[AsyncSession], fixture: AnalyticsFixture
) -> None:
    business_zone = ZoneInfo(settings.business_timezone)
    today = datetime.now(business_zone).date()
    local_midnight = datetime.combine(today, time.min, tzinfo=business_zone)
    yesterday = local_midnight - timedelta(days=1)
    async with factory() as session, session.begin():
        session.add_all(
            [
                event(
                    company_id=fixture.company_a_id,
                    event_type=AnalyticsService.PAYMENT_RECEIVED,
                    occurred_at=(local_midnight + timedelta(minutes=15)).astimezone(
                        timezone.utc
                    ),
                    payload={"amount": "10.10"},
                ),
                event(
                    company_id=fixture.company_a_id,
                    event_type=AnalyticsService.ESTIMATE_APPROVED,
                    occurred_at=(
                        yesterday + timedelta(hours=23, minutes=45)
                    ).astimezone(timezone.utc),
                    payload={"approved_amount": "20.20"},
                ),
                event(
                    company_id=fixture.company_a_id,
                    event_type=AnalyticsService.CUSTOMER_CREATED,
                    occurred_at=(local_midnight + timedelta(hours=1)).astimezone(
                        timezone.utc
                    ),
                ),
                event(
                    company_id=fixture.company_a_id,
                    event_type=AnalyticsService.ESTIMATE_APPROVED,
                    occurred_at=(local_midnight + timedelta(minutes=30)).astimezone(
                        timezone.utc
                    ),
                    payload={"approved_amount": "30.30"},
                ),
                event(
                    company_id=fixture.company_a_id,
                    event_type=AnalyticsService.APPOINTMENT_BOOKED,
                    occurred_at=(local_midnight + timedelta(hours=2)).astimezone(
                        timezone.utc
                    ),
                ),
                event(
                    company_id=fixture.company_b_id,
                    event_type=AnalyticsService.PAYMENT_RECEIVED,
                    occurred_at=(local_midnight + timedelta(hours=3)).astimezone(
                        timezone.utc
                    ),
                    payload={"amount": "999999.99"},
                ),
                event(
                    company_id=fixture.company_b_id,
                    event_type=AnalyticsService.ESTIMATE_APPROVED,
                    occurred_at=(local_midnight + timedelta(hours=4)).astimezone(
                        timezone.utc
                    ),
                    payload={"amount": "888888.88"},
                ),
                event(
                    company_id=None,
                    event_type=AnalyticsService.PAYMENT_RECEIVED,
                    occurred_at=(local_midnight + timedelta(hours=5)).astimezone(
                        timezone.utc
                    ),
                    payload={"amount": "777777.77"},
                ),
            ]
        )


def build_app(
    factory: async_sessionmaker[AsyncSession],
    authenticated: AuthenticatedContext | None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(analytics_router)

    async def database_override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_database_session] = database_override
    if authenticated is not None:

        async def identity_override() -> AuthenticatedContext:
            return authenticated

        app.dependency_overrides[get_authenticated_context] = identity_override
    return app


@pytest.mark.asyncio
async def test_summary_authorization_and_company_isolation(
    analytics_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = analytics_database
    fixture = await seed_analytics_fixture(factory)
    await seed_events(factory, fixture)
    app = build_app(factory, fixture.authenticated)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/analytics/summary",
            headers={"X-Company-ID": str(fixture.company_a_id)},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["cash_collected"]["value"] == "10.10"
        assert payload["cash_collected"]["event_count"] == 1
        assert payload["booked_revenue"]["value"] == "30.30"
        assert payload["new_customers"]["value"] == 1
        assert payload["appointments_booked"]["value"] == 1
        assert payload["total_events"]["value"] == 4
        assert len(payload["recent_activity"]) == 4
        assert all(
            item["payload"].get("amount") not in {"999999.99", "777777.77"}
            for item in payload["recent_activity"]
        )

        missing = await client.get(
            "/api/v1/analytics/summary",
            headers={"X-Company-ID": str(fixture.missing_permission_company_id)},
        )
        assert missing.status_code == 403
        suspended = await client.get(
            "/api/v1/analytics/summary",
            headers={"X-Company-ID": str(fixture.suspended_company_id)},
        )
        assert suspended.status_code == 403

    unauthenticated_app = build_app(factory, None)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=unauthenticated_app),
        base_url="http://test",
    ) as client:
        unauthenticated = await client.get(
            "/api/v1/analytics/summary",
            headers={"X-Company-ID": str(fixture.company_a_id)},
        )
    assert unauthenticated.status_code == 401
