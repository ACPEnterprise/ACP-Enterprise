import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.events.models import BusinessEvent
from app.payroll.contracts import PayrollAuthorizationError, PayrollConflictError
from app.payroll.finalization import (
    GrossResultLifecycle,
    GrossReviewDecision,
    PayPeriodCalculationStatus,
    PayrollGrossResultService,
)
from app.payroll.models import (
    CompanyPayrollPolicyVersion,
    EmployeeCompensationAuthorityVersion,
    PayrollGrossCalculationResultRecord,
    PayrollGrossCalculationReviewRecord,
)
from app.payroll.permissions import PayrollPermission
from app.platform.audit.models import AuditRecord
from app.platform.branch.models import Branch
from app.platform.company.models import Company
from app.platform.employees.models import Employee
from app.platform.users.models import User
from app.timekeeping.contracts import seal_payroll_time_input
from app.timekeeping.models import PayPeriod, PayrollTimeInputRecord
from tests.payroll.test_gross_pay_calculation import (
    NOW,
    calculate,
    compensation,
    policy,
    time_input,
)


class FakeContext:
    def __init__(self, company_id: UUID, user_id: UUID, permissions: set[str]):
        self.company = SimpleNamespace(id=company_id)
        self.user = SimpleNamespace(id=user_id)
        self._permissions = permissions

    def has_permission(self, permission: str) -> bool:
        return permission in self._permissions


@pytest_asyncio.fixture
async def finalization_database() -> AsyncIterator[
    tuple[async_sessionmaker[AsyncSession], dict[str, object]]
]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    company_id, other_company_id = uuid4(), uuid4()
    branch_id, other_branch_id, actor_id, reviewer_id, employee_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    policy_value = policy(company_id)
    compensation_value = compensation(company_id, employee_id)
    async with factory() as session, session.begin():
        session.add_all(
            [
                Company(
                    id=company_id,
                    name="Synthetic Payroll Company",
                    code=f"GROSS{uuid4().hex[:6].upper()}",
                    status="active",
                    timezone="America/New_York",
                ),
                Company(
                    id=other_company_id,
                    name="Other Synthetic Company",
                    code=f"OTHER{uuid4().hex[:6].upper()}",
                    status="active",
                    timezone="America/New_York",
                ),
                User(
                    id=actor_id,
                    normalized_email=f"calculator-{uuid4().hex}@example.test",
                    first_name="Synthetic",
                    last_name="Calculator",
                    display_name="Synthetic Calculator",
                    status="active",
                    authorization_version=1,
                ),
                User(
                    id=reviewer_id,
                    normalized_email=f"reviewer-{uuid4().hex}@example.test",
                    first_name="Synthetic",
                    last_name="Reviewer",
                    display_name="Synthetic Reviewer",
                    status="active",
                    authorization_version=1,
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                Branch(
                    id=branch_id,
                    company_id=company_id,
                    name="Main",
                    code=f"MAIN{uuid4().hex[:4].upper()}",
                    status="active",
                    timezone="America/New_York",
                    is_primary=True,
                ),
                Branch(
                    id=other_branch_id,
                    company_id=other_company_id,
                    name="Other",
                    code=f"OTHR{uuid4().hex[:4].upper()}",
                    status="active",
                    timezone="America/New_York",
                    is_primary=True,
                ),
            ]
        )
        await session.flush()
        session.add(
            Employee(
                id=employee_id,
                company_id=company_id,
                home_branch_id=branch_id,
                employee_number=f"SYN-{uuid4().hex[:8]}",
                first_name="Synthetic",
                last_name="Employee",
                display_name="Synthetic Employee",
                employee_type="employee",
                status="active",
            )
        )
        await session.flush()
        session.add(
            CompanyPayrollPolicyVersion(
                id=policy_value.policy_id,
                company_id=company_id,
                policy_version=policy_value.policy_version,
                effective_start=policy_value.effective_start,
                effective_end=policy_value.effective_end,
                lifecycle="approved",
                definition_version="payroll.company-policy.v1",
                definition=policy_value.definition.canonical_content(),
                decision_evidence_digest=policy_value.decision_evidence_digest,
                authority_digest=policy_value.authority_digest,
                supersedes_policy_id=None,
                drafted_by_user_id=actor_id,
                approved_by_user_id=reviewer_id,
                approved_at=NOW,
                retired_by_user_id=None,
                retired_at=None,
                audit_reason="Synthetic finalization qualification",
            )
        )
        session.add(
            EmployeeCompensationAuthorityVersion(
                id=compensation_value.authority_id,
                company_id=company_id,
                employee_id=employee_id,
                authority_version=compensation_value.authority_version,
                effective_start=compensation_value.effective_start,
                effective_end=compensation_value.effective_end,
                lifecycle="approved",
                definition_version="payroll.compensation-authority.v1",
                compensation_type=compensation_value.compensation_type.value,
                hourly_rate=compensation_value.hourly_rate,
                salary_amount=None,
                salary_frequency=None,
                worker_class_reference=compensation_value.worker_class_reference,
                additional_earning_types=[],
                recurring_components=[],
                decision_evidence_digest=compensation_value.decision_evidence_digest,
                authority_digest=compensation_value.authority_digest,
                supersedes_authority_id=None,
                drafted_by_user_id=actor_id,
                approved_by_user_id=reviewer_id,
                approved_at=NOW,
                retired_by_user_id=None,
                retired_at=None,
                audit_reason="Synthetic finalization qualification",
            )
        )
    try:
        yield factory, {
            "company_id": company_id,
            "other_company_id": other_company_id,
            "actor_id": actor_id,
            "reviewer_id": reviewer_id,
            "employee_id": employee_id,
            "policy": policy_value,
            "compensation": compensation_value,
        }
    finally:
        await engine.dispose()


def candidate(
    values: dict[str, object],
    minutes: int = 600,
    *,
    pay_period_id: UUID | None = None,
    **overrides,
):  # type: ignore[no-untyped-def]
    company_id = values["company_id"]
    employee_id = values["employee_id"]
    snapshot = time_input(company_id, employee_id, minutes)  # type: ignore[arg-type]
    if pay_period_id is not None:
        snapshot = seal_payroll_time_input(
            company_id=snapshot.company_id,
            employee_id=snapshot.employee_id,
            pay_period_id=pay_period_id,
            period_start=snapshot.period_start,
            period_end=snapshot.period_end,
            approved_entries=snapshot.approved_entries,
        )
    return calculate(values["policy"], values["compensation"], snapshot, **overrides)


async def seed_candidate_time(
    session: AsyncSession, value, actor_id: UUID  # type: ignore[no-untyped-def]
) -> None:
    existing = await session.get(PayPeriod, value.pay_period.pay_period_id)
    if existing is not None:
        return
    session.add(
        PayPeriod(
            id=value.pay_period.pay_period_id,
            company_id=value.company_id,
            period_start=value.pay_period.period_start,
            period_end=value.pay_period.period_end,
            processing_date=value.pay_period.period_end + timedelta(days=6),
            payday=value.pay_period.period_end + timedelta(days=7),
            timezone="America/New_York",
            schedule_definition_id=value.pay_period.schedule_definition_id,
            schedule_version=value.pay_period.schedule_version,
            created_by_user_id=actor_id,
        )
    )
    await session.flush()
    session.add(
        PayrollTimeInputRecord(
            id=uuid4(),
            snapshot_identity=value.time_snapshot_id,
            snapshot_version="payroll.time-input.v1",
            company_id=value.company_id,
            employee_id=value.employee_id,
            pay_period_id=value.pay_period.pay_period_id,
            approved_revision_ids=[],
            total_approved_minutes=value.components[0].payable_minutes,
            snapshot_digest=value.time_snapshot_digest,
            created_by_user_id=actor_id,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_persist_replay_review_and_safe_evidence(
    finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]],
) -> None:
    factory, values = finalization_database
    execute: Any = FakeContext(
        values["company_id"],  # type: ignore[arg-type]
        values["actor_id"],  # type: ignore[arg-type]
        {PayrollPermission.CALCULATION_EXECUTE, PayrollPermission.CALCULATION_READ},
    )
    review: Any = FakeContext(
        values["company_id"],  # type: ignore[arg-type]
        values["reviewer_id"],  # type: ignore[arg-type]
        {PayrollPermission.CALCULATION_REVIEW, PayrollPermission.CALCULATION_READ},
    )
    service = PayrollGrossResultService()
    value = candidate(values)
    async with factory() as session:
        await seed_candidate_time(session, value, values["actor_id"])  # type: ignore[arg-type]
        first = await service.persist_candidate(session, context=execute, candidate=value)
        replay = await service.persist_candidate(session, context=execute, candidate=value)
        assert first.id == replay.id
        initiated = await service.initiate_review(
            session,
            context=review,
            result_id=first.id,
            reason_code="synthetic_review",
            reviewed_at=NOW,
        )
        accepted = await service.decide_review(
            session,
            context=review,
            result_id=first.id,
            decision=GrossReviewDecision.ACCEPTED,
            reason_code="synthetic_accepted",
            reviewed_at=datetime(2026, 9, 10, 16, tzinfo=timezone.utc),
        )
        await session.refresh(first)
        assert initiated.review_sequence == 1 and accepted.review_sequence == 2
        assert first.lifecycle == GrossResultLifecycle.APPROVED.value
        audits = tuple((await session.scalars(select(AuditRecord))).all())
        events = tuple((await session.scalars(select(BusinessEvent))).all())
        assert audits and events
        assert all("gross_pay_total" not in item.details for item in audits)
        assert all("gross_pay_total" not in item.payload for item in events)


@pytest.mark.asyncio
async def test_supersession_history_active_uniqueness_and_contradiction(
    finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]],
) -> None:
    factory, values = finalization_database
    context: Any = FakeContext(
        values["company_id"],  # type: ignore[arg-type]
        values["actor_id"],  # type: ignore[arg-type]
        {PayrollPermission.CALCULATION_EXECUTE, PayrollPermission.CALCULATION_READ},
    )
    service = PayrollGrossResultService()
    pay_period_id = uuid4()
    first_candidate = candidate(values, 600, pay_period_id=pay_period_id)
    async with factory() as session:
        await seed_candidate_time(
            session, first_candidate, values["actor_id"]  # type: ignore[arg-type]
        )
        first = await service.persist_candidate(
            session, context=context, candidate=first_candidate
        )
        conflicting = candidate(values, 601, pay_period_id=pay_period_id)
        session.add(
            PayrollTimeInputRecord(
                id=uuid4(),
                snapshot_identity=conflicting.time_snapshot_id,
                snapshot_version="payroll.time-input.v1",
                company_id=conflicting.company_id,
                employee_id=conflicting.employee_id,
                pay_period_id=conflicting.pay_period.pay_period_id,
                approved_revision_ids=[],
                total_approved_minutes=conflicting.components[0].payable_minutes,
                snapshot_digest=conflicting.time_snapshot_digest,
                created_by_user_id=values["actor_id"],
            )
        )
        await session.commit()
        with pytest.raises(PayrollConflictError, match="active"):
            await service.persist_candidate(
                session, context=context, candidate=conflicting
            )
        superseding = candidate(
            values,
            601,
            pay_period_id=pay_period_id,
            supersedes_result_id=first_candidate.result_id,
        )
        # The corrected snapshot shares the authoritative pay period but has a
        # distinct immutable snapshot identity.
        session.add(
            PayrollTimeInputRecord(
                id=uuid4(),
                snapshot_identity=superseding.time_snapshot_id,
                snapshot_version="payroll.time-input.v1",
                company_id=superseding.company_id,
                employee_id=superseding.employee_id,
                pay_period_id=superseding.pay_period.pay_period_id,
                approved_revision_ids=[],
                total_approved_minutes=superseding.components[0].payable_minutes,
                snapshot_digest=superseding.time_snapshot_digest,
                created_by_user_id=values["actor_id"],
            )
        )
        await session.commit()
        second = await service.persist_candidate(
            session, context=context, candidate=superseding
        )
        await session.refresh(first)
        assert first.lifecycle == GrossResultLifecycle.SUPERSEDED.value
        assert second.supersedes_result_id == first.id
        history = await service.history(
            session,
            context=context,
            employee_id=values["employee_id"],  # type: ignore[arg-type]
            pay_period_id=second.pay_period_id,
        )
        assert tuple(item.id for item in history) == (first.id, second.id)
        fork = candidate(
            values,
            602,
            pay_period_id=pay_period_id,
            supersedes_result_id=first_candidate.result_id,
        )
        session.add(
            PayrollTimeInputRecord(
                id=uuid4(),
                snapshot_identity=fork.time_snapshot_id,
                snapshot_version="payroll.time-input.v1",
                company_id=fork.company_id,
                employee_id=fork.employee_id,
                pay_period_id=fork.pay_period.pay_period_id,
                approved_revision_ids=[],
                total_approved_minutes=fork.components[0].payable_minutes,
                snapshot_digest=fork.time_snapshot_digest,
                created_by_user_id=values["actor_id"],
            )
        )
        await session.commit()
        with pytest.raises(PayrollConflictError, match="lineage"):
            await service.persist_candidate(session, context=context, candidate=fork)


@pytest.mark.asyncio
async def test_permissions_company_isolation_and_blocked_period_status(
    finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]],
) -> None:
    factory, values = finalization_database
    service = PayrollGrossResultService()
    no_permission: Any = FakeContext(
        values["company_id"], values["actor_id"], set()  # type: ignore[arg-type]
    )
    other_company: Any = FakeContext(
        values["other_company_id"],  # type: ignore[arg-type]
        values["actor_id"],  # type: ignore[arg-type]
        {PayrollPermission.CALCULATION_EXECUTE, PayrollPermission.CALCULATION_READ},
    )
    read: Any = FakeContext(
        values["company_id"],  # type: ignore[arg-type]
        values["actor_id"],  # type: ignore[arg-type]
        {PayrollPermission.CALCULATION_EXECUTE, PayrollPermission.CALCULATION_READ},
    )
    value = candidate(values)
    async with factory() as session:
        await seed_candidate_time(session, value, values["actor_id"])  # type: ignore[arg-type]
        with pytest.raises(PayrollAuthorizationError):
            await service.persist_candidate(
                session, context=no_permission, candidate=value
            )
        with pytest.raises(PayrollConflictError, match="Company"):
            await service.persist_candidate(
                session, context=other_company, candidate=value
            )
        persisted = await service.persist_candidate(
            session, context=read, candidate=value
        )
        blocked_employee = uuid4()
        statuses = await service.period_results(
            session,
            context=read,
            pay_period_id=persisted.pay_period_id,
            blocked=(
                PayPeriodCalculationStatus(
                    blocked_employee,
                    None,
                    None,
                    "blocked_compensation",
                    None,
                ),
            ),
        )
        assert {item.employee_id for item in statuses} == {
            values["employee_id"],
            blocked_employee,
        }
        assert any(item.status == "blocked_compensation" for item in statuses)
        assert (
            await session.scalar(
                select(func.count(PayrollGrossCalculationResultRecord.id)).where(
                    PayrollGrossCalculationResultRecord.company_id
                    == values["company_id"]
                )
            )
        ) == 1
        assert (
            await session.scalar(
                select(func.count(PayrollGrossCalculationReviewRecord.id)).where(
                    PayrollGrossCalculationReviewRecord.company_id
                    == values["company_id"]
                )
            )
        ) == 0


@pytest.mark.asyncio
async def test_concurrent_exact_replay_creates_one_authoritative_result(
    finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]],
) -> None:
    factory, values = finalization_database
    context: Any = FakeContext(
        values["company_id"],  # type: ignore[arg-type]
        values["actor_id"],  # type: ignore[arg-type]
        {PayrollPermission.CALCULATION_EXECUTE},
    )
    value = candidate(values)

    async with factory() as session:
        await seed_candidate_time(session, value, values["actor_id"])  # type: ignore[arg-type]

    async def persist() -> UUID:
        async with factory() as session:
            result = await PayrollGrossResultService().persist_candidate(
                session, context=context, candidate=value
            )
            return result.id

    first, second = await asyncio.gather(persist(), persist())
    assert first == second
    async with factory() as session:
        count = await session.scalar(
            select(func.count(PayrollGrossCalculationResultRecord.id)).where(
                PayrollGrossCalculationResultRecord.company_id == values["company_id"]
            )
        )
        assert count == 1
