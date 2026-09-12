# ruff: noqa: F811

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.payroll.commands import DraftCompensationAuthority, DraftPayrollPolicy
from app.payroll.contracts import (
    CompensationType,
    PayrollAdmissionState,
    PayrollConflictError,
    evaluate_payroll_admission,
)
from app.payroll.permissions import PayrollPermission
from app.payroll.service import PayrollAuthorityService
from tests.payroll.test_policy_authority import (
    FakeContext,
    approved_time_snapshot,
    payroll_database,  # noqa: F401
    policy_definition,
)


def contexts(ids: dict[str, UUID]) -> tuple[Any, Any]:
    manager: Any = FakeContext(
        company_id=ids["company_a"],
        user_id=ids["drafter"],
        permissions={
            PayrollPermission.POLICY_MANAGE,
            PayrollPermission.COMPENSATION_MANAGE,
        },
    )
    approver: Any = FakeContext(
        company_id=ids["company_a"],
        user_id=ids["approver"],
        permissions={
            PayrollPermission.POLICY_APPROVE,
            PayrollPermission.COMPENSATION_APPROVE,
            PayrollPermission.ADMISSION_REVIEW,
        },
    )
    return manager, approver


async def approved_policy(
    service: PayrollAuthorityService,
    session: AsyncSession,
    ids: dict[str, UUID],
    manager: Any,
    approver: Any,
):
    draft = await service.draft_policy(
        session,
        context=manager,
        command=DraftPayrollPolicy(
            policy_version=1,
            effective_start=date(2026, 8, 1),
            effective_end=None,
            definition=policy_definition(),
            decision_evidence_digest="1" * 64,
            audit_reason="Synthetic period-input assembly policy",
        ),
    )
    await service.approve_policy(session, context=approver, policy_id=draft.id)
    return await service.resolve_policy(
        session, company_id=ids["company_a"], as_of_date=date(2026, 8, 29)
    )


async def compensation_draft(
    service: PayrollAuthorityService,
    session: AsyncSession,
    ids: dict[str, UUID],
    manager: Any,
    *,
    version: int,
    effective_start: date,
    rate: str,
    supersedes: UUID | None = None,
):
    return await service.draft_compensation(
        session,
        context=manager,
        command=DraftCompensationAuthority(
            employee_id=ids["employee_a"],
            authority_version=version,
            effective_start=effective_start,
            effective_end=None,
            compensation_type=CompensationType.HOURLY,
            hourly_rate=Decimal(rate),
            salary_amount=None,
            salary_frequency=None,
            worker_class_reference="synthetic.period-assembly",
            additional_earning_types=(),
            recurring_components=(),
            decision_evidence_digest=f"{version}" * 64,
            audit_reason="Synthetic period-input compensation evidence",
            supersedes_authority_id=supersedes,
        ),
    )


@pytest.mark.asyncio
async def test_period_packet_resolves_current_compensation_and_replays(
    payroll_database: tuple[async_sessionmaker[AsyncSession], dict[str, UUID]],
) -> None:
    factory, ids = payroll_database
    service = PayrollAuthorityService()
    manager, approver = contexts(ids)
    async with factory() as session:
        policy = await approved_policy(service, session, ids, manager, approver)
        assert policy is not None
        first_draft = await compensation_draft(
            service,
            session,
            ids,
            manager,
            version=1,
            effective_start=date(2026, 8, 1),
            rate="30.00",
        )
        await service.approve_compensation(
            session, context=approver, authority_id=first_draft.id
        )
        compensation = await service.resolve_compensation(
            session,
            company_id=ids["company_a"],
            employee_id=ids["employee_a"],
            as_of_date=date(2026, 8, 29),
        )
        assert compensation is not None
        time_input = approved_time_snapshot(
            company_id=ids["company_a"],
            employee_id=ids["employee_a"],
            minutes=480,
        )
        packet = evaluate_payroll_admission(
            company_id=ids["company_a"],
            identity_resolved=True,
            policy=policy,
            compensation=compensation,
            time_input=time_input,
            pay_period_schedule_definition_id="synthetic.weekly-held-back",
            pay_period_schedule_version=1,
        )
        replay = evaluate_payroll_admission(
            company_id=ids["company_a"],
            identity_resolved=True,
            policy=policy,
            compensation=compensation,
            time_input=time_input,
            pay_period_schedule_definition_id="synthetic.weekly-held-back",
            pay_period_schedule_version=1,
        )
        assert packet.state is PayrollAdmissionState.READY_FOR_CALCULATION
        assert packet.admission_digest == replay.admission_digest
        assert packet.time_snapshot_digest == time_input.snapshot_digest
        assert packet.compensation_authority_id == compensation.authority_id
        assert len(time_input.approved_entries) == 1

        successor_draft = await compensation_draft(
            service,
            session,
            ids,
            manager,
            version=2,
            effective_start=date(2026, 9, 5),
            rate="32.00",
            supersedes=first_draft.id,
        )
        await service.approve_compensation(
            session, context=approver, authority_id=successor_draft.id
        )
        historical = await service.resolve_compensation(
            session,
            company_id=ids["company_a"],
            employee_id=ids["employee_a"],
            as_of_date=date(2026, 9, 4),
        )
        current = await service.resolve_compensation(
            session,
            company_id=ids["company_a"],
            employee_id=ids["employee_a"],
            as_of_date=date(2026, 9, 5),
        )
        assert historical is not None and historical.authority_id == first_draft.id
        assert current is not None and current.authority_id == successor_draft.id
        assert current.authority_digest != compensation.authority_digest


@pytest.mark.asyncio
async def test_missing_compensation_and_scope_block_without_mutating_time(
    payroll_database: tuple[async_sessionmaker[AsyncSession], dict[str, UUID]],
) -> None:
    factory, ids = payroll_database
    service = PayrollAuthorityService()
    manager, approver = contexts(ids)
    async with factory() as session:
        policy = await approved_policy(service, session, ids, manager, approver)
        assert policy is not None
        time_input = approved_time_snapshot(
            company_id=ids["company_a"],
            employee_id=ids["employee_a"],
            minutes=480,
        )
        original_digest = time_input.snapshot_digest
        missing = evaluate_payroll_admission(
            company_id=ids["company_a"],
            identity_resolved=True,
            policy=policy,
            compensation=None,
            time_input=time_input,
            pay_period_schedule_definition_id="synthetic.weekly-held-back",
            pay_period_schedule_version=1,
        )
        assert missing.state is PayrollAdmissionState.BLOCKED_COMPENSATION
        assert time_input.snapshot_digest == original_digest

        first_draft = await compensation_draft(
            service,
            session,
            ids,
            manager,
            version=1,
            effective_start=date(2026, 8, 1),
            rate="30.00",
        )
        await service.approve_compensation(
            session, context=approver, authority_id=first_draft.id
        )
        compensation = await service.resolve_compensation(
            session,
            company_id=ids["company_a"],
            employee_id=ids["employee_a"],
            as_of_date=date(2026, 8, 29),
        )
        assert compensation is not None
        cross_company = evaluate_payroll_admission(
            company_id=ids["company_b"],
            identity_resolved=True,
            policy=policy,
            compensation=compensation,
            time_input=time_input,
            pay_period_schedule_definition_id="synthetic.weekly-held-back",
            pay_period_schedule_version=1,
        )
        assert cross_company.state is PayrollAdmissionState.CONFLICTING
        assert time_input.snapshot_digest == original_digest

        with pytest.raises(PayrollConflictError, match="intervals overlap"):
            second = await compensation_draft(
                service,
                session,
                ids,
                manager,
                version=2,
                effective_start=date(2026, 8, 1),
                rate="31.00",
            )
            await service.approve_compensation(
                session, context=approver, authority_id=second.id
            )


@pytest.mark.asyncio
async def test_mid_period_compensation_change_requires_explicit_proration_policy(
    payroll_database: tuple[async_sessionmaker[AsyncSession], dict[str, UUID]],
) -> None:
    factory, ids = payroll_database
    authority = PayrollAuthorityService()
    manager, approver = contexts(ids)
    async with factory() as session:
        policy = await approved_policy(authority, session, ids, manager, approver)
        assert policy is not None
        first_draft = await compensation_draft(
            authority,
            session,
            ids,
            manager,
            version=1,
            effective_start=date(2026, 8, 1),
            rate="30.00",
        )
        await authority.approve_compensation(
            session, context=approver, authority_id=first_draft.id
        )
        successor_draft = await compensation_draft(
            authority,
            session,
            ids,
            manager,
            version=2,
            effective_start=date(2026, 9, 1),
            rate="32.00",
            supersedes=first_draft.id,
        )
        await authority.approve_compensation(
            session, context=approver, authority_id=successor_draft.id
        )
        period_start_compensation = await authority.resolve_compensation(
            session,
            company_id=ids["company_a"],
            employee_id=ids["employee_a"],
            as_of_date=date(2026, 8, 29),
        )
        assert period_start_compensation is not None
        with pytest.raises(PayrollConflictError, match="proration policy"):
            await authority.resolve_period_compensation(
                session,
                company_id=ids["company_a"],
                employee_id=ids["employee_a"],
                period_start=date(2026, 8, 29),
                period_end=date(2026, 9, 4),
            )
