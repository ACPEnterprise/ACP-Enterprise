from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from app.core.config import settings
from app.equipment_readiness.models import (
    EquipmentAttention,
    EquipmentCatalogItem,
    EquipmentPlacement,
)
from app.equipment_readiness.service import (
    EquipmentNotFound,
    equipment_readiness_service,
)
from app.platform.branch.models import Branch
from app.platform.company.models import Company
from app.platform.employees.models import Employee
from app.platform.users.models import User
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def equipment_database():
    engine = create_async_engine(settings.database_url)
    connection = await engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(connection, expire_on_commit=False)
    company_id, branch_id, user_id = uuid4(), uuid4(), uuid4()
    async with factory() as session, session.begin():
        session.add(
            Company(
                id=company_id,
                name="Equipment Readiness Qualification",
                code=f"EQ{uuid4().hex[:8].upper()}",
                status="active",
                timezone="America/New_York",
            )
        )
        session.add(
            User(
                id=user_id,
                normalized_email=f"equipment-{uuid4().hex}@example.test",
                first_name="Equipment",
                last_name="Manager",
                display_name="Equipment Manager",
                status="active",
                authorization_version=1,
            )
        )
        await session.flush()
        session.add(
            Branch(
                id=branch_id,
                company_id=company_id,
                name="Equipment Branch",
                code=f"EB{uuid4().hex[:8].upper()}",
                status="active",
                timezone="America/New_York",
                is_primary=True,
            )
        )
    context = SimpleNamespace(
        company=SimpleNamespace(id=company_id),
        user=SimpleNamespace(id=user_id),
        authorized_branch_ids=(branch_id,),
        effective_roles=(SimpleNamespace(code="FIELD_MANAGER"),),
        can_access_branch=lambda value: value == branch_id,
    )
    try:
        yield factory, context, company_id, branch_id
    finally:
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_employee_setting_not_position_controls_daily_prompt(
    equipment_database,
) -> None:
    factory, context, company_id, branch_id = equipment_database
    now = datetime.now(timezone.utc)
    work_date = now.date()
    combinations = (
        ("Technician", "not_required", False),
        ("Technician", "required_at_clock_in", True),
        ("Helper", "not_required", False),
        ("Helper", "required_at_clock_in", True),
        ("Field Service Manager", "not_required", False),
        ("Field Service Manager", "required_at_clock_in", True),
    )
    async with factory() as session, session.begin():
        catalog = EquipmentCatalogItem(
            company_id=company_id,
            branch_id=branch_id,
            code=f"QUAL-{uuid4().hex[:8].upper()}",
            display_name="Qualification Equipment",
            capability_code="QUALIFICATION_EQUIPMENT",
            item_kind="non_serialized_item",
            serialization_required=False,
            provenance={"source": "release_qualification"},
            created_by_user_id=context.user.id,
        )
        session.add(catalog)
        await session.flush()
        employees = []
        for ordinal, (position, requirement, _) in enumerate(combinations, start=1):
            employee = Employee(
                company_id=company_id,
                home_branch_id=branch_id,
                employee_number=f"EQ-{uuid4().hex[:8].upper()}",
                first_name="Equipment",
                last_name=str(ordinal),
                display_name=f"Equipment {ordinal}",
                job_title=position,
                employee_type="employee",
                status="active",
                equipment_checklist_requirement=requirement,
            )
            session.add(employee)
            await session.flush()
            session.add(
                EquipmentPlacement(
                    company_id=company_id,
                    branch_id=branch_id,
                    catalog_item_id=catalog.id,
                    home_kind="shop",
                    current_location_kind="employee",
                    current_custodian_employee_id=employee.id,
                    custody_effective_at=now,
                    readiness_state="ready",
                    service_state="available",
                    missing_components=[],
                    version=1,
                    request_digest=uuid4().hex * 2,
                    idempotency_key=f"equipment-qualification-{uuid4().hex}",
                    updated_at=now,
                )
            )
            employees.append(employee)

        terminated = Employee(
            company_id=company_id,
            home_branch_id=branch_id,
            employee_number=f"EQ-{uuid4().hex[:8].upper()}",
            first_name="Former",
            last_name="Employee",
            display_name="Former Employee",
            job_title="Technician",
            employee_type="employee",
            status="terminated",
            termination_date=work_date,
            equipment_checklist_requirement="required_at_clock_in",
        )
        session.add(terminated)

    async with factory() as session:
        for employee, (_, _, expected) in zip(employees, combinations, strict=True):
            prompt = await equipment_readiness_service.daily_prompt(
                session, context, employee.id, work_date
            )
            assert prompt["required"] is expected
        with pytest.raises(EquipmentNotFound):
            await equipment_readiness_service.daily_prompt(
                session, context, terminated.id, work_date
            )


@pytest.mark.asyncio
async def test_field_manager_attention_is_branch_scoped_and_read_only(
    equipment_database,
) -> None:
    factory, context, company_id, branch_id = equipment_database
    now = datetime.now(timezone.utc)
    async with factory() as session, session.begin():
        attention = EquipmentAttention(
            company_id=company_id,
            branch_id=branch_id,
            identity_key=f"equipment-qualification:{uuid4()}",
            attention_code="MISSING_OR_UNKNOWN",
            priority="needs_attention",
            state="open",
            title="Equipment needs attention",
            explanation="Qualification evidence",
            responsibility_code="FIELD_OPERATIONS",
            first_observed_at=now,
            last_observed_at=now,
            evidence_digest=uuid4().hex * 2,
            version=1,
        )
        session.add(attention)

    async with factory() as session:
        rows = await equipment_readiness_service.attention(session, context)
        assert [row.id for row in rows] == [attention.id]
        technician = SimpleNamespace(
            **{
                **context.__dict__,
                "effective_roles": (SimpleNamespace(code="TECHNICIAN"),),
            }
        )
        assert await equipment_readiness_service.attention(session, technician) == []
