from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import settings
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership, MembershipBranchAccess
from app.platform.company.models import Company
from app.platform.employees.models import Employee
from app.platform.users.models import User, UserCredential


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def identity_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(settings.database_url)
    try:
        yield engine
    finally:
        await engine.dispose()


async def create_company_branch(
    engine: AsyncEngine,
    *,
    company_code: str,
    branch_code: str,
) -> tuple[UUID, UUID]:
    company_id = uuid4()
    branch_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(Company).values(
                id=company_id,
                name=f"{company_code} Company",
                code=company_code,
                status="active",
                timezone="America/New_York",
            )
        )
        await connection.execute(
            insert(Branch).values(
                id=branch_id,
                company_id=company_id,
                name=f"{branch_code} Branch",
                code=branch_code,
                status="active",
                timezone="America/New_York",
                is_primary=True,
            )
        )
    return company_id, branch_id


async def create_user(engine: AsyncEngine, email: str) -> UUID:
    user_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(User).values(
                id=user_id,
                normalized_email=email,
                first_name="Jordan",
                last_name="Rivera",
                display_name="Jordan Rivera",
                status="active",
            )
        )
    return user_id


@pytest.mark.asyncio
async def test_unique_user_email_and_one_credential_per_user(
    identity_engine: AsyncEngine,
) -> None:
    user_id = await create_user(identity_engine, "jordan@example.com")

    with pytest.raises(IntegrityError):
        async with identity_engine.begin() as connection:
            await connection.execute(
                insert(User).values(
                    normalized_email="jordan@example.com",
                    first_name="Other",
                    last_name="Person",
                    display_name="Other Person",
                    status="invited",
                )
            )

    async with identity_engine.begin() as connection:
        await connection.execute(
            insert(UserCredential).values(
                user_id=user_id,
                password_hash="$argon2id$test-hash-not-a-password",
            )
        )

    with pytest.raises(IntegrityError):
        async with identity_engine.begin() as connection:
            await connection.execute(
                insert(UserCredential).values(
                    user_id=user_id,
                    password_hash="$argon2id$second-test-hash",
                )
            )


@pytest.mark.asyncio
async def test_membership_uniqueness_status_and_default_branch_ownership(
    identity_engine: AsyncEngine,
) -> None:
    company_id, branch_id = await create_company_branch(
        identity_engine, company_code="MEMBERA", branch_code="MAIN"
    )
    other_company_id, other_branch_id = await create_company_branch(
        identity_engine, company_code="MEMBERB", branch_code="OTHER"
    )
    user_id = await create_user(identity_engine, "membership@example.com")

    with pytest.raises(IntegrityError):
        async with identity_engine.begin() as connection:
            await connection.execute(
                insert(Membership).values(
                    user_id=user_id,
                    company_id=company_id,
                    status="invalid",
                    has_all_branch_access=False,
                )
            )

    with pytest.raises(IntegrityError):
        async with identity_engine.begin() as connection:
            await connection.execute(
                insert(Membership).values(
                    user_id=user_id,
                    company_id=company_id,
                    default_branch_id=other_branch_id,
                    status="active",
                    has_all_branch_access=False,
                )
            )

    membership_id = uuid4()
    async with identity_engine.begin() as connection:
        await connection.execute(
            insert(Membership).values(
                id=membership_id,
                user_id=user_id,
                company_id=company_id,
                default_branch_id=branch_id,
                status="active",
                has_all_branch_access=False,
                accepted_at=utc_now(),
            )
        )

    with pytest.raises(IntegrityError):
        async with identity_engine.begin() as connection:
            await connection.execute(
                insert(Membership).values(
                    user_id=user_id,
                    company_id=company_id,
                    status="suspended",
                    has_all_branch_access=False,
                )
            )

    async with identity_engine.connect() as connection:
        branch_grant_count = await connection.scalar(
            select(func.count())
            .select_from(MembershipBranchAccess)
            .where(MembershipBranchAccess.membership_id == membership_id)
        )
        has_all_access = await connection.scalar(
            select(Membership.has_all_branch_access).where(
                Membership.id == membership_id
            )
        )
    assert branch_grant_count == 0
    assert has_all_access is False
    assert other_company_id != company_id


@pytest.mark.asyncio
async def test_unique_membership_branch_access_and_restrictive_deletion(
    identity_engine: AsyncEngine,
) -> None:
    company_id, branch_id = await create_company_branch(
        identity_engine, company_code="ACCESS", branch_code="FIELD"
    )
    user_id = await create_user(identity_engine, "access@example.com")
    membership_id = uuid4()
    async with identity_engine.begin() as connection:
        await connection.execute(
            insert(Membership).values(
                id=membership_id,
                user_id=user_id,
                company_id=company_id,
                status="active",
                has_all_branch_access=False,
            )
        )
        await connection.execute(
            insert(MembershipBranchAccess).values(
                membership_id=membership_id,
                branch_id=branch_id,
                assigned_by_user_id=user_id,
            )
        )

    with pytest.raises(IntegrityError):
        async with identity_engine.begin() as connection:
            await connection.execute(
                insert(MembershipBranchAccess).values(
                    membership_id=membership_id,
                    branch_id=branch_id,
                )
            )

    with pytest.raises(IntegrityError):
        async with identity_engine.begin() as connection:
            await connection.execute(delete(User).where(User.id == user_id))


@pytest.mark.asyncio
async def test_employee_uniqueness_and_same_company_links(
    identity_engine: AsyncEngine,
) -> None:
    company_id, branch_id = await create_company_branch(
        identity_engine, company_code="EMPA", branch_code="HOME"
    )
    other_company_id, other_branch_id = await create_company_branch(
        identity_engine, company_code="EMPB", branch_code="AWAY"
    )
    user_id = await create_user(identity_engine, "employee@example.com")
    other_user_id = await create_user(identity_engine, "other-employee@example.com")
    membership_id = uuid4()
    other_membership_id = uuid4()
    async with identity_engine.begin() as connection:
        await connection.execute(
            insert(Membership).values(
                id=membership_id,
                user_id=user_id,
                company_id=company_id,
                status="active",
                has_all_branch_access=False,
            )
        )
        await connection.execute(
            insert(Membership).values(
                id=other_membership_id,
                user_id=other_user_id,
                company_id=other_company_id,
                status="active",
                has_all_branch_access=False,
            )
        )
        await connection.execute(
            insert(Employee).values(
                company_id=company_id,
                membership_id=membership_id,
                home_branch_id=branch_id,
                employee_number="E-100",
                first_name="Jordan",
                last_name="Rivera",
                display_name="Jordan Rivera",
                employee_type="employee",
                status="active",
            )
        )

    for conflicting_values in (
        {
            "company_id": company_id,
            "employee_number": "E-100",
        },
        {
            "company_id": company_id,
            "membership_id": membership_id,
            "employee_number": "E-101",
        },
        {
            "company_id": company_id,
            "home_branch_id": other_branch_id,
            "employee_number": "E-102",
        },
        {
            "company_id": company_id,
            "membership_id": other_membership_id,
            "employee_number": "E-103",
        },
    ):
        with pytest.raises(IntegrityError):
            async with identity_engine.begin() as connection:
                await connection.execute(
                    insert(Employee).values(
                        first_name="Conflict",
                        last_name="Record",
                        display_name="Conflict Record",
                        employee_type="contractor",
                        status="active",
                        **conflicting_values,
                    )
                )


def test_branch_access_cross_company_check_is_service_responsibility() -> None:
    columns = MembershipBranchAccess.__table__.c
    assert "company_id" not in columns
    access_default = Membership.__table__.c.has_all_branch_access.default
    assert access_default is not None
    assert access_default.arg is False
