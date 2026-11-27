from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from app.core.config import settings
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership, MembershipBranchAccess
from app.platform.company.models import Company
from app.platform.employees.models import Employee
from app.platform.permissions.models import MembershipRole, Role
from app.platform.users.models import User
from app.workforce.administration_commands import WorkforceAdministrationService
from app.workforce.models import (
    Capability,
    CapabilityCategory,
    WorkforceBranchEligibility,
    WorkforceCapability,
    WorkforceCapabilityProfile,
    WorkforceWorkingAvailability,
)
from app.workforce.router import prepare_field_readiness
from app.workforce.schemas import FieldReadinessRequest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def field_readiness_database():
    engine = create_async_engine(settings.database_url)
    connection = await engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(connection, expire_on_commit=False)
    company_id, branch_id, employee_id, user_id = uuid4(), uuid4(), uuid4(), uuid4()
    async with factory() as session, session.begin():
        company = Company(
            id=company_id,
            name="Field Readiness Test",
            code=f"FR{uuid4().hex[:8].upper()}",
            status="active",
            timezone="America/New_York",
        )
        branch = Branch(
            id=branch_id,
            company_id=company_id,
            name="Test Branch",
            code=f"B{uuid4().hex[:8].upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        actor = User(
            id=user_id,
            normalized_email=f"readiness-admin-{uuid4()}@example.test",
            first_name="Readiness",
            last_name="Admin",
            display_name="Readiness Admin",
            status="active",
        )
        technician_user = User(
            normalized_email=f"readiness-tech-{uuid4()}@example.test",
            first_name="Field",
            last_name="Employee",
            display_name="Field Employee",
            status="active",
        )
        session.add_all([company, branch, actor, technician_user])
        await session.flush()
        membership = Membership(
            user_id=technician_user.id,
            company_id=company_id,
            status="active",
            default_branch_id=branch_id,
            has_all_branch_access=False,
        )
        technician_role = Role(
            company_id=company_id,
            code="TECHNICIAN",
            name="Technician",
            status="active",
            is_system=True,
        )
        session.add_all([membership, technician_role])
        await session.flush()
        session.add_all(
            [
                MembershipBranchAccess(
                    membership_id=membership.id,
                    branch_id=branch_id,
                    assigned_by_user_id=user_id,
                ),
                MembershipRole(
                    company_id=company_id,
                    membership_id=membership.id,
                    role_id=technician_role.id,
                    assigned_by_user_id=user_id,
                ),
                Employee(
                    id=employee_id,
                    company_id=company_id,
                    home_branch_id=branch_id,
                    membership_id=membership.id,
                    employee_number=f"E{uuid4().hex[:8].upper()}",
                    first_name="Field",
                    last_name="Employee",
                    display_name="Field Employee",
                    employee_type="employee",
                    status="active",
                ),
            ]
        )
    context = SimpleNamespace(
        company=SimpleNamespace(id=company_id),
        user=SimpleNamespace(id=user_id),
        active_branch=SimpleNamespace(id=branch_id),
        can_access_branch=lambda value: value == branch_id,
    )
    try:
        yield factory, context, employee_id, branch_id
    finally:
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_field_readiness_atomically_creates_canonical_evidence(
    field_readiness_database,
) -> None:
    service = WorkforceAdministrationService()
    factory, context, employee_id, branch_id = field_readiness_database
    start = datetime.now(timezone.utc)
    async with factory() as session:
        first = await service.prepare_field_readiness(
            session,
            context=context,
            employee_id=employee_id,
            branch_id=branch_id,
            start_at=start,
            end_at=start + timedelta(hours=2),
            reason="Owner confirmed shift",
        )
        second = await service.prepare_field_readiness(
            session,
            context=context,
            employee_id=employee_id,
            branch_id=branch_id,
            start_at=start,
            end_at=start + timedelta(hours=2),
            reason="Owner confirmed shift",
        )
        assert first == second
        profile = await session.scalar(
            select(WorkforceCapabilityProfile).where(
                WorkforceCapabilityProfile.employee_id == employee_id
            )
        )
        capability = await session.scalar(
            select(Capability).where(
                Capability.company_id == context.company.id,
                Capability.code == "technician",
            )
        )
        evidence = await session.scalar(
            select(WorkforceCapability).where(
                WorkforceCapability.profile_id == profile.id,
                WorkforceCapability.capability_id == capability.id,
            )
        )
        availability = await session.scalar(
            select(WorkforceWorkingAvailability).where(
                WorkforceWorkingAvailability.profile_id == profile.id
            )
        )
        branch_eligibility = await session.scalar(
            select(WorkforceBranchEligibility).where(
                WorkforceBranchEligibility.profile_id == profile.id,
                WorkforceBranchEligibility.branch_id == branch_id,
            )
        )
        assert evidence.proficiency == "qualified"
        assert branch_eligibility.status == "active"
        assert availability.source == "operator_confirmed_dispatch_window"


@pytest.mark.asyncio
async def test_field_readiness_rolls_back_profile_when_catalog_conflicts(
    field_readiness_database,
) -> None:
    service = WorkforceAdministrationService()
    factory, context, employee_id, branch_id = field_readiness_database
    async with factory() as session, session.begin():
        session.add(
            CapabilityCategory(
                company_id=context.company.id,
                code="field_service",
                display_name="Retired Field Service",
                status="inactive",
            )
        )
    start = datetime.now(timezone.utc)
    async with factory() as session:
        with pytest.raises(ValueError, match="category conflicts"):
            await service.prepare_field_readiness(
                session,
                context=context,
                employee_id=employee_id,
                branch_id=branch_id,
                start_at=start,
                end_at=start + timedelta(hours=1),
                reason="Owner confirmed shift",
            )
        assert (
            await session.scalar(
                select(WorkforceCapabilityProfile).where(
                    WorkforceCapabilityProfile.employee_id == employee_id
                )
            )
            is None
        )


@pytest.mark.asyncio
async def test_field_readiness_fails_closed_without_technician_role(
    field_readiness_database,
) -> None:
    service = WorkforceAdministrationService()
    factory, context, employee_id, branch_id = field_readiness_database
    async with factory() as session, session.begin():
        employee = await session.get(Employee, employee_id)
        role_assignment = await session.scalar(
            select(MembershipRole).where(
                MembershipRole.membership_id == employee.membership_id
            )
        )
        await session.delete(role_assignment)
    start = datetime.now(timezone.utc)
    async with factory() as session:
        with pytest.raises(ValueError, match="Technician role"):
            await service.prepare_field_readiness(
                session,
                context=context,
                employee_id=employee_id,
                branch_id=branch_id,
                start_at=start,
                end_at=start + timedelta(hours=1),
                reason="Owner confirmed shift",
            )
        assert await session.scalar(
            select(WorkforceCapabilityProfile).where(
                WorkforceCapabilityProfile.employee_id == employee_id
            )
        ) is None


@pytest.mark.asyncio
async def test_field_readiness_fails_closed_without_membership_branch_grant(
    field_readiness_database,
) -> None:
    service = WorkforceAdministrationService()
    factory, context, employee_id, branch_id = field_readiness_database
    async with factory() as session, session.begin():
        employee = await session.get(Employee, employee_id)
        membership = await session.get(Membership, employee.membership_id)
        membership.default_branch_id = None
        branch_grant = await session.scalar(
            select(MembershipBranchAccess).where(
                MembershipBranchAccess.membership_id == membership.id,
                MembershipBranchAccess.branch_id == branch_id,
            )
        )
        await session.delete(branch_grant)
    start = datetime.now(timezone.utc)
    async with factory() as session:
        with pytest.raises(ValueError, match="not granted"):
            await service.prepare_field_readiness(
                session,
                context=context,
                employee_id=employee_id,
                branch_id=branch_id,
                start_at=start,
                end_at=start + timedelta(hours=1),
                reason="Owner confirmed shift",
            )
        assert await session.scalar(
            select(WorkforceCapabilityProfile).where(
                WorkforceCapabilityProfile.employee_id == employee_id
            )
        ) is None


@pytest.mark.asyncio
async def test_field_readiness_requires_both_workforce_permissions() -> None:
    context = SimpleNamespace(has_permission=lambda _permission: False)
    request = FieldReadinessRequest(
        branch_id=uuid4(),
        window_start_at=datetime.now(timezone.utc),
        window_end_at=datetime.now(timezone.utc) + timedelta(hours=1),
        reason="Owner confirmed shift",
    )
    with pytest.raises(HTTPException) as captured:
        await prepare_field_readiness(uuid4(), request, context, object())
    assert captured.value.status_code == 403
