from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest
from app.core.config import settings
from app.customers.router import router as customers_router
from app.database.session import get_database_session, get_security_database_session
from app.dispatch.router import router as dispatch_router
from app.employee_operations.permissions import EmployeeOperationsPermission
from app.employee_operations.router import router as employee_operations_router
from app.jobs.router import router as jobs_router
from app.platform.auth.models import AuthenticationSession
from app.platform.auth.services import access_token_service, utc_now
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership, MembershipBranchAccess
from app.platform.company.models import Company
from app.platform.employees.models import Employee
from app.platform.permissions.catalog_sync import PermissionCatalogSyncService
from app.platform.permissions.codes import (
    CustomerPermission,
    DispatchPermission,
    JobPermission,
    SchedulingPermission,
)
from app.platform.permissions.models import (
    MembershipRole,
    Permission,
    Role,
    RolePermission,
)
from app.platform.users.models import User, UserCredential
from app.scheduling.models import (
    BranchSchedulingCalendar,
    BranchSchedulingWeeklyInterval,
)
from app.scheduling.router import router as scheduling_router
from app.workforce.models import (
    WorkforceBranchEligibility,
    WorkforceCapabilityProfile,
    WorkforceWorkingAvailability,
)
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


async def _actor(
    session: AsyncSession,
    *,
    company: Company,
    branch: Branch,
    permissions: tuple[Permission, ...],
    role_code: str,
    display_name: str,
    suffix: str,
    authentication_session_count: int = 1,
) -> tuple[User, Membership, tuple[AuthenticationSession, ...]]:
    now = utc_now()
    user = User(
        normalized_email=f"{role_code.lower()}-{suffix}@example.test",
        first_name=display_name.split()[0],
        last_name=display_name.split()[-1],
        display_name=display_name,
        status="active",
        authorization_version=1,
    )
    session.add(user)
    await session.flush()
    membership = Membership(
        user_id=user.id,
        company_id=company.id,
        status="active",
        has_all_branch_access=False,
        default_branch_id=branch.id,
        invited_at=now,
        accepted_at=now,
    )
    authentication_sessions = tuple(
        AuthenticationSession(
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
        for _ in range(authentication_session_count)
    )
    session.add_all(
        [
            UserCredential(
                user_id=user.id,
                password_hash="$argon2id$isolated-operational-qualification",
                password_changed_at=now,
                credential_version=1,
            ),
            membership,
            *authentication_sessions,
        ]
    )
    await session.flush()
    role = Role(
        company_id=company.id,
        code=role_code,
        name=display_name,
        status="active",
        is_system=False,
        created_by_user_id=user.id,
        updated_by_user_id=user.id,
    )
    session.add(role)
    await session.flush()
    session.add_all(
        [
            MembershipBranchAccess(
                membership_id=membership.id,
                branch_id=branch.id,
                assigned_at=now,
            ),
            MembershipRole(
                company_id=company.id,
                membership_id=membership.id,
                role_id=role.id,
                assigned_by_user_id=user.id,
            ),
            *(
                RolePermission(
                    role_id=role.id,
                    permission_id=permission.id,
                    assigned_by_user_id=user.id,
                )
                for permission in permissions
            ),
        ]
    )
    return user, membership, authentication_sessions


def _token(user: User, authentication_session: AuthenticationSession) -> str:
    token, _ = access_token_service.issue(
        user_id=user.id,
        session_id=authentication_session.id,
        credential_version=1,
        authorization_version=1,
        now=utc_now(),
    )
    return token


def _headers(*, company_id: UUID, branch_id: UUID, token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Company-ID": str(company_id),
        "X-Branch-ID": str(branch_id),
    }


@pytest.mark.asyncio
async def test_authenticated_csr_dispatch_flow_persists_across_sessions() -> None:
    """Qualify the current-date CSR-to-technician path with isolated test data."""
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex[:10]
    now = utc_now()
    business_zone = ZoneInfo("America/New_York")
    local_now = now.astimezone(business_zone)
    window_start_local = (local_now + timedelta(minutes=45)).replace(
        second=0, microsecond=0
    )
    window_start_local += timedelta(minutes=(-window_start_local.minute) % 15)
    override_reason_code = None
    if window_start_local.date() != local_now.date():
        window_start_local = local_now.replace(
            hour=22, minute=0, second=0, microsecond=0
        )
        override_reason_code = "after_hours_call"
    window_end_local = window_start_local + timedelta(minutes=60)
    window_start = window_start_local.astimezone(timezone.utc)
    window_end = window_end_local.astimezone(timezone.utc)

    async with factory() as session:
        await PermissionCatalogSyncService().synchronize(session)
    async with factory() as session, session.begin():
        company = Company(
            name=f"OM1-B CSR Dispatch Qualification {suffix}",
            code=f"O1B{suffix.upper()}",
            status="active",
            timezone="America/New_York",
        )
        branch = Branch(
            company=company,
            name="Isolated Qualification Branch",
            code=f"QB{suffix.upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        session.add_all([company, branch])
        await session.flush()
        requested_codes = frozenset(
            {
                *CustomerPermission.ALL,
                *JobPermission.ALL,
                *SchedulingPermission.ALL,
                *DispatchPermission.ALL,
                EmployeeOperationsPermission.OWN_DAY_READ,
            }
        )
        permissions = tuple(
            (
                await session.scalars(
                    select(Permission).where(Permission.code.in_(requested_codes))
                )
            ).all()
        )
        assert {permission.code for permission in permissions} == requested_codes
        csr_permissions = tuple(
            permission
            for permission in permissions
            if permission.code != EmployeeOperationsPermission.OWN_DAY_READ
        )
        technician_permissions = tuple(
            permission
            for permission in permissions
            if permission.code == EmployeeOperationsPermission.OWN_DAY_READ
        )
        csr_user, _, csr_sessions = await _actor(
            session,
            company=company,
            branch=branch,
            permissions=csr_permissions,
            role_code=f"CSR_DISPATCH_{suffix.upper()}",
            display_name="CSR Dispatcher",
            suffix=suffix,
            authentication_session_count=2,
        )
        technician_user, technician_membership, technician_sessions = await _actor(
            session,
            company=company,
            branch=branch,
            permissions=technician_permissions,
            role_code="TECHNICIAN",
            display_name="Qualification Technician",
            suffix=suffix,
        )
        technician = Employee(
            company_id=company.id,
            home_branch_id=branch.id,
            membership_id=technician_membership.id,
            employee_number=f"QT-{suffix.upper()}",
            first_name="Qualification",
            last_name="Technician",
            display_name="Qualification Technician",
            job_title="Service Technician",
            employee_type="employee",
            status="active",
        )
        session.add(technician)
        await session.flush()
        profile = WorkforceCapabilityProfile(
            company_id=company.id,
            employee_id=technician.id,
            status="active",
        )
        session.add(profile)
        await session.flush()
        calendar = BranchSchedulingCalendar(
            company_id=company.id,
            branch_id=branch.id,
            booking_horizon_days=180,
            minimum_notice_minutes=0,
            slot_interval_minutes=15,
            default_capacity_units=Decimal("2.00"),
        )
        session.add(calendar)
        await session.flush()
        session.add_all(
            [
                WorkforceBranchEligibility(
                    company_id=company.id,
                    profile_id=profile.id,
                    branch_id=branch.id,
                    status="active",
                ),
                WorkforceWorkingAvailability(
                    company_id=company.id,
                    profile_id=profile.id,
                    branch_id=branch.id,
                    start_at=window_start - timedelta(hours=1),
                    end_at=window_end + timedelta(hours=1),
                    status="available",
                    source="isolated_qualification",
                ),
                *(
                    BranchSchedulingWeeklyInterval(
                        calendar_id=calendar.id,
                        day_of_week=day,
                        start_minute=0,
                        end_minute=24 * 60,
                        capacity_units=Decimal("2.00"),
                    )
                    for day in range(7)
                ),
            ]
        )

    app = FastAPI()
    for router in (
        customers_router,
        jobs_router,
        scheduling_router,
        dispatch_router,
        employee_operations_router,
    ):
        app.include_router(router)

    async def database_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_database_session] = database_session
    app.dependency_overrides[get_security_database_session] = database_session
    csr_write_headers = _headers(
        company_id=company.id,
        branch_id=branch.id,
        token=_token(csr_user, csr_sessions[0]),
    )
    csr_read_headers = _headers(
        company_id=company.id,
        branch_id=branch.id,
        token=_token(csr_user, csr_sessions[1]),
    )
    technician_headers = _headers(
        company_id=company.id,
        branch_id=branch.id,
        token=_token(technician_user, technician_sessions[0]),
    )
    customer_name = f"P0 Rivera Residence {suffix}"

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as csr_write_session:
            customer_response = await csr_write_session.post(
                "/api/v1/customers",
                headers={
                    **csr_write_headers,
                    "Idempotency-Key": f"p0-customer-{suffix}",
                },
                json={
                    "customer_type": "residential",
                    "display_name": customer_name,
                    "preferred_contact_method": "phone",
                    "status": "active",
                },
            )
            assert customer_response.status_code == 201, customer_response.text
            customer = customer_response.json()
            location_response = await csr_write_session.post(
                f"/api/v1/customers/{customer['id']}/locations",
                headers=csr_write_headers,
                json={
                    "nickname": "Primary residence",
                    "address": "101 Qualification Lane",
                    "city": "Raleigh",
                    "state": "NC",
                    "postal_code": "27601",
                    "country": "US",
                    "is_primary": True,
                },
            )
            assert location_response.status_code == 201, location_response.text
            location = location_response.json()
            appointment_response = await csr_write_session.post(
                "/api/v1/scheduling/appointments",
                headers=csr_write_headers,
                json={
                    "idempotency_key": str(uuid4()),
                    "branch_id": str(branch.id),
                    "customer_id": customer["id"],
                    "service_location_id": location["id"],
                    "arrival_window_start_at": window_start.isoformat(),
                    "arrival_window_end_at": window_end.isoformat(),
                    "expected_duration_minutes": 60,
                    "capacity_units": "1.00",
                    "override_reason_code": override_reason_code,
                },
            )
            assert appointment_response.status_code == 201, appointment_response.text
            appointment = appointment_response.json()
            assert (
                datetime.fromisoformat(appointment["arrival_window_start_at"])
                .astimezone(business_zone)
                .date()
                == local_now.date()
            )
            job_response = await csr_write_session.post(
                "/api/v1/jobs/from-appointment",
                headers=csr_write_headers,
                json={
                    "appointment_id": appointment["id"],
                    "job_type_code": "repair",
                    "priority": "normal",
                    "customer_reported_problem": "Isolated P0 dispatch qualification",
                },
            )
            assert job_response.status_code == 201, job_response.text
            job = job_response.json()
            activated_response = await csr_write_session.post(
                f"/api/v1/jobs/{job['id']}/activate",
                headers=csr_write_headers,
                json={"expected_version": job["concurrency_version"]},
            )
            assert activated_response.status_code == 200, activated_response.text
            assignment_response = await csr_write_session.post(
                f"/api/v1/dispatch/appointments/{appointment['id']}/assignment",
                headers=csr_write_headers,
                json={
                    "employee_id": str(technician.id),
                    "reason": "Current-date operational qualification",
                    "idempotency_key": f"p0-dispatch-{suffix}",
                },
            )
            assert assignment_response.status_code == 200, assignment_response.text
            assignment = assignment_response.json()
            assert assignment["primary_employee_id"] == str(technician.id)

        day_start = datetime.combine(
            local_now.date(), datetime.min.time(), business_zone
        ).astimezone(timezone.utc)
        day_end = day_start + timedelta(days=1)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as independent_csr_session:
            search_response = await independent_csr_session.get(
                "/api/v1/customers/search",
                headers=csr_read_headers,
                params={"query": customer_name},
            )
            assert search_response.status_code == 200, search_response.text
            search_items = search_response.json()["items"]
            assert [item["display_name"] for item in search_items] == [customer_name]
            assert search_items[0]["primary_location"]["address_line_1"] == (
                "101 Qualification Lane"
            )

            jobs_response = await independent_csr_session.get(
                "/api/v1/jobs",
                headers=csr_read_headers,
                params={"customer_id": customer["id"]},
            )
            assert jobs_response.status_code == 200, jobs_response.text
            jobs = jobs_response.json()["items"]
            assert len(jobs) == 1
            assert jobs[0]["customer_display_name"] == customer_name
            assert jobs[0]["appointment_count"] == 1

            board_response = await independent_csr_session.get(
                "/api/v1/dispatch/board",
                headers=csr_read_headers,
                params={
                    "start_at": day_start.isoformat(),
                    "end_at": day_end.isoformat(),
                    "branch_id": str(branch.id),
                },
            )
            assert board_response.status_code == 200, board_response.text
            board_items = board_response.json()["items"]
            board_item = next(
                item
                for item in board_items
                if item["appointment_id"] == appointment["id"]
            )
            assert board_item["customer_display_name"] == customer_name
            assert board_item["job_id"] == job["id"]
            assert board_item["assignment"]["primary_employee_id"] == str(technician.id)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as technician_session:
            my_day_response = await technician_session.get(
                "/api/v1/employee-operations/me/day",
                headers=technician_headers,
                params={"business_date": local_now.date().isoformat()},
            )
            assert my_day_response.status_code == 200, my_day_response.text
            my_day_items = my_day_response.json()["assignments"]
            my_day_item = next(
                item
                for item in my_day_items
                if item["appointment_id"] == appointment["id"]
            )
            assert my_day_item["job_id"] == job["id"]
            assert my_day_item["customer_display_name"] == customer_name
            assert my_day_item["service_location"]["address_line_1"] == (
                "101 Qualification Lane"
            )

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as persistence_readback_session:
            detail_response = await persistence_readback_session.get(
                f"/api/v1/customers/{customer['id']}", headers=csr_read_headers
            )
            job_detail_response = await persistence_readback_session.get(
                f"/api/v1/jobs/{job['id']}", headers=csr_read_headers
            )
            assignment_detail_response = await persistence_readback_session.get(
                f"/api/v1/dispatch/appointments/{appointment['id']}/assignment",
                headers=csr_read_headers,
            )
            assert detail_response.status_code == 200, detail_response.text
            assert job_detail_response.status_code == 200, job_detail_response.text
            assert assignment_detail_response.status_code == 200
            assert detail_response.json()["display_name"] == customer_name
            assert job_detail_response.json()["customer"]["display_name"] == (
                customer_name
            )
            assert (
                job_detail_response.json()["appointments"][0]["appointment_id"]
                == (appointment["id"])
            )
            assert assignment_detail_response.json()["primary_employee_id"] == str(
                technician.id
            )
    finally:
        await engine.dispose()
