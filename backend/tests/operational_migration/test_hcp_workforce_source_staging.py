from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from app.core.config import settings
from app.operational_migration.hcp_workforce_source_staging import (
    AUTHORITY_PATH,
    WorkforceSourcePacket,
    WorkforceSourceStagingService,
)
from app.operational_migration.models import (
    HcpEmployeeSourceCrosswalk,
    HcpMigrationMasterRun,
)
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.employees.models import Employee
from app.platform.users.models import User
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def test_authority_packet_is_exact_and_deterministic() -> None:
    first = WorkforceSourcePacket.load()
    second = WorkforceSourcePacket.load(Path(AUTHORITY_PATH))

    assert first == second
    assert len(first.records) == 7
    assert sum(record.creates_candidate for record in first.records) == 6
    assert sum(record.employment_status == "TERMINATED" for record in first.records) == 1
    assert sum(
        record.owner_disposition == "OWNER_IDENTITY_DECISION_REQUIRED"
        for record in first.records
    ) == 1
    assert len(first.digest) == 64


def test_alex_preserves_provider_email_and_owner_current_email_separately() -> None:
    packet = WorkforceSourcePacket.load()
    alex = next(
        record
        for record in packet.records
        if record.provider_employee_id == "pro_10853bfb63874a0b9d17cab14d1da20b"
    )

    assert alex.source_email == "alexallcountyleaks@gmail.com"
    assert alex.owner_current_email == "alexallcountyplumbingandleak@gmail.com"
    assert alex.owner_disposition == "OWNER_IDENTITY_DECISION_REQUIRED"


def test_adam_is_non_invitational_terminated_history() -> None:
    packet = WorkforceSourcePacket.load()
    adam = next(
        record
        for record in packet.records
        if record.provider_employee_id == "pro_4f1d81e3d31b4ffa9072dd6a32906586"
    )

    assert adam.employment_status == "TERMINATED"
    assert adam.status_effective_at == "2026-09-18T00:00:00-04:00"
    assert adam.owner_current_email is None
    assert not adam.creates_candidate
    assert adam.crosswalk_disposition == "EXCLUDE_EMPLOYEE_HOLD_ASSIGNMENTS"


def test_packet_rejects_duplicate_or_changed_authority() -> None:
    packet = WorkforceSourcePacket.load()
    duplicate = replace(packet, records=(*packet.records[:-1], packet.records[0]))
    with pytest.raises(ValueError, match="duplicate HCP Employee identity"):
        duplicate.validate()

    active = packet.records[0]
    invalid = replace(active, employment_status="TERMINATED")
    with pytest.raises(ValueError, match="terminated source Employee"):
        invalid.validate()


@pytest_asyncio.fixture
async def staging_database():
    engine = create_async_engine(settings.database_url)
    connection = await engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(
        connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    company_id, branch_id, actor_id, membership_id, master_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    packet = WorkforceSourcePacket.load()
    async with factory() as session, session.begin():
        session.add(
            Company(
                id=company_id,
                name="Workforce Source Staging Test",
                code=f"WS{uuid4().hex[:8].upper()}",
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
                    normalized_email=f"staging-{uuid4().hex}@example.test",
                    first_name="Migration",
                    last_name="Operator",
                    display_name="Migration Operator",
                    status="active",
                    authorization_version=1,
                ),
            ]
        )
        await session.flush()
        session.add(
            Membership(
                id=membership_id,
                user_id=actor_id,
                company_id=company_id,
                status="active",
                default_branch_id=branch_id,
            )
        )
        session.add(
            HcpMigrationMasterRun(
                id=master_id,
                company_id=company_id,
                branch_id=branch_id,
                actor_user_id=actor_id,
                package_digest=packet.source_package_digest,
                collection_digests={},
                transformation_contracts={},
                owner_receipts={},
                schema_head="fixture",
                implementation_version="fixture",
                supported_entities=["employee"],
                baseline_counts={},
                source_counts={},
                transformed_counts={},
                persisted_counts={},
                hold_counts={},
                exception_counts={},
                rejection_counts={},
                unresolved_counts={},
                non_applicable_counts={},
                child_run_ids={},
                reconciliation_digest=None,
                replay_state={},
                resume_state={},
                rollback_state={},
                input_digest="a" * 64,
                attestation_digest="b" * 64,
                status="completed_current_operational",
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )
        )
    context = SimpleNamespace(
        company=SimpleNamespace(id=company_id),
        user=SimpleNamespace(id=actor_id),
        active_branch=SimpleNamespace(id=branch_id, code="MAIN"),
        has_permission=lambda _permission: True,
    )
    try:
        yield factory, context, master_id
    finally:
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_stage_and_exact_replay_are_idempotent(staging_database) -> None:
    factory, context, master_id = staging_database
    service = WorkforceSourceStagingService()
    packet = WorkforceSourcePacket.load()

    async with factory() as session, session.begin():
        first = await service.stage(
            session, context=context, master_run_id=master_id, packet=packet
        )
    async with factory() as session, session.begin():
        replay = await service.stage(
            session, context=context, master_run_id=master_id, packet=packet
        )
        employees = await session.scalar(
            select(func.count()).select_from(Employee).where(
                Employee.company_id == context.company.id
            )
        )
        crosswalks = await session.scalar(
            select(func.count()).select_from(HcpEmployeeSourceCrosswalk).where(
                HcpEmployeeSourceCrosswalk.company_id == context.company.id
            )
        )
        adam = await session.scalar(
            select(HcpEmployeeSourceCrosswalk).where(
                HcpEmployeeSourceCrosswalk.company_id == context.company.id,
                HcpEmployeeSourceCrosswalk.native_employee_id
                == "pro_4f1d81e3d31b4ffa9072dd6a32906586",
            )
        )

    assert first.staged == 7
    assert first.created_candidates == 6
    assert first.terminated == 1
    assert first.owner_decisions == 1
    assert first.replayed == 0
    assert replay.created_candidates == 0
    assert replay.replayed == 7
    assert employees == 6
    assert crosswalks == 7
    assert adam is not None
    assert adam.employee_id is None
    assert adam.disposition == "EXCLUDE_EMPLOYEE_HOLD_ASSIGNMENTS"
