from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from app.core.config import settings
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.employees.models import Employee
from app.platform.permissions.models import MembershipRole, Role
from app.platform.users.models import User
from app.workforce.functional_access import FunctionalAccessService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def functional_access_database():
    engine = create_async_engine(settings.database_url)
    connection = await engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(connection, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with factory() as session, session.begin():
        company = Company(
            name="Functional Access",
            code=f"FA{uuid4().hex[:8].upper()}",
            status="active",
            timezone="America/New_York",
        )
        actor = User(
            normalized_email=f"owner-{uuid4().hex}@example.test",
            first_name="Owner",
            last_name="Test",
            display_name="Owner Test",
            status="active",
        )
        employee_user = User(
            normalized_email=f"employee-{uuid4().hex}@example.test",
            first_name="Field",
            last_name="Helper",
            display_name="Field Helper",
            status="active",
        )
        session.add_all([company, actor, employee_user])
        await session.flush()
        branch = Branch(
            company_id=company.id,
            name="MAIN",
            code=f"MAIN{uuid4().hex[:5].upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        membership = Membership(
            user_id=employee_user.id,
            company_id=company.id,
            status="active",
            has_all_branch_access=False,
            created_at=now,
            updated_at=now,
        )
        session.add_all([branch, membership])
        await session.flush()
        membership.default_branch_id = branch.id
        employee = Employee(
            company_id=company.id,
            membership_id=membership.id,
            home_branch_id=branch.id,
            employee_number=f"EMP-{uuid4().hex[:6]}",
            first_name="Field",
            last_name="Helper",
            display_name="Field Helper",
            employee_type="employee",
            status="active",
            hire_date=now.date(),
        )
        roles = [
            Role(
                company_id=company.id,
                code=code,
                name=code,
                status="active",
                is_system=True,
            )
            for code in ("TECHNICIAN", "CSR")
        ]
        session.add_all([employee, *roles])
        await session.flush()
    context = SimpleNamespace(
        company=SimpleNamespace(id=company.id),
        user=SimpleNamespace(id=actor.id),
        can_access_branch=lambda value: value == branch.id,
    )
    try:
        yield factory, context, employee, employee_user
    finally:
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_overlapping_temporary_access_preserves_other_function_and_expires(
    functional_access_database,
) -> None:
    factory, context, employee, employee_user = functional_access_database
    service = FunctionalAccessService()
    now = datetime.now(timezone.utc)
    async with factory() as session:
        technician = await service.grant(
            session,
            context=context,
            employee_id=employee.id,
            functional_area="FIELD_OPERATIONS",
            access_level="TECHNICIAN",
            effective_at=now - timedelta(minutes=1),
            expires_at=None,
            reason="Normal field access",
        )
        csr = await service.grant(
            session,
            context=context,
            employee_id=employee.id,
            functional_area="CUSTOMER_SERVICE",
            access_level="CSR",
            effective_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(days=7),
            reason="Temporary office coverage",
        )
        items = await service.list(session, context=context, employee_id=employee.id)
        assert {item.functional_area for item in items if item.effective} == {
            "FIELD_OPERATIONS",
            "CUSTOMER_SERVICE",
        }
        assert technician.expires_at is None and csr.expires_at is not None
        persisted = await session.scalar(
            select(Employee).where(Employee.id == employee.id)
        )
        assert persisted.job_title == employee.job_title
        refreshed_user = await session.get(User, employee_user.id)
        assert refreshed_user is not None
        assert refreshed_user.authorization_version == 3


@pytest.mark.asyncio
async def test_functional_access_replacement_and_revocation_preserve_history(
    functional_access_database,
) -> None:
    factory, context, employee, _ = functional_access_database
    service = FunctionalAccessService()
    now = datetime.now(timezone.utc)
    async with factory() as session:
        first = await service.grant(
            session,
            context=context,
            employee_id=employee.id,
            functional_area="CUSTOMER_SERVICE",
            access_level="CSR",
            effective_at=now,
            expires_at=now + timedelta(days=1),
            reason="First coverage",
        )
        second = await service.grant(
            session,
            context=context,
            employee_id=employee.id,
            functional_area="CUSTOMER_SERVICE",
            access_level="CSR",
            effective_at=now,
            expires_at=now + timedelta(days=7),
            reason="Extended coverage",
        )
        await service.revoke(
            session,
            context=context,
            employee_id=employee.id,
            assignment_id=second.assignment_id,
            reason="Coverage complete",
        )
        rows = tuple(
            (
                await session.scalars(
                    select(MembershipRole)
                    .where(MembershipRole.membership_id == employee.membership_id)
                    .order_by(MembershipRole.assigned_at, MembershipRole.id)
                )
            ).all()
        )
        assert len(rows) == 2
        assert rows[0].id == first.assignment_id and rows[0].revoked_at is not None
        assert rows[1].id == second.assignment_id and rows[1].revoked_at is not None
