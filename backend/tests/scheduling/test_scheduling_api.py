from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.analytics.service import AnalyticsService
from app.core.config import settings
from app.customers.models import Customer, ServiceLocation
from app.database.session import get_database_session, get_security_database_session
from app.events.models import BusinessEvent
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.auth.models import AuthenticationSession
from app.platform.auth.services import access_token_service, utc_now
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership, MembershipBranchAccess
from app.platform.company.models import Company
from app.platform.permissions.codes import SchedulingPermission
from app.platform.permissions.catalog_sync import PermissionCatalogSyncService
from app.platform.permissions.models import (
    MembershipRole,
    Permission,
    Role,
    RolePermission,
)
from app.platform.users.models import User, UserCredential
from app.scheduling.models import (
    Appointment,
    AppointmentCapacityReservation,
    BranchSchedulingCalendar,
    BranchSchedulingException,
    BranchSchedulingWeeklyInterval,
)
from app.scheduling.router import router


@dataclass(frozen=True)
class SchedulingApiFixture:
    factory: async_sessionmaker[AsyncSession]
    app: FastAPI
    company_id: UUID
    branch_id: UUID
    unauthorized_branch_id: UUID
    customer_id: UUID
    location_id: UUID
    other_customer_id: UUID
    other_location_id: UUID
    token: str
    denied_token: str
    start: datetime
    application_sessions: list[AsyncSession]
    security_sessions: list[AsyncSession]


async def _add_actor(
    session: AsyncSession,
    *,
    company: Company,
    branch: Branch,
    permission: Permission,
    has_permission: bool,
    suffix: str,
) -> tuple[User, AuthenticationSession]:
    now = utc_now()
    user = User(
        normalized_email=f"scheduler-{suffix}@example.test",
        first_name="Scheduling",
        last_name="Operator",
        display_name="Scheduling Operator",
        status="active",
        authorization_version=1,
    )
    session.add(user)
    await session.flush()
    credential = UserCredential(
        user_id=user.id,
        password_hash="$argon2id$api-test-only-hash",
        password_changed_at=now,
        credential_version=1,
    )
    membership = Membership(
        user_id=user.id,
        company_id=company.id,
        status="active",
        has_all_branch_access=False,
        default_branch_id=branch.id,
        invited_at=now,
        accepted_at=now,
    )
    auth_session = AuthenticationSession(
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
    session.add_all([credential, membership, auth_session])
    await session.flush()
    session.add(
        MembershipBranchAccess(
            membership_id=membership.id,
            branch_id=branch.id,
            assigned_at=now,
        )
    )
    if has_permission:
        role = Role(
            company_id=company.id,
            code=f"SCHEDULER_{suffix.upper()}",
            name="Scheduler",
            status="active",
            is_system=False,
            created_by_user_id=user.id,
            updated_by_user_id=user.id,
        )
        session.add(role)
        await session.flush()
        session.add_all(
            [
                RolePermission(
                    role_id=role.id,
                    permission_id=permission.id,
                    assigned_by_user_id=user.id,
                ),
                MembershipRole(
                    company_id=company.id,
                    membership_id=membership.id,
                    role_id=role.id,
                    assigned_by_user_id=user.id,
                ),
            ]
        )
    return user, auth_session


@pytest_asyncio.fixture
async def scheduling_api() -> AsyncIterator[SchedulingApiFixture]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex[:10]
    now = utc_now()
    async with factory() as session:
        await PermissionCatalogSyncService().synchronize(session)
    async with factory() as session, session.begin():
        company = Company(
            name=f"Scheduling API {suffix}",
            code=f"SAPI{suffix.upper()}",
            status="active",
            timezone="America/New_York",
        )
        other_company = Company(
            name=f"Scheduling Other {suffix}",
            code=f"SAPO{suffix.upper()}",
            status="active",
            timezone="America/New_York",
        )
        branch = Branch(
            company=company,
            name="Authorized Branch",
            code=f"AB{suffix.upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        unauthorized_branch = Branch(
            company=company,
            name="Unauthorized Branch",
            code=f"UB{suffix.upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=False,
        )
        customer = Customer(
            company=company,
            customer_number=f"CUS-{int(uuid4().hex[:8], 16):010d}",
            status="active",
            customer_type="residential",
            display_name="Scheduling Customer",
            preferred_contact_method="phone",
            normalized_name=f"scheduling customer {suffix}",
        )
        other_customer = Customer(
            company=other_company,
            customer_number=f"CUS-{int(uuid4().hex[:8], 16):010d}",
            status="active",
            customer_type="residential",
            display_name="Other Customer",
            preferred_contact_method="phone",
            normalized_name=f"other customer {suffix}",
        )
        location = ServiceLocation(
            customer=customer,
            address="100 API Street",
            city="Testville",
            state="NY",
            postal_code="10001",
            country="US",
            normalized_address=f"100 api street {suffix}",
            active=True,
        )
        other_location = ServiceLocation(
            customer=other_customer,
            address="200 Other Street",
            city="Testville",
            state="NY",
            postal_code="10002",
            country="US",
            normalized_address=f"200 other street {suffix}",
            active=True,
        )
        session.add_all(
            [
                company,
                other_company,
                branch,
                unauthorized_branch,
                customer,
                other_customer,
                location,
                other_location,
            ]
        )
        await session.flush()
        canonical_permission = await session.scalar(
            select(Permission).where(Permission.code == SchedulingPermission.MANAGE)
        )
        assert canonical_permission is not None
        user, auth_session = await _add_actor(
            session,
            company=company,
            branch=branch,
            permission=canonical_permission,
            has_permission=True,
            suffix=f"allowed-{suffix}",
        )
        denied_user, denied_session = await _add_actor(
            session,
            company=company,
            branch=branch,
            permission=canonical_permission,
            has_permission=False,
            suffix=f"denied-{suffix}",
        )
        for target_branch in (branch, unauthorized_branch):
            calendar = BranchSchedulingCalendar(
                company_id=company.id,
                branch_id=target_branch.id,
                booking_horizon_days=180,
                minimum_notice_minutes=0,
                slot_interval_minutes=30,
                default_capacity_units=Decimal("2.00"),
            )
            session.add(calendar)
            await session.flush()
            session.add_all(
                BranchSchedulingWeeklyInterval(
                    calendar_id=calendar.id,
                    day_of_week=day,
                    start_minute=8 * 60,
                    end_minute=18 * 60,
                    capacity_units=Decimal("2.00"),
                )
                for day in range(7)
            )
    token, _ = access_token_service.issue(
        user_id=user.id,
        session_id=auth_session.id,
        credential_version=1,
        authorization_version=1,
        now=now,
    )
    denied_token, _ = access_token_service.issue(
        user_id=denied_user.id,
        session_id=denied_session.id,
        credential_version=1,
        authorization_version=1,
        now=now,
    )
    application_sessions: list[AsyncSession] = []
    security_sessions: list[AsyncSession] = []
    app = FastAPI()
    app.include_router(router)

    async def application_session_override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            application_sessions.append(session)
            yield session

    async def security_session_override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            security_sessions.append(session)
            yield session

    app.dependency_overrides[get_database_session] = application_session_override
    app.dependency_overrides[get_security_database_session] = security_session_override
    local_start = now.astimezone(ZoneInfo("America/New_York")) + timedelta(days=2)
    start = local_start.replace(hour=10, minute=0, second=0, microsecond=0).astimezone(
        timezone.utc
    )
    try:
        yield SchedulingApiFixture(
            factory=factory,
            app=app,
            company_id=company.id,
            branch_id=branch.id,
            unauthorized_branch_id=unauthorized_branch.id,
            customer_id=customer.id,
            location_id=location.id,
            other_customer_id=other_customer.id,
            other_location_id=other_location.id,
            token=token,
            denied_token=denied_token,
            start=start,
            application_sessions=application_sessions,
            security_sessions=security_sessions,
        )
    finally:
        await engine.dispose()


def _headers(
    fixture: SchedulingApiFixture, *, token: str | None = None
) -> dict[str, str]:
    headers = {"X-Company-ID": str(fixture.company_id)}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _create_payload(
    fixture: SchedulingApiFixture,
    *,
    start: datetime | None = None,
    capacity: str = "1.00",
) -> dict[str, object]:
    window_start = start or fixture.start
    return {
        "branch_id": str(fixture.branch_id),
        "customer_id": str(fixture.customer_id),
        "service_location_id": str(fixture.location_id),
        "arrival_window_start_at": window_start.isoformat(),
        "arrival_window_end_at": (window_start + timedelta(hours=1)).isoformat(),
        "expected_duration_minutes": 60,
        "capacity_units": capacity,
    }


def test_scheduling_openapi_registers_versioned_authenticated_operations() -> None:
    app = FastAPI()
    app.include_router(router)
    schema = app.openapi()
    paths = schema["paths"]
    assert "/api/v1/scheduling/appointments" in paths
    assert "/api/v1/scheduling/appointments/{appointment_id}/cancel" in paths
    assert "/api/v1/scheduling/appointments/{appointment_id}/reschedule" in paths
    for path, method in (
        ("/api/v1/scheduling/appointments", "post"),
        ("/api/v1/scheduling/appointments/{appointment_id}/cancel", "post"),
        ("/api/v1/scheduling/appointments/{appointment_id}/reschedule", "post"),
    ):
        operation = paths[path][method]
        assert operation["summary"]
        assert operation["security"] == [{"HTTPBearer": []}]


async def _post(
    fixture: SchedulingApiFixture,
    path: str,
    payload: dict[str, object],
    *,
    token: str | None,
    raise_app_exceptions: bool = True,
) -> httpx.Response:
    transport = httpx.ASGITransport(
        app=fixture.app, raise_app_exceptions=raise_app_exceptions
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            path, json=payload, headers=_headers(fixture, token=token)
        )


async def _seed_unauthorized_branch_appointment(
    fixture: SchedulingApiFixture,
) -> UUID:
    appointment_id = uuid4()
    now = utc_now()
    async with fixture.factory() as session, session.begin():
        session.add(
            Appointment(
                id=appointment_id,
                company_id=fixture.company_id,
                branch_id=fixture.unauthorized_branch_id,
                appointment_number=f"APT-{int(uuid4().hex[:6], 16):08d}",
                customer_id=fixture.customer_id,
                service_location_id=fixture.location_id,
                status="scheduled",
                arrival_window_start_at=fixture.start,
                arrival_window_end_at=fixture.start + timedelta(hours=1),
                expected_duration_minutes=60,
                scheduling_timezone="America/New_York",
                concurrency_version=1,
                created_at=now,
                updated_at=now,
            )
        )
        await session.flush()
        session.add(
            AppointmentCapacityReservation(
                company_id=fixture.company_id,
                branch_id=fixture.unauthorized_branch_id,
                appointment_id=appointment_id,
                reserved_start_at=fixture.start,
                reserved_end_at=fixture.start + timedelta(hours=1),
                capacity_units=Decimal("1.00"),
                created_at=now,
                updated_at=now,
            )
        )
    return appointment_id


async def _seed_draft_appointment(fixture: SchedulingApiFixture) -> UUID:
    appointment_id = uuid4()
    now = utc_now()
    async with fixture.factory() as session, session.begin():
        session.add(
            Appointment(
                id=appointment_id,
                company_id=fixture.company_id,
                branch_id=fixture.branch_id,
                appointment_number=f"APT-{int(uuid4().hex[:6], 16):08d}",
                customer_id=fixture.customer_id,
                service_location_id=fixture.location_id,
                status="draft",
                arrival_window_start_at=None,
                arrival_window_end_at=None,
                expected_duration_minutes=None,
                scheduling_timezone="America/New_York",
                concurrency_version=1,
                created_at=now,
                updated_at=now,
            )
        )
    return appointment_id


@pytest.mark.asyncio
async def test_create_appointment_uses_real_security_and_transaction_contract(
    scheduling_api: SchedulingApiFixture,
) -> None:
    response = await _post(
        scheduling_api,
        "/api/v1/scheduling/appointments",
        _create_payload(scheduling_api),
        token=scheduling_api.token,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["appointment_number"] == "APT-000001"
    assert body["status"] == "scheduled"
    assert body["concurrency_version"] == 1
    assert Decimal(body["capacity_units"]) == Decimal("1.00")
    appointment_id = UUID(body["id"])
    async with scheduling_api.factory() as session:
        events = tuple(
            (
                await session.scalars(
                    select(BusinessEvent)
                    .where(BusinessEvent.entity_id == appointment_id)
                    .order_by(BusinessEvent.event_type)
                )
            ).all()
        )
        analytics = await AnalyticsService.get_today_summary(
            session, company_id=scheduling_api.company_id
        )
    assert [event.event_type for event in events] == [
        "appointment.booked",
        "appointment.created",
    ]
    assert events[0].occurred_at == events[1].occurred_at
    assert analytics.appointments_booked.value == 1
    assert len(scheduling_api.application_sessions) == 1
    assert len(scheduling_api.security_sessions) == 1
    assert (
        scheduling_api.application_sessions[0]
        is not scheduling_api.security_sessions[0]
    )


@pytest.mark.asyncio
async def test_create_requires_authentication_permission_and_valid_schema(
    scheduling_api: SchedulingApiFixture,
) -> None:
    path = "/api/v1/scheduling/appointments"
    payload = _create_payload(scheduling_api)
    unauthenticated = await _post(scheduling_api, path, payload, token=None)
    denied = await _post(
        scheduling_api, path, payload, token=scheduling_api.denied_token
    )
    malformed = await _post(
        scheduling_api,
        path,
        {**payload, "arrival_window_start_at": "2026-07-22T10:00:00"},
        token=scheduling_api.token,
    )
    unsupported = await _post(
        scheduling_api,
        path,
        {**payload, "unsupported": True},
        token=scheduling_api.token,
    )
    assert unauthenticated.status_code == 401
    assert denied.status_code == 403
    assert malformed.status_code == 422
    assert unsupported.status_code == 422


@pytest.mark.asyncio
async def test_create_conceals_tenant_and_branch_references(
    scheduling_api: SchedulingApiFixture,
) -> None:
    path = "/api/v1/scheduling/appointments"
    base = _create_payload(scheduling_api)
    unauthorized_branch = await _post(
        scheduling_api,
        path,
        {**base, "branch_id": str(scheduling_api.unauthorized_branch_id)},
        token=scheduling_api.token,
    )
    concealed_customer = await _post(
        scheduling_api,
        path,
        {
            **base,
            "customer_id": str(scheduling_api.other_customer_id),
            "service_location_id": str(scheduling_api.other_location_id),
        },
        token=scheduling_api.token,
    )
    concealed_location = await _post(
        scheduling_api,
        path,
        {**base, "service_location_id": str(scheduling_api.other_location_id)},
        token=scheduling_api.token,
    )
    assert unauthorized_branch.status_code == 404
    assert concealed_customer.status_code == 404
    assert concealed_location.status_code == 404
    assert all(
        response.json()["detail"] == "Scheduling resource was not found."
        for response in (
            unauthorized_branch,
            concealed_customer,
            concealed_location,
        )
    )


@pytest.mark.asyncio
async def test_create_maps_calendar_and_capacity_conflicts(
    scheduling_api: SchedulingApiFixture,
) -> None:
    path = "/api/v1/scheduling/appointments"
    first = await _post(
        scheduling_api,
        path,
        _create_payload(scheduling_api, capacity="2.00"),
        token=scheduling_api.token,
    )
    capacity_conflict = await _post(
        scheduling_api,
        path,
        _create_payload(scheduling_api),
        token=scheduling_api.token,
    )
    closed_start = scheduling_api.start + timedelta(days=1)
    async with scheduling_api.factory() as session, session.begin():
        calendar = await session.scalar(
            select(BranchSchedulingCalendar).where(
                BranchSchedulingCalendar.company_id == scheduling_api.company_id,
                BranchSchedulingCalendar.branch_id == scheduling_api.branch_id,
            )
        )
        assert calendar is not None
        session.add(
            BranchSchedulingException(
                calendar_id=calendar.id,
                exception_date=closed_start.astimezone(
                    ZoneInfo("America/New_York")
                ).date(),
                is_closed=True,
                reason_code="test_closure",
            )
        )
    calendar_conflict = await _post(
        scheduling_api,
        path,
        _create_payload(scheduling_api, start=closed_start),
        token=scheduling_api.token,
    )
    assert first.status_code == 201
    assert capacity_conflict.status_code == 409
    assert calendar_conflict.status_code == 409


@pytest.mark.asyncio
async def test_cancellation_is_versioned_idempotent_and_releases_capacity(
    scheduling_api: SchedulingApiFixture,
) -> None:
    created = await _post(
        scheduling_api,
        "/api/v1/scheduling/appointments",
        _create_payload(scheduling_api),
        token=scheduling_api.token,
    )
    appointment_id = UUID(created.json()["id"])
    path = f"/api/v1/scheduling/appointments/{appointment_id}/cancel"
    payload = {"expected_version": 1, "reason_code": "customer_request"}
    cancelled = await _post(scheduling_api, path, payload, token=scheduling_api.token)
    repeated = await _post(scheduling_api, path, payload, token=scheduling_api.token)
    different_reason = await _post(
        scheduling_api,
        path,
        {"expected_version": 1, "reason_code": "scheduling_conflict"},
        token=scheduling_api.token,
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["concurrency_version"] == 2
    assert repeated.status_code == 200
    assert repeated.json()["concurrency_version"] == 2
    assert different_reason.status_code == 409
    async with scheduling_api.factory() as session:
        reservation = await session.scalar(
            select(AppointmentCapacityReservation).where(
                AppointmentCapacityReservation.appointment_id == appointment_id
            )
        )
        event_count = await session.scalar(
            select(func.count())
            .select_from(BusinessEvent)
            .where(
                BusinessEvent.entity_id == appointment_id,
                BusinessEvent.event_type == EventType.APPOINTMENT_CANCELLED.value,
            )
        )
    assert reservation is not None and reservation.released_at is not None
    assert event_count == 1


@pytest.mark.asyncio
async def test_draft_without_reservation_cancels_with_nullable_response(
    scheduling_api: SchedulingApiFixture,
) -> None:
    appointment_id = await _seed_draft_appointment(scheduling_api)
    path = f"/api/v1/scheduling/appointments/{appointment_id}/cancel"
    payload = {"expected_version": 1, "reason_code": "customer_request"}

    cancelled = await _post(scheduling_api, path, payload, token=scheduling_api.token)
    repeated = await _post(scheduling_api, path, payload, token=scheduling_api.token)

    assert cancelled.status_code == 200
    assert repeated.status_code == 200
    for response in (cancelled, repeated):
        body = response.json()
        assert body["status"] == "cancelled"
        assert body["concurrency_version"] == 2
        assert body["arrival_window_start_at"] is None
        assert body["arrival_window_end_at"] is None
        assert body["expected_duration_minutes"] is None
        assert body["capacity_units"] is None

    async with scheduling_api.factory() as session:
        appointment = await session.get(Appointment, appointment_id)
        event_count = await session.scalar(
            select(func.count())
            .select_from(BusinessEvent)
            .where(
                BusinessEvent.entity_id == appointment_id,
                BusinessEvent.event_type == EventType.APPOINTMENT_CANCELLED.value,
            )
        )
    assert appointment is not None and appointment.status == "cancelled"
    assert appointment.concurrency_version == 2
    assert event_count == 1


@pytest.mark.asyncio
async def test_cancellation_maps_stale_concealed_and_authorization_failures(
    scheduling_api: SchedulingApiFixture,
) -> None:
    created = await _post(
        scheduling_api,
        "/api/v1/scheduling/appointments",
        _create_payload(scheduling_api),
        token=scheduling_api.token,
    )
    appointment_id = created.json()["id"]
    path = f"/api/v1/scheduling/appointments/{appointment_id}/cancel"
    payload = {"expected_version": 99, "reason_code": "customer_request"}
    stale = await _post(scheduling_api, path, payload, token=scheduling_api.token)
    concealed = await _post(
        scheduling_api,
        f"/api/v1/scheduling/appointments/{uuid4()}/cancel",
        {"expected_version": 1, "reason_code": "customer_request"},
        token=scheduling_api.token,
    )
    unauthenticated = await _post(scheduling_api, path, payload, token=None)
    denied = await _post(
        scheduling_api, path, payload, token=scheduling_api.denied_token
    )
    unauthorized_branch_id = await _seed_unauthorized_branch_appointment(scheduling_api)
    unauthorized_branch = await _post(
        scheduling_api,
        f"/api/v1/scheduling/appointments/{unauthorized_branch_id}/cancel",
        {"expected_version": 1, "reason_code": "customer_request"},
        token=scheduling_api.token,
    )
    assert stale.status_code == 409
    assert concealed.status_code == 404
    assert unauthenticated.status_code == 401
    assert denied.status_code == 403
    assert unauthorized_branch.status_code == 404


@pytest.mark.asyncio
async def test_reschedule_moves_reservation_and_stages_event(
    scheduling_api: SchedulingApiFixture,
) -> None:
    created = await _post(
        scheduling_api,
        "/api/v1/scheduling/appointments",
        _create_payload(scheduling_api),
        token=scheduling_api.token,
    )
    appointment_id = UUID(created.json()["id"])
    replacement = scheduling_api.start + timedelta(days=1)
    response = await _post(
        scheduling_api,
        f"/api/v1/scheduling/appointments/{appointment_id}/reschedule",
        {
            "expected_version": 1,
            "arrival_window_start_at": replacement.isoformat(),
            "arrival_window_end_at": (replacement + timedelta(hours=1)).isoformat(),
            "expected_duration_minutes": 90,
            "capacity_units": "1.50",
            "reason_code": "customer_request",
        },
        token=scheduling_api.token,
    )
    assert response.status_code == 200
    assert response.json()["concurrency_version"] == 2
    assert response.json()["reschedule_count"] == 1
    assert Decimal(response.json()["capacity_units"]) == Decimal("1.50")
    async with scheduling_api.factory() as session:
        reservation = await session.scalar(
            select(AppointmentCapacityReservation).where(
                AppointmentCapacityReservation.appointment_id == appointment_id
            )
        )
        event_count = await session.scalar(
            select(func.count())
            .select_from(BusinessEvent)
            .where(
                BusinessEvent.entity_id == appointment_id,
                BusinessEvent.event_type == EventType.APPOINTMENT_RESCHEDULED.value,
            )
        )
    assert reservation is not None
    assert reservation.reserved_start_at == replacement
    assert event_count == 1


@pytest.mark.asyncio
async def test_reschedule_conflict_preserves_original_and_maps_failures(
    scheduling_api: SchedulingApiFixture,
) -> None:
    source = await _post(
        scheduling_api,
        "/api/v1/scheduling/appointments",
        _create_payload(scheduling_api),
        token=scheduling_api.token,
    )
    source_id = UUID(source.json()["id"])
    destination = scheduling_api.start + timedelta(days=1)
    blocker = await _post(
        scheduling_api,
        "/api/v1/scheduling/appointments",
        _create_payload(scheduling_api, start=destination, capacity="2.00"),
        token=scheduling_api.token,
    )
    assert blocker.status_code == 201
    path = f"/api/v1/scheduling/appointments/{source_id}/reschedule"
    payload = {
        "expected_version": 1,
        "arrival_window_start_at": destination.isoformat(),
        "arrival_window_end_at": (destination + timedelta(hours=1)).isoformat(),
        "expected_duration_minutes": 60,
        "capacity_units": "1.00",
        "reason_code": "operational_adjustment",
    }
    conflict = await _post(scheduling_api, path, payload, token=scheduling_api.token)
    stale = await _post(
        scheduling_api,
        path,
        {**payload, "expected_version": 99},
        token=scheduling_api.token,
    )
    concealed = await _post(
        scheduling_api,
        f"/api/v1/scheduling/appointments/{uuid4()}/reschedule",
        payload,
        token=scheduling_api.token,
    )
    unauthorized_branch_id = await _seed_unauthorized_branch_appointment(scheduling_api)
    unauthorized_branch = await _post(
        scheduling_api,
        f"/api/v1/scheduling/appointments/{unauthorized_branch_id}/reschedule",
        payload,
        token=scheduling_api.token,
    )
    assert conflict.status_code == 409
    assert stale.status_code == 409
    assert concealed.status_code == 404
    assert unauthorized_branch.status_code == 404
    async with scheduling_api.factory() as session:
        appointment = await session.get(Appointment, source_id)
        reservation = await session.scalar(
            select(AppointmentCapacityReservation).where(
                AppointmentCapacityReservation.appointment_id == source_id
            )
        )
    assert appointment is not None and appointment.concurrency_version == 1
    assert appointment.arrival_window_start_at == scheduling_api.start
    assert reservation is not None
    assert reservation.reserved_start_at == scheduling_api.start


@pytest.mark.asyncio
async def test_reschedule_rejects_invalid_lifecycle_and_requires_authorization(
    scheduling_api: SchedulingApiFixture,
) -> None:
    start = scheduling_api.start + timedelta(days=3)
    created = await _post(
        scheduling_api,
        "/api/v1/scheduling/appointments",
        _create_payload(scheduling_api, start=start),
        token=scheduling_api.token,
    )
    appointment_id = created.json()["id"]
    cancelled = await _post(
        scheduling_api,
        f"/api/v1/scheduling/appointments/{appointment_id}/cancel",
        {"expected_version": 1, "reason_code": "customer_request"},
        token=scheduling_api.token,
    )
    assert cancelled.status_code == 200
    path = f"/api/v1/scheduling/appointments/{appointment_id}/reschedule"
    replacement = start + timedelta(days=1)
    payload = {
        "expected_version": 2,
        "arrival_window_start_at": replacement.isoformat(),
        "arrival_window_end_at": (replacement + timedelta(hours=1)).isoformat(),
        "expected_duration_minutes": 60,
        "capacity_units": "1.00",
        "reason_code": "weather",
    }
    invalid_lifecycle = await _post(
        scheduling_api, path, payload, token=scheduling_api.token
    )
    unauthenticated = await _post(scheduling_api, path, payload, token=None)
    denied = await _post(
        scheduling_api, path, payload, token=scheduling_api.denied_token
    )
    unsupported_reason = await _post(
        scheduling_api,
        path,
        {**payload, "reason_code": "free_text_reason"},
        token=scheduling_api.token,
    )
    assert invalid_lifecycle.status_code == 409
    assert unauthenticated.status_code == 401
    assert denied.status_code == 403
    assert unsupported_reason.status_code == 422


@pytest.mark.asyncio
async def test_second_creation_event_failure_rolls_back_complete_request(
    scheduling_api: SchedulingApiFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_stage = BusinessEventService.stage

    def fail_compatibility_event(
        session: AsyncSession, event_data: BusinessEventCreate
    ) -> BusinessEvent:
        event = original_stage(session, event_data)
        if event_data.event_type is EventType.APPOINTMENT_BOOKED:
            raise RuntimeError("controlled compatibility event failure")
        return event

    monkeypatch.setattr(BusinessEventService, "stage", fail_compatibility_event)
    response = await _post(
        scheduling_api,
        "/api/v1/scheduling/appointments",
        _create_payload(scheduling_api),
        token=scheduling_api.token,
        raise_app_exceptions=False,
    )
    assert response.status_code == 500
    async with scheduling_api.factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Appointment)
                .where(Appointment.company_id == scheduling_api.company_id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AppointmentCapacityReservation)
                .where(
                    AppointmentCapacityReservation.company_id
                    == scheduling_api.company_id
                )
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(BusinessEvent)
                .where(BusinessEvent.company_id == scheduling_api.company_id)
            )
            == 0
        )
    monkeypatch.setattr(BusinessEventService, "stage", original_stage)
    retry = await _post(
        scheduling_api,
        "/api/v1/scheduling/appointments",
        _create_payload(scheduling_api),
        token=scheduling_api.token,
    )
    assert retry.status_code == 201
    assert retry.json()["appointment_number"] == "APT-000001"
