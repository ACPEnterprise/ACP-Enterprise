from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.customers.models import Customer, ServiceLocation  # noqa: F401
from app.events.models import BusinessEvent
from app.payroll.commands import DraftCompensationAuthority, DraftPayrollPolicy
from app.payroll.contracts import (
    ApprovedCompensationAuthority,
    CompanyPayrollPolicyDefinition,
    CompensationType,
    OvertimePolicy,
    PayrollAdmissionState,
    PayrollAuthorizationError,
    PayrollConflictError,
    SalariedTimeRequirement,
    canonical_digest,
    evaluate_payroll_admission,
)
from app.payroll.permissions import PayrollPermission
from app.payroll.service import PayrollAuthorityService
from app.platform.audit.models import AuditRecord
from app.platform.branch.models import Branch
from app.platform.company.models import Company
from app.platform.employees.models import Employee
from app.platform.permissions.catalog import permission_catalog
from app.platform.users.models import User
from app.scheduling.models import Appointment  # noqa: F401
from app.timekeeping.contracts import (
    ApprovedWorkdayTimeFact,
    TimeEntryProvenance,
    seal_payroll_time_input,
)
from app.timekeeping.contracts import (
    canonical_digest as time_digest,
)

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


class FakeContext:
    def __init__(self, *, company_id: UUID, user_id: UUID, permissions: set[str]):
        self.company = SimpleNamespace(id=company_id)
        self.user = SimpleNamespace(id=user_id)
        self._permissions = permissions

    def has_permission(self, value: str) -> bool:
        return value in self._permissions


@pytest_asyncio.fixture
async def payroll_database() -> AsyncIterator[
    tuple[async_sessionmaker[AsyncSession], dict[str, UUID]]
]:
    engine: AsyncEngine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ids = {
        key: uuid4()
        for key in (
            "company_a",
            "company_b",
            "branch_a",
            "branch_b",
            "drafter",
            "approver",
            "employee_a",
            "employee_salary",
        )
    }
    async with factory() as session, session.begin():
        for company_key, branch_key, code in (
            ("company_a", "branch_a", "PAYA"),
            ("company_b", "branch_b", "PAYB"),
        ):
            session.add(
                Company(
                    id=ids[company_key],
                    name=f"Synthetic {code}",
                    code=f"{code}{uuid4().hex[:6].upper()}",
                    status="active",
                    timezone="America/New_York",
                )
            )
            session.add(
                Branch(
                    id=ids[branch_key],
                    company_id=ids[company_key],
                    name=f"{code} Branch",
                    code=f"{code}{uuid4().hex[:4].upper()}",
                    status="active",
                    timezone="America/New_York",
                    is_primary=True,
                )
            )
        for key in ("drafter", "approver"):
            session.add(
                User(
                    id=ids[key],
                    normalized_email=f"{key}-{uuid4().hex}@example.test",
                    first_name=key.title(),
                    last_name="Payroll",
                    display_name=f"{key.title()} Payroll",
                    status="active",
                    authorization_version=1,
                )
            )
        await session.flush()
        for employee_key, number in (
            ("employee_a", "PAY-001"),
            ("employee_salary", "PAY-002"),
        ):
            session.add(
                Employee(
                    id=ids[employee_key],
                    company_id=ids["company_a"],
                    home_branch_id=ids["branch_a"],
                    employee_number=number,
                    first_name="Synthetic",
                    last_name=number,
                    display_name=number,
                    employee_type="employee",
                    status="active",
                )
            )
    try:
        yield factory, ids
    finally:
        await engine.dispose()


def policy_definition(*, schedule_version: int = 1) -> CompanyPayrollPolicyDefinition:
    return CompanyPayrollPolicyDefinition(
        pay_frequency="synthetic_weekly",
        schedule_definition_id="synthetic.weekly-held-back",
        schedule_version=schedule_version,
        regular_earning_categories=("synthetic_regular",),
        overtime=OvertimePolicy(
            weekly_threshold_minutes=2400,
            daily_threshold_minutes=None,
            multiplier=Decimal("1.50"),
            double_time_threshold_minutes=None,
            double_time_multiplier=None,
            workweek_start_day=5,
            workweek_start_time="00:00",
            included_earning_categories=("synthetic_regular",),
            excluded_earning_categories=(),
        ),
        break_treatment="approved_break_policy_reference_required",
        leave_category_refs=("synthetic.approved_leave",),
        holiday_policy_ref="synthetic.holiday-policy.v1",
        pto_policy_ref="synthetic.pto-policy.v1",
        salaried_time_requirement=SalariedTimeRequirement.POLICY_DEPENDENT,
        minimum_increment_minutes=None,
        rounding_rule=None,
        pre_finalization_correction_treatment="refresh_time_input_before_finalization",
        post_finalization_adjustment_treatment="new_retroactive_adjustment_required",
        post_payment_adjustment_treatment="new_post_payment_adjustment_required",
        cutoff_rule="explicit_period_finalization_required",
        required_time_approvals=1,
        compensation_authority_required=True,
    )


def approved_time_snapshot(*, company_id: UUID, employee_id: UUID, minutes: int):
    draft = ApprovedWorkdayTimeFact(
        entry_id=uuid4(),
        revision_id=uuid4(),
        revision_number=3,
        company_id=company_id,
        branch_id=None,
        employee_id=employee_id,
        work_date=date(2026, 8, 31),
        timezone="America/New_York",
        provenance=TimeEntryProvenance.AUTHORIZED_MANUAL_ENTRY,
        start_at=None,
        end_at=None,
        approved_duration_minutes=minutes,
        punch_event_ids=(),
        correction_lineage=(uuid4(),),
        entered_by_user_id=uuid4(),
        approval_id=uuid4(),
        approved_by_user_id=uuid4(),
        approved_at=NOW,
        evidence_digest="",
    )
    fact = replace(draft, evidence_digest=time_digest(draft.canonical_content()))
    return seal_payroll_time_input(
        company_id=company_id,
        employee_id=employee_id,
        pay_period_id=uuid4(),
        period_start=date(2026, 8, 29),
        period_end=date(2026, 9, 4),
        approved_entries=(fact,),
    )


@pytest.mark.asyncio
async def test_policy_lifecycle_company_isolation_overlap_and_replay(
    payroll_database: tuple[async_sessionmaker[AsyncSession], dict[str, UUID]],
) -> None:
    factory, ids = payroll_database
    service = PayrollAuthorityService()
    manage: Any = FakeContext(
        company_id=ids["company_a"],
        user_id=ids["drafter"],
        permissions={PayrollPermission.POLICY_MANAGE},
    )
    approve: Any = FakeContext(
        company_id=ids["company_a"],
        user_id=ids["approver"],
        permissions={PayrollPermission.POLICY_APPROVE},
    )
    async with factory() as session:
        draft = await service.draft_policy(
            session,
            context=manage,  # type: ignore[arg-type]
            command=DraftPayrollPolicy(
                policy_version=1,
                effective_start=date(2026, 8, 29),
                effective_end=None,
                definition=policy_definition(),
                decision_evidence_digest=canonical_digest("synthetic-policy-decision"),
                audit_reason="Synthetic policy qualification",
            ),
        )
        assert (
            await service.resolve_policy(
                session, company_id=ids["company_a"], as_of_date=date(2026, 8, 30)
            )
            is None
        )
        with pytest.raises(PayrollAuthorizationError):
            await service.approve_policy(
                session,
                context=FakeContext(
                    company_id=ids["company_a"],
                    user_id=ids["drafter"],
                    permissions={PayrollPermission.POLICY_APPROVE},
                ),  # type: ignore[arg-type]
                policy_id=draft.id,
            )
        approved = await service.approve_policy(
            session,
            context=approve,
            policy_id=draft.id,  # type: ignore[arg-type]
        )
        first_digest = approved.authority_digest
        resolved = await service.resolve_policy(
            session, company_id=ids["company_a"], as_of_date=date(2026, 8, 30)
        )
        assert resolved is not None and resolved.authority_digest == first_digest
        assert (
            await service.resolve_policy(
                session, company_id=ids["company_b"], as_of_date=date(2026, 8, 30)
            )
            is None
        )

        overlap = await service.draft_policy(
            session,
            context=manage,  # type: ignore[arg-type]
            command=DraftPayrollPolicy(
                policy_version=2,
                effective_start=date(2026, 9, 1),
                effective_end=None,
                definition=policy_definition(),
                decision_evidence_digest=canonical_digest("overlap"),
                audit_reason="Overlap regression",
            ),
        )
        with pytest.raises(PayrollConflictError):
            await service.approve_policy(
                session,
                context=approve,
                policy_id=overlap.id,  # type: ignore[arg-type]
            )
        successor = await service.draft_policy(
            session,
            context=manage,  # type: ignore[arg-type]
            command=DraftPayrollPolicy(
                policy_version=3,
                effective_start=date(2026, 10, 1),
                effective_end=None,
                definition=policy_definition(schedule_version=2),
                decision_evidence_digest=canonical_digest("successor"),
                audit_reason="Synthetic successor",
                supersedes_policy_id=approved.id,
            ),
        )
        await service.approve_policy(
            session,
            context=approve,
            policy_id=successor.id,  # type: ignore[arg-type]
        )
        historical = await service.resolve_policy(
            session, company_id=ids["company_a"], as_of_date=date(2026, 9, 15)
        )
        current = await service.resolve_policy(
            session, company_id=ids["company_a"], as_of_date=date(2026, 10, 2)
        )
        assert historical is not None and historical.authority_digest == first_digest
        assert current is not None and current.policy_id == successor.id
        assert approved.authority_digest == first_digest


@pytest.mark.asyncio
async def test_compensation_sod_hourly_salary_admission_and_audit(
    payroll_database: tuple[async_sessionmaker[AsyncSession], dict[str, UUID]],
) -> None:
    factory, ids = payroll_database
    service = PayrollAuthorityService()
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
    async with factory() as session:
        policy_draft = await service.draft_policy(
            session,
            context=manager,  # type: ignore[arg-type]
            command=DraftPayrollPolicy(
                policy_version=10,
                effective_start=date(2026, 8, 29),
                effective_end=None,
                definition=policy_definition(),
                decision_evidence_digest=canonical_digest("admission-policy"),
                audit_reason="Synthetic admission policy",
            ),
        )
        await service.approve_policy(
            session,
            context=approver,
            policy_id=policy_draft.id,  # type: ignore[arg-type]
        )
        policy = await service.resolve_policy(
            session, company_id=ids["company_a"], as_of_date=date(2026, 9, 4)
        )
        assert policy is not None
        time_input = approved_time_snapshot(
            company_id=ids["company_a"], employee_id=ids["employee_a"], minutes=480
        )
        missing_identity = evaluate_payroll_admission(
            company_id=ids["company_a"],
            identity_resolved=False,
            policy=policy,
            compensation=None,
            time_input=time_input,
            pay_period_schedule_definition_id="synthetic.weekly-held-back",
            pay_period_schedule_version=1,
        )
        assert missing_identity.state is PayrollAdmissionState.BLOCKED_IDENTITY
        missing_compensation = evaluate_payroll_admission(
            company_id=ids["company_a"],
            identity_resolved=True,
            policy=policy,
            compensation=None,
            time_input=time_input,
            pay_period_schedule_definition_id="synthetic.weekly-held-back",
            pay_period_schedule_version=1,
        )
        assert missing_compensation.state is PayrollAdmissionState.BLOCKED_COMPENSATION
        missing_time_compensation = ApprovedCompensationAuthority(
            authority_id=uuid4(),
            company_id=ids["company_a"],
            employee_id=ids["employee_a"],
            authority_version=99,
            effective_start=date(2026, 8, 29),
            effective_end=None,
            compensation_type=CompensationType.HOURLY,
            hourly_rate=Decimal("1.00"),
            salary_amount=None,
            salary_frequency=None,
            worker_class_reference=None,
            additional_earning_types=(),
            recurring_components=(),
            approved_by_user_id=ids["approver"],
            approved_at=NOW,
            decision_evidence_digest=canonical_digest("synthetic-missing-time"),
            authority_digest="",
        )
        missing_time_compensation = replace(
            missing_time_compensation,
            authority_digest=canonical_digest(
                missing_time_compensation.canonical_content()
            ),
        )
        missing_time = evaluate_payroll_admission(
            company_id=ids["company_a"],
            identity_resolved=True,
            policy=policy,
            compensation=missing_time_compensation,
            time_input=None,
            pay_period_schedule_definition_id="synthetic.weekly-held-back",
            pay_period_schedule_version=1,
        )
        assert missing_time.state is PayrollAdmissionState.BLOCKED_TIME

        hourly_draft = await service.draft_compensation(
            session,
            context=manager,  # type: ignore[arg-type]
            command=DraftCompensationAuthority(
                employee_id=ids["employee_a"],
                authority_version=1,
                effective_start=date(2026, 8, 29),
                effective_end=None,
                compensation_type=CompensationType.HOURLY,
                hourly_rate=Decimal("31.2500"),
                salary_amount=None,
                salary_frequency=None,
                worker_class_reference="synthetic.worker-class",
                additional_earning_types=("synthetic_bonus",),
                recurring_components=(),
                decision_evidence_digest=canonical_digest("synthetic-hourly"),
                audit_reason="Synthetic hourly authority",
            ),
        )
        with pytest.raises(PayrollAuthorizationError):
            await service.approve_compensation(
                session,
                context=FakeContext(
                    company_id=ids["company_a"],
                    user_id=ids["drafter"],
                    permissions={PayrollPermission.COMPENSATION_APPROVE},
                ),  # type: ignore[arg-type]
                authority_id=hourly_draft.id,
            )
        await service.approve_compensation(
            session,
            context=approver,  # type: ignore[arg-type]
            authority_id=hourly_draft.id,
        )
        hourly = await service.resolve_compensation(
            session,
            company_id=ids["company_a"],
            employee_id=ids["employee_a"],
            as_of_date=date(2026, 9, 4),
        )
        assert (
            hourly is not None and hourly.compensation_type is CompensationType.HOURLY
        )

        salary_draft = await service.draft_compensation(
            session,
            context=manager,  # type: ignore[arg-type]
            command=DraftCompensationAuthority(
                employee_id=ids["employee_salary"],
                authority_version=1,
                effective_start=date(2026, 8, 29),
                effective_end=None,
                compensation_type=CompensationType.SALARIED,
                hourly_rate=None,
                salary_amount=Decimal("98765.43"),
                salary_frequency="synthetic_annual",
                worker_class_reference="synthetic.salaried-class",
                additional_earning_types=(),
                recurring_components=(),
                decision_evidence_digest=canonical_digest("synthetic-salary"),
                audit_reason="Synthetic salaried authority",
            ),
        )
        await service.approve_compensation(
            session,
            context=approver,  # type: ignore[arg-type]
            authority_id=salary_draft.id,
        )
        salary = await service.resolve_compensation(
            session,
            company_id=ids["company_a"],
            employee_id=ids["employee_salary"],
            as_of_date=date(2026, 9, 4),
        )
        assert (
            salary is not None and salary.compensation_type is CompensationType.SALARIED
        )
        assert salary.hourly_rate is None

        ready = await service.evaluate_admission(
            session,
            context=approver,  # type: ignore[arg-type]
            identity_resolved=True,
            policy=policy,
            compensation=hourly,
            time_input=time_input,
            pay_period_schedule_definition_id="synthetic.weekly-held-back",
            pay_period_schedule_version=1,
        )
        replay = evaluate_payroll_admission(
            company_id=ids["company_a"],
            identity_resolved=True,
            policy=policy,
            compensation=hourly,
            time_input=time_input,
            pay_period_schedule_definition_id="synthetic.weekly-held-back",
            pay_period_schedule_version=1,
        )
        assert ready.state is PayrollAdmissionState.READY_FOR_CALCULATION
        assert ready.admission_digest == replay.admission_digest
        corrected_input = approved_time_snapshot(
            company_id=ids["company_a"], employee_id=ids["employee_a"], minutes=540
        )
        corrected = evaluate_payroll_admission(
            company_id=ids["company_a"],
            identity_resolved=True,
            policy=policy,
            compensation=hourly,
            time_input=corrected_input,
            pay_period_schedule_definition_id="synthetic.weekly-held-back",
            pay_period_schedule_version=1,
        )
        assert corrected.admission_digest != ready.admission_digest
        assert corrected.time_snapshot_digest != ready.time_snapshot_digest
        audits = tuple((await session.scalars(select(AuditRecord))).all())
        events = tuple((await session.scalars(select(BusinessEvent))).all())
        assert any(item.action == "payroll.compensation.approved" for item in audits)
        assert any(item.event_type == "payroll.admission_evaluated" for item in events)
        assert all("hourly_rate" not in str(item.details) for item in audits)


def test_payroll_permissions_are_reserved_and_not_timekeeping_or_economics() -> None:
    permission_catalog.validate()
    definitions = {
        item.code: item
        for item in permission_catalog.definitions
        if item.code in PayrollPermission.ALL
    }
    assert set(definitions) == set(PayrollPermission.ALL)
    assert all(item.resource == "payroll_authority" for item in definitions.values())
    assert all(item.reserved for item in definitions.values())
    assert PayrollPermission.COMPENSATION_READ not in {
        "COMPANY_TIMEKEEPING_OWN_READ",
        "COMPANY_ECONOMICS_POLICY_READ",
    }
