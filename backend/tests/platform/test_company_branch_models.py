from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import CheckConstraint, Table, UniqueConstraint
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.platform.branch.models import Branch
from app.platform.company.models import Company


def test_company_model_shape() -> None:
    table = cast(Table, Company.__table__)

    assert Company.__tablename__ == "companies"
    assert table.c.id.primary_key
    assert not table.c.name.nullable
    assert not table.c.code.nullable
    assert not table.c.status.nullable
    assert not table.c.timezone.nullable
    assert table.c.archived_at.nullable

    constraints = {constraint.name for constraint in table.constraints}
    assert "uq_companies_code" in constraints
    assert "ck_companies_status" in constraints


def test_branch_model_shape_and_ownership() -> None:
    table = cast(Table, Branch.__table__)

    assert Branch.__tablename__ == "branches"
    assert not table.c.company_id.nullable
    assert table.c.archived_at.nullable

    company_fk = next(iter(table.c.company_id.foreign_keys))
    assert company_fk.target_fullname == "companies.id"
    assert company_fk.ondelete == "RESTRICT"
    assert company_fk.constraint is not None
    assert company_fk.constraint.name == "fk_branches_company_id_companies"

    unique_constraints = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    check_constraints = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "uq_branches_company_id_code" in unique_constraints
    assert "ck_branches_status" in check_constraints


def test_branch_primary_index_is_company_scoped_and_partial() -> None:
    table = cast(Table, Branch.__table__)
    primary_index = next(
        index
        for index in table.indexes
        if index.name == "uq_branches_active_primary_company"
    )

    assert primary_index.unique
    assert [column.name for column in primary_index.columns] == ["company_id"]
    predicate = str(primary_index.dialect_options["postgresql"]["where"])
    assert "is_primary" in predicate
    assert "status = 'active'" in predicate
    assert "archived_at IS NULL" in predicate


def test_company_branch_relationships_do_not_delete_orphans() -> None:
    assert Company.branches.property.back_populates == "company"
    assert Company.branches.property.cascade.delete is False
    assert Company.branches.property.cascade.delete_orphan is False
    assert Branch.company.property.back_populates == "branches"


@pytest.mark.asyncio
async def test_company_and_branch_database_constraints() -> None:
    test_engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    company_id = uuid4()
    async with session_factory() as session:
        session.add(
            Company(
                id=company_id,
                name="All County Plumbing & Leak",
                code="ACP",
                status="active",
                timezone="America/New_York",
            )
        )
        await session.commit()

    async with session_factory() as session:
        session.add(
            Company(
                name="Duplicate Code Company",
                code="ACP",
                status="active",
                timezone="America/Chicago",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()

    async with session_factory() as session:
        session.add_all(
            [
                Branch(
                    company_id=company_id,
                    name="Main Office",
                    code="MAIN",
                    status="active",
                    timezone="America/New_York",
                    is_primary=True,
                ),
                Branch(
                    company_id=company_id,
                    name="North Office",
                    code="NORTH",
                    status="active",
                    timezone="America/New_York",
                    is_primary=True,
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            await session.commit()

    async with session_factory() as session:
        session.add_all(
            [
                Branch(
                    company_id=company_id,
                    name="Main Office",
                    code="MAIN",
                    status="active",
                    timezone="America/New_York",
                    is_primary=True,
                ),
                Branch(
                    company_id=company_id,
                    name="Secondary Office",
                    code="MAIN",
                    status="inactive",
                    timezone="America/New_York",
                    is_primary=False,
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            await session.commit()

    async with session_factory() as session:
        session.add(
            Branch(
                company_id=company_id,
                name="Main Office",
                code="MAIN",
                status="active",
                timezone="America/New_York",
                is_primary=True,
            )
        )
        await session.commit()

    async with session_factory() as session:
        company = await session.get(Company, company_id)
        assert company is not None
        await session.delete(company)
        with pytest.raises(IntegrityError):
            await session.commit()

    await test_engine.dispose()
