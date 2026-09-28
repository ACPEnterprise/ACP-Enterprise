from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.platform.branch.models import Branch
from app.platform.company.models import Company
from app.platform.employees.models import Employee
from app.platform.users.models import User
from app.workforce.real_roster import REAL_ALL_COUNTY_ROSTER, RealRosterRole
from app.workforce.real_roster_service import RealRosterConflict, RealRosterService


@pytest_asyncio.fixture
async def real_roster_database():
    engine = create_async_engine(settings.database_url)
    connection = await engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(
        connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    company_id, branch_id, employee_id, synthetic_id, actor_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    async with factory() as session, session.begin():
        session.add(
            Company(
                id=company_id,
                name="Roster Contract Test",
                code=f"RR{uuid4().hex[:8].upper()}",
                status="active",
                timezone="America/New_York",
            )
        )
        await session.flush()
        session.add_all(
            [
                Branch(
                    id=branch_id,
                    company_id=company_id,
                    name="Main Branch",
                    code="MAIN",
                    status="active",
                    timezone="America/New_York",
                    is_primary=True,
                ),
                User(
                    id=actor_id,
                    normalized_email=f"owner-{uuid4().hex}@example.test",
                    first_name="Owner",
                    last_name="Test",
                    display_name="Owner Test",
                    status="active",
                    authorization_version=1,
                ),
                Employee(
                    id=employee_id,
                    company_id=company_id,
                    home_branch_id=branch_id,
                    employee_number=f"E{uuid4().hex[:8].upper()}",
                    first_name="Exact",
                    last_name="Employee",
                    display_name="Exact Employee",
                    employee_type="employee",
                    status="active",
                ),
                Employee(
                    id=synthetic_id,
                    company_id=company_id,
                    home_branch_id=branch_id,
                    employee_number="SYN-BETA-0001",
                    first_name="Synthetic",
                    last_name="Beta Employee",
                    display_name="Synthetic Beta Employee",
                    employee_type="employee",
                    status="active",
                ),
            ]
        )
    context = SimpleNamespace(
        company=SimpleNamespace(id=company_id),
        user=SimpleNamespace(id=actor_id),
    )
    try:
        yield factory, context, employee_id, synthetic_id
    finally:
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


def test_owner_confirmed_roster_is_exact_and_excludes_marketing_account() -> None:
    assert len(REAL_ALL_COUNTY_ROSTER) == 8
    assert [item.display_name for item in REAL_ALL_COUNTY_ROSTER] == [
        "Michael Fouse",
        "Lianne Hernandez",
        "Alex Donahue",
        "Melvin Santiago",
        "Adam Mari",
        "Dareis Montgomery",
        "Dakota Wilcox",
        "Jason Calci",
    ]
    assert sum(item.field_tech for item in REAL_ALL_COUNTY_ROSTER) == 5
    assert all("marketing" not in item.key for item in REAL_ALL_COUNTY_ROSTER)


def test_roster_role_contracts_compose_existing_canonical_roles() -> None:
    roles = {item.role: item.required_role_codes for item in REAL_ALL_COUNTY_ROSTER}
    assert roles[RealRosterRole.ADMIN] == {"COMPANY_ADMINISTRATOR"}
    assert roles[RealRosterRole.OFFICE_MANAGER] == {"OFFICE_MANAGER"}
    assert roles[RealRosterRole.OFFICE_STAFF] == {"SERVICE_CSR"}
    assert roles[RealRosterRole.FIELD_TECH] == {
        "TECHNICIAN",
        "ACP_EMPLOYEE_MOBILE",
    }


def test_unbound_roster_identity_remains_unknown_not_missing() -> None:
    item = RealRosterService._unbound(REAL_ALL_COUNTY_ROSTER[3])
    assert item.employee_id is None
    assert item.employment_status is None
    assert item.user_state == "AUTHENTICATED_VERIFICATION_REQUIRED"
    assert item.employee_state == "AUTHENTICATED_VERIFICATION_REQUIRED"
    assert item.dispatch_state == "AUTHENTICATED_VERIFICATION_REQUIRED"
    assert item.blockers == ("OWNER_EMPLOYEE_BINDING_REQUIRED",)


def test_source_certification_requires_exact_persisted_target_binding() -> None:
    employee_id = uuid4()
    assert (
        RealRosterService._source_certification_state(
            disposition="CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE",
            employee_id=employee_id,
            roster_by_employee={employee_id: "melvin-santiago"},
        )
        == "ACP_EMPLOYEE_BOUND"
    )
    assert (
        RealRosterService._source_certification_state(
            disposition="CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE",
            employee_id=employee_id,
            roster_by_employee={},
        )
        == "OWNER_CERTIFICATION_REQUIRED"
    )
    assert (
        RealRosterService._source_certification_state(
            disposition="CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE",
            employee_id=None,
            roster_by_employee={},
        )
        == "SOURCE_ONLY"
    )


def test_excluded_source_identity_is_not_reported_as_employee() -> None:
    assert (
        RealRosterService._source_certification_state(
            disposition="EXCLUDE_EMPLOYEE_HOLD_ASSIGNMENTS",
            employee_id=None,
            roster_by_employee={},
        )
        == "NOT_EMPLOYEE"
    )


@pytest.mark.asyncio
async def test_exact_employee_binding_is_durable_and_does_not_name_match(
    real_roster_database,
) -> None:
    factory, context, employee_id, _ = real_roster_database
    async with factory() as session:
        result = await RealRosterService().bind(
            session,
            context=context,
            roster_key="melvin-santiago",
            employee_id=employee_id,
        )
        melvin = next(
            item for item in result.items if item.roster_key == "melvin-santiago"
        )
        assert melvin.employee_id == employee_id
        assert melvin.employee_display_name == "Exact Employee"
        assert melvin.employment_status == "active"
        assert melvin.user_state == "USER_MISSING_OR_INACTIVE"
        assert "USER_NOT_READY" in melvin.blockers
        assert result.login_ready_total == 0
        assert result.membership_ready_total == 0
        assert result.branch_ready_total == 0
        assert result.mobile_ready_total == 0
        assert result.dispatch_ready_total == 0
        assert result.timekeeping_ready_total == 0
        assert result.payroll_identity_ready_total == 1
        assert result.binding_candidates == ()
        assert result.binding_candidate_count == 0


@pytest.mark.asyncio
async def test_real_binding_candidates_exclude_synthetic_acceptance_employee(
    real_roster_database,
) -> None:
    factory, context, employee_id, synthetic_id = real_roster_database
    async with factory() as session:
        result = await RealRosterService().readiness(session, context=context)
        assert [candidate.employee_id for candidate in result.binding_candidates] == [
            employee_id
        ]
        assert result.binding_candidate_count == 1
        assert synthetic_id not in {
            candidate.employee_id for candidate in result.binding_candidates
        }


@pytest.mark.asyncio
async def test_synthetic_employee_binding_fails_closed_at_mutation_boundary(
    real_roster_database,
) -> None:
    factory, context, _, synthetic_id = real_roster_database
    async with factory() as session:
        with pytest.raises(
            RealRosterConflict,
            match="Synthetic acceptance Employees cannot represent real roster identities",
        ):
            await RealRosterService().bind(
                session,
                context=context,
                roster_key="alex-donahue",
                employee_id=synthetic_id,
            )
