from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.platform.branch.models import Branch
from app.platform.company.models import Company
from app.platform.employees.models import Employee
from app.workforce.administration_commands import WorkforceAdministrationService
from app.workforce.models import (
    Capability,
    CapabilityCategory,
    WorkforceCapability,
    WorkforceCapabilityProfile,
    WorkforceWorkingAvailability,
)
from app.workforce.router import prepare_field_readiness
from app.workforce.schemas import FieldReadinessRequest


@pytest_asyncio.fixture
async def field_readiness_database():
    engine = create_async_engine(settings.database_url)
    connection = await engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(connection, expire_on_commit=False)
    company_id, branch_id, employee_id, user_id = uuid4(), uuid4(), uuid4(), uuid4()
    async with factory() as session, session.begin():
        session.add(
            Company(
                id=company_id, name="Field Readiness Test", code=f"FR{uuid4().hex[:8].upper()}",
                status="active", timezone="America/New_York",
            )
        )
        await session.flush()
        session.add_all(
            [
                Branch(
                    id=branch_id, company_id=company_id, name="Test Branch",
                    code=f"B{uuid4().hex[:8].upper()}", status="active",
                    timezone="America/New_York", is_primary=True,
                ),
                Employee(
                    id=employee_id, company_id=company_id, home_branch_id=branch_id,
                    employee_number=f"E{uuid4().hex[:8].upper()}", first_name="Field",
                    last_name="Employee", display_name="Field Employee",
                    employee_type="employee", status="active",
                ),
            ]
        )
    context = SimpleNamespace(
        company=SimpleNamespace(id=company_id), user=SimpleNamespace(id=user_id),
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
            session, context=context, employee_id=employee_id, branch_id=branch_id,
            start_at=start, end_at=start + timedelta(hours=2),
        )
        second = await service.prepare_field_readiness(
            session, context=context, employee_id=employee_id, branch_id=branch_id,
            start_at=start, end_at=start + timedelta(hours=2),
        )
        assert first == second
        profile = await session.scalar(
            select(WorkforceCapabilityProfile).where(
                WorkforceCapabilityProfile.employee_id == employee_id
            )
        )
        capability = await session.scalar(
            select(Capability).where(Capability.code == "technician")
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
        assert evidence.proficiency == "qualified"
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
                company_id=context.company.id, code="field_service",
                display_name="Retired Field Service", status="inactive",
            )
        )
    start = datetime.now(timezone.utc)
    async with factory() as session:
        with pytest.raises(ValueError, match="category conflicts"):
            await service.prepare_field_readiness(
                session, context=context, employee_id=employee_id, branch_id=branch_id,
                start_at=start, end_at=start + timedelta(hours=1),
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
    )
    with pytest.raises(HTTPException) as captured:
        await prepare_field_readiness(uuid4(), request, context, object())
    assert captured.value.status_code == 403
