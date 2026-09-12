# ruff: noqa: F811

from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.payroll.contracts import CompensationType, PayrollConflictError
from app.payroll.proration import (
    ApprovedProrationPolicy,
    CompensationProrationMethod,
    CompensationProrationPolicyService,
    allocate_hourly_time,
)
from app.timekeeping.contracts import canonical_digest, seal_payroll_time_input
from tests.payroll.test_period_input_assembly_acceptance import (
    compensation_draft,
    contexts,
)
from tests.payroll.test_policy_authority import (
    approved_time_snapshot,
    payroll_database,  # noqa: F401
)


def approved_policy(record) -> ApprovedProrationPolicy:  # type: ignore[no-untyped-def]
    assert record.approved_by_user_id is not None and record.approved_at is not None
    return ApprovedProrationPolicy(
        policy_id=record.id,
        company_id=record.company_id,
        policy_version=record.policy_version,
        effective_start=record.effective_start,
        effective_end=record.effective_end,
        method=CompensationProrationMethod(record.method),
        rationale=record.rationale,
        provenance=record.provenance,
        approved_by_user_id=record.approved_by_user_id,
        approved_at=record.approved_at,
        supersedes_policy_id=record.supersedes_policy_id,
        policy_digest=record.policy_digest,
    )


async def compensation_pair(
    session: AsyncSession, ids: dict[str, UUID], manager: Any, approver: Any
):
    from app.payroll.service import PayrollAuthorityService

    authority = PayrollAuthorityService()
    first = await compensation_draft(
        authority,
        session,
        ids,
        manager,
        version=1,
        effective_start=date(2026, 8, 1),
        rate="30.00",
    )
    await authority.approve_compensation(
        session, context=approver, authority_id=first.id
    )
    second = await compensation_draft(
        authority,
        session,
        ids,
        manager,
        version=2,
        effective_start=date(2026, 9, 1),
        rate="32.00",
        supersedes=first.id,
    )
    await authority.approve_compensation(
        session, context=approver, authority_id=second.id
    )
    before = await authority.resolve_compensation(
        session,
        company_id=ids["company_a"],
        employee_id=ids["employee_a"],
        as_of_date=date(2026, 8, 31),
    )
    after = await authority.resolve_compensation(
        session,
        company_id=ids["company_a"],
        employee_id=ids["employee_a"],
        as_of_date=date(2026, 9, 1),
    )
    assert before is not None and after is not None
    return before, after


@pytest.mark.asyncio
async def test_policy_is_explicit_approved_versioned_and_superseded(
    payroll_database: tuple[async_sessionmaker[AsyncSession], dict[str, UUID]],
) -> None:
    factory, ids = payroll_database
    manager, approver = contexts(ids)
    service = CompensationProrationPolicyService()
    async with factory() as session:
        unselected = await service.draft(
            session,
            context=manager,
            policy_version=1,
            effective_start=date(2026, 8, 1),
            effective_end=None,
            method=CompensationProrationMethod.UNSELECTED,
            rationale="Owner decision has not been supplied",
            provenance="synthetic.owner-decision-pending",
        )
        with pytest.raises(PayrollConflictError, match="unselected"):
            await service.approve(session, context=approver, policy_id=unselected.id)
        block = await service.draft(
            session,
            context=manager,
            policy_version=2,
            effective_start=date(2026, 8, 1),
            effective_end=None,
            method=CompensationProrationMethod.BLOCK_PAYROLL,
            rationale="Synthetic explicit block",
            provenance="synthetic.owner-approved",
        )
        await service.approve(session, context=approver, policy_id=block.id)
        successor = await service.draft(
            session,
            context=manager,
            policy_version=3,
            effective_start=date(2026, 9, 1),
            effective_end=None,
            method=CompensationProrationMethod.BY_WORK_DATE,
            rationale="Synthetic work-date selection",
            provenance="synthetic.owner-approved",
            supersedes_policy_id=block.id,
        )
        await service.approve(session, context=approver, policy_id=successor.id)
        historical = await service.resolve_record(
            session, company_id=ids["company_a"], as_of_date=date(2026, 8, 31)
        )
        current = await service.resolve_record(
            session, company_id=ids["company_a"], as_of_date=date(2026, 9, 1)
        )
        assert historical is not None and historical.id == block.id
        assert current is not None and current.id == successor.id
        assert block.policy_digest != successor.policy_digest
        assert successor.approved_by_user_id == ids["approver"]


@pytest.mark.asyncio
async def test_hourly_work_date_allocation_is_unique_and_replay_stable(
    payroll_database: tuple[async_sessionmaker[AsyncSession], dict[str, UUID]],
) -> None:
    factory, ids = payroll_database
    manager, approver = contexts(ids)
    policy_service = CompensationProrationPolicyService()
    async with factory() as session:
        first, second = await compensation_pair(session, ids, manager, approver)
        draft = await policy_service.draft(
            session,
            context=manager,
            policy_version=1,
            effective_start=date(2026, 8, 1),
            effective_end=None,
            method=CompensationProrationMethod.BY_WORK_DATE,
            rationale="Synthetic acceptance",
            provenance="synthetic.fixture",
        )
        record = await policy_service.approve(
            session, context=approver, policy_id=draft.id
        )
        snapshot = approved_time_snapshot(
            company_id=ids["company_a"],
            employee_id=ids["employee_a"],
            minutes=120,
        )
        before = replace(snapshot.approved_entries[0], work_date=date(2026, 8, 31))
        before = replace(
            before, evidence_digest=canonical_digest(before.canonical_content())
        )
        after_draft = replace(
            before,
            entry_id=uuid4(),
            revision_id=uuid4(),
            work_date=date(2026, 9, 1),
            approved_duration_minutes=180,
            evidence_digest="",
        )
        after = replace(
            after_draft,
            evidence_digest=canonical_digest(after_draft.canonical_content()),
        )
        time = seal_payroll_time_input(
            company_id=ids["company_a"],
            employee_id=ids["employee_a"],
            pay_period_id=uuid4(),
            period_start=date(2026, 8, 29),
            period_end=date(2026, 9, 4),
            approved_entries=(before, after),
        )
        result = allocate_hourly_time(
            company_id=ids["company_a"],
            employee_id=ids["employee_a"],
            policy=approved_policy(record),
            time=time.approved_entries,
            compensation=(first, second),
        )
        replay = allocate_hourly_time(
            company_id=ids["company_a"],
            employee_id=ids["employee_a"],
            policy=approved_policy(record),
            time=time.approved_entries,
            compensation=(first, second),
        )
        assert result.total_payable_minutes == 300
        assert result.result_digest == replay.result_digest
        assert tuple(item.compensation_authority_id for item in result.allocations) == (
            first.authority_id,
            second.authority_id,
        )
        with pytest.raises(PayrollConflictError, match="duplicated"):
            allocate_hourly_time(
                company_id=ids["company_a"],
                employee_id=ids["employee_a"],
                policy=approved_policy(record),
                time=(before, before),
                compensation=(first, second),
            )


@pytest.mark.asyncio
async def test_salary_and_unselected_policy_fail_closed(
    payroll_database: tuple[async_sessionmaker[AsyncSession], dict[str, UUID]],
) -> None:
    factory, ids = payroll_database
    manager, approver = contexts(ids)
    snapshot = approved_time_snapshot(
        company_id=ids["company_a"], employee_id=ids["employee_a"], minutes=60
    )
    policy = ApprovedProrationPolicy(
        policy_id=uuid4(),
        company_id=ids["company_a"],
        policy_version=1,
        effective_start=date(2026, 8, 1),
        effective_end=None,
        method=CompensationProrationMethod.UNSELECTED,
        rationale="Owner decision pending",
        provenance="synthetic",
        approved_by_user_id=approver.user.id,
        approved_at=snapshot.approved_entries[0].approved_at,
        supersedes_policy_id=None,
        policy_digest="f" * 64,
    )
    with pytest.raises(PayrollConflictError, match="blocks Payroll"):
        allocate_hourly_time(
            company_id=ids["company_a"],
            employee_id=ids["employee_a"],
            policy=policy,
            time=snapshot.approved_entries,
            compensation=(),
        )

    async with factory() as session:
        hourly, _ = await compensation_pair(session, ids, manager, approver)
        salary = replace(
            hourly,
            compensation_type=CompensationType.SALARIED,
            hourly_rate=None,
            salary_amount=Decimal("60000.00"),
            salary_frequency="annual",
        )
        selected = replace(policy, method=CompensationProrationMethod.BY_WORK_DATE)
        with pytest.raises(PayrollConflictError, match="type is unsupported"):
            allocate_hourly_time(
                company_id=ids["company_a"],
                employee_id=ids["employee_a"],
                policy=selected,
                time=snapshot.approved_entries,
                compensation=(salary,),
            )
