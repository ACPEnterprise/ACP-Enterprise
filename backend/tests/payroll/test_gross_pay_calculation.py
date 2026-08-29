from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from app.payroll.calculation import (
    ApprovedAdditionalEarning,
    EarningsComponentType,
    GrossPayCalculationError,
    PayPeriodCalculationContext,
    PayrollGrossCalculationEngine,
)
from app.payroll.company_policy_configurations.all_county_v1_1 import (
    build_all_county_payroll_policy_v1_1,
)
from app.payroll.contracts import (
    ApprovedCompensationAuthority,
    CompensationType,
    PayrollAdmissionState,
    PayrollAuthorizationError,
    canonical_digest,
    evaluate_payroll_admission,
)
from app.payroll.permissions import PayrollPermission
from app.timekeeping.contracts import (
    ApprovedWorkdayTimeFact,
    TimeEntryProvenance,
    seal_payroll_time_input,
)
from app.timekeeping.contracts import (
    canonical_digest as time_digest,
)

NOW = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)
PERIOD_START = date(2026, 8, 29)
PERIOD_END = date(2026, 9, 4)


def policy(company_id: UUID):  # type: ignore[no-untyped-def]
    return build_all_county_payroll_policy_v1_1(
        company_id=company_id,
        approver_user_id=uuid4(),
        approved_at=NOW,
    ).policy


def compensation(
    company_id: UUID,
    employee_id: UUID,
    *,
    kind: CompensationType = CompensationType.HOURLY,
    rate: Decimal = Decimal("24.00"),
    worker_class: str = "hourly_labor",
    effective_start: date = PERIOD_START,
    effective_end: date | None = None,
) -> ApprovedCompensationAuthority:
    value = ApprovedCompensationAuthority(
        authority_id=uuid4(),
        company_id=company_id,
        employee_id=employee_id,
        authority_version=1,
        effective_start=effective_start,
        effective_end=effective_end,
        compensation_type=kind,
        hourly_rate=rate if kind is CompensationType.HOURLY else None,
        salary_amount=rate if kind is CompensationType.SALARIED else None,
        salary_frequency="weekly" if kind is CompensationType.SALARIED else None,
        worker_class_reference=worker_class,
        additional_earning_types=(),
        recurring_components=(),
        approved_by_user_id=uuid4(),
        approved_at=NOW,
        decision_evidence_digest=canonical_digest({"synthetic": str(uuid4())}),
        authority_digest="",
    )
    return replace(value, authority_digest=canonical_digest(value.canonical_content()))


def time_input(company_id: UUID, employee_id: UUID, minutes: int):  # type: ignore[no-untyped-def]
    entry = ApprovedWorkdayTimeFact(
        entry_id=uuid4(),
        revision_id=uuid4(),
        revision_number=1,
        company_id=company_id,
        branch_id=uuid4(),
        employee_id=employee_id,
        work_date=PERIOD_START,
        timezone="America/New_York",
        provenance=TimeEntryProvenance.EMPLOYEE_PUNCH,
        start_at=None,
        end_at=None,
        approved_duration_minutes=minutes,
        punch_event_ids=(uuid4(), uuid4()),
        correction_lineage=(),
        entered_by_user_id=None,
        approval_id=uuid4(),
        approved_by_user_id=uuid4(),
        approved_at=NOW,
        evidence_digest="",
    )
    entry = replace(entry, evidence_digest=time_digest(entry.canonical_content()))
    return seal_payroll_time_input(
        company_id=company_id,
        employee_id=employee_id,
        pay_period_id=uuid4(),
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        approved_entries=(entry,),
    )


def admitted(policy_value, compensation_value, snapshot):  # type: ignore[no-untyped-def]
    return evaluate_payroll_admission(
        company_id=policy_value.company_id,
        identity_resolved=True,
        policy=policy_value,
        compensation=compensation_value,
        time_input=snapshot,
        pay_period_schedule_definition_id=(
            policy_value.definition.schedule_definition_id
        ),
        pay_period_schedule_version=policy_value.definition.schedule_version,
    )


def period(policy_value, snapshot):  # type: ignore[no-untyped-def]
    return PayPeriodCalculationContext(
        snapshot.pay_period_id,
        snapshot.period_start,
        snapshot.period_end,
        policy_value.definition.schedule_definition_id,
        policy_value.definition.schedule_version,
    )


def calculate(policy_value, compensation_value, snapshot, **overrides):  # type: ignore[no-untyped-def]
    values = {
        "actor_permissions": frozenset({PayrollPermission.CALCULATION_EXECUTE}),
        "company_id": policy_value.company_id,
        "employee_id": compensation_value.employee_id,
        "period": period(policy_value, snapshot),
        "admission": admitted(policy_value, compensation_value, snapshot),
        "policy": policy_value,
        "compensation": compensation_value,
        "time_input": snapshot,
        "currency": "USD",
        "calculated_at": NOW,
    }
    values.update(overrides)
    return PayrollGrossCalculationEngine().calculate(**values)


def test_hourly_below_threshold_and_exact_minute_money() -> None:
    company_id, employee_id = uuid4(), uuid4()
    policy_value = policy(company_id)
    authority = compensation(company_id, employee_id, rate=Decimal("24.00"))
    snapshot = time_input(company_id, employee_id, 39 * 60 + 1)
    result = calculate(policy_value, authority, snapshot)
    assert result.gross_pay_total == Decimal("936.40")
    assert tuple(item.component_type for item in result.components) == (
        EarningsComponentType.REGULAR,
    )


def test_ordinary_hourly_overtime_is_incremental_half_rate_premium() -> None:
    company_id, employee_id = uuid4(), uuid4()
    policy_value = policy(company_id)
    authority = compensation(company_id, employee_id, rate=Decimal("24.00"))
    snapshot = time_input(company_id, employee_id, 45 * 60)
    result = calculate(policy_value, authority, snapshot)
    regular, premium = result.components
    assert regular.payable_minutes == 2700
    assert regular.amount == Decimal("1080.00")
    assert premium.payable_minutes == 300
    assert premium.multiplier == Decimal("0.5")
    assert premium.amount == Decimal("60.00")
    assert result.gross_pay_total == Decimal("1140.00")


def test_hourly_supervisor_keeps_all_hours_at_straight_time() -> None:
    company_id, employee_id = uuid4(), uuid4()
    policy_value = policy(company_id)
    authority = compensation(
        company_id,
        employee_id,
        rate=Decimal("24.00"),
        worker_class="hourly_supervisor",
    )
    result = calculate(
        policy_value, authority, time_input(company_id, employee_id, 45 * 60)
    )
    assert len(result.components) == 1
    assert result.components[0].payable_minutes == 2700
    assert result.gross_pay_total == Decimal("1080.00")


def test_salary_is_period_amount_and_attendance_does_not_multiply_it() -> None:
    company_id, employee_id = uuid4(), uuid4()
    policy_value = policy(company_id)
    authority = compensation(
        company_id,
        employee_id,
        kind=CompensationType.SALARIED,
        rate=Decimal("1500.00"),
        worker_class="salaried_management",
    )
    first = calculate(
        policy_value, authority, time_input(company_id, employee_id, 10 * 60)
    )
    second = calculate(
        policy_value, authority, time_input(company_id, employee_id, 50 * 60)
    )
    assert first.gross_pay_total == second.gross_pay_total == Decimal("1500.00")
    assert first.components[0].payable_minutes is None


def test_salary_attendance_only_admission_does_not_require_time_input() -> None:
    company_id, employee_id = uuid4(), uuid4()
    policy_value = policy(company_id)
    authority = compensation(
        company_id,
        employee_id,
        kind=CompensationType.SALARIED,
        rate=Decimal("1500.00"),
        worker_class="salaried_management",
    )
    pay_period_id = uuid4()
    admission = evaluate_payroll_admission(
        company_id=company_id,
        identity_resolved=True,
        policy=policy_value,
        compensation=authority,
        time_input=None,
        pay_period_schedule_definition_id=policy_value.definition.schedule_definition_id,
        pay_period_schedule_version=policy_value.definition.schedule_version,
        pay_period_id=pay_period_id,
    )
    assert admission.state is PayrollAdmissionState.READY_FOR_CALCULATION
    result = PayrollGrossCalculationEngine().calculate(
        actor_permissions=frozenset({PayrollPermission.CALCULATION_EXECUTE}),
        company_id=company_id,
        employee_id=employee_id,
        period=PayPeriodCalculationContext(
            pay_period_id,
            PERIOD_START,
            PERIOD_END,
            policy_value.definition.schedule_definition_id,
            policy_value.definition.schedule_version,
        ),
        admission=admission,
        policy=policy_value,
        compensation=authority,
        time_input=None,
        currency="USD",
        calculated_at=NOW,
    )
    assert result.gross_pay_total == Decimal("1500.00")
    assert result.time_snapshot_id is None


def test_identical_economic_input_replays_digest_despite_timestamp() -> None:
    company_id, employee_id = uuid4(), uuid4()
    policy_value = policy(company_id)
    authority = compensation(company_id, employee_id)
    snapshot = time_input(company_id, employee_id, 1200)
    first = calculate(policy_value, authority, snapshot)
    second = calculate(
        policy_value,
        authority,
        snapshot,
        calculated_at=datetime(2026, 9, 10, 16, 0, tzinfo=timezone.utc),
    )
    assert first.result_id == second.result_id
    assert first.calculation_digest == second.calculation_digest
    assert first.calculated_at != second.calculated_at


def test_changed_time_or_compensation_changes_result() -> None:
    company_id, employee_id = uuid4(), uuid4()
    policy_value = policy(company_id)
    first_authority = compensation(company_id, employee_id, rate=Decimal(20))
    first_time = time_input(company_id, employee_id, 600)
    first = calculate(policy_value, first_authority, first_time)
    changed_time = time_input(company_id, employee_id, 601)
    changed_time_result = calculate(policy_value, first_authority, changed_time)
    changed_authority = compensation(company_id, employee_id, rate=Decimal(21))
    changed_authority_result = calculate(
        policy_value, changed_authority, first_time
    )
    assert len(
        {
            first.calculation_digest,
            changed_time_result.calculation_digest,
            changed_authority_result.calculation_digest,
        }
    ) == 3


def test_changed_policy_and_superseding_calculation_preserve_identity() -> None:
    company_id, employee_id = uuid4(), uuid4()
    first_policy = policy(company_id)
    authority = compensation(company_id, employee_id)
    snapshot = time_input(company_id, employee_id, 600)
    first = calculate(first_policy, authority, snapshot)
    changed_definition = replace(
        first_policy.definition, cutoff_rule="synthetic-changed-cutoff"
    )
    second_policy = replace(
        first_policy,
        policy_id=uuid4(),
        policy_version=first_policy.policy_version + 1,
        definition=changed_definition,
        authority_digest="",
    )
    second_policy = replace(
        second_policy,
        authority_digest=canonical_digest(second_policy.canonical_content()),
    )
    second = calculate(second_policy, authority, snapshot)
    superseding = calculate(
        second_policy,
        authority,
        snapshot,
        supersedes_result_id=first.result_id,
    )
    assert first.calculation_digest != second.calculation_digest
    assert second.calculation_digest != superseding.calculation_digest
    assert first.supersedes_result_id is None
    first.verify()


def test_result_tampering_fails_integrity_verification() -> None:
    company_id, employee_id = uuid4(), uuid4()
    policy_value = policy(company_id)
    authority = compensation(company_id, employee_id)
    snapshot = time_input(company_id, employee_id, 600)
    result = calculate(policy_value, authority, snapshot)
    with pytest.raises(GrossPayCalculationError, match="digest mismatch"):
        replace(result, gross_pay_total=result.gross_pay_total + Decimal(1)).verify()


def test_only_explicitly_authorized_additional_earnings_are_included() -> None:
    company_id, employee_id = uuid4(), uuid4()
    policy_value = policy(company_id)
    authority = compensation(company_id, employee_id)
    authority = replace(
        authority,
        additional_earning_types=("synthetic_bonus",),
        authority_digest="",
    )
    authority = replace(
        authority, authority_digest=canonical_digest(authority.canonical_content())
    )
    snapshot = time_input(company_id, employee_id, 600)
    earning = ApprovedAdditionalEarning(
        "synthetic-earning-1",
        "synthetic_bonus",
        Decimal("10.00"),
        "USD",
        canonical_digest({"synthetic": "earning-evidence"}),
    )
    result = calculate(
        policy_value, authority, snapshot, additional_earnings=(earning,)
    )
    assert result.components[-1].component_type is EarningsComponentType.ADDITIONAL
    assert result.gross_pay_total == Decimal("250.00")
    with pytest.raises(GrossPayCalculationError, match="not authorized"):
        calculate(
            policy_value,
            authority,
            snapshot,
            additional_earnings=(replace(earning, category="commission"),),
        )


@pytest.mark.parametrize(
    ("missing", "expected_state"),
    [
        ("identity", PayrollAdmissionState.BLOCKED_IDENTITY),
        ("policy", PayrollAdmissionState.BLOCKED_POLICY),
        ("compensation", PayrollAdmissionState.BLOCKED_COMPENSATION),
        ("time", PayrollAdmissionState.BLOCKED_TIME),
    ],
)
def test_existing_admission_blockers_cannot_bypass_calculation(
    missing: str, expected_state: PayrollAdmissionState
) -> None:
    company_id, employee_id = uuid4(), uuid4()
    policy_value = policy(company_id)
    authority = compensation(company_id, employee_id)
    snapshot = time_input(company_id, employee_id, 600)
    admission = evaluate_payroll_admission(
        company_id=company_id,
        identity_resolved=missing != "identity",
        policy=None if missing == "policy" else policy_value,
        compensation=None if missing == "compensation" else authority,
        time_input=None if missing == "time" else snapshot,
        pay_period_schedule_definition_id=policy_value.definition.schedule_definition_id,
        pay_period_schedule_version=policy_value.definition.schedule_version,
    )
    assert admission.state is expected_state
    with pytest.raises(GrossPayCalculationError, match="admission is not ready"):
        calculate(policy_value, authority, snapshot, admission=admission)


def test_unapproved_time_and_conflicting_authority_remain_blocked() -> None:
    company_id, employee_id = uuid4(), uuid4()
    policy_value = policy(company_id)
    authority = compensation(company_id, employee_id)
    snapshot = time_input(company_id, employee_id, 600)
    unapproved = evaluate_payroll_admission(
        company_id=company_id,
        identity_resolved=True,
        policy=policy_value,
        compensation=authority,
        time_input=None,
        pay_period_schedule_definition_id=policy_value.definition.schedule_definition_id,
        pay_period_schedule_version=policy_value.definition.schedule_version,
    )
    conflicting = evaluate_payroll_admission(
        company_id=company_id,
        identity_resolved=True,
        policy=policy_value,
        compensation=authority,
        time_input=snapshot,
        pay_period_schedule_definition_id=policy_value.definition.schedule_definition_id,
        pay_period_schedule_version=policy_value.definition.schedule_version,
        resolution_conflict=True,
    )
    assert unapproved.state is PayrollAdmissionState.BLOCKED_TIME
    assert conflicting.state is PayrollAdmissionState.CONFLICTING
    for admission in (unapproved, conflicting):
        with pytest.raises(GrossPayCalculationError):
            calculate(policy_value, authority, snapshot, admission=admission)


def test_cross_company_cross_currency_and_missing_permission_fail_closed() -> None:
    company_id, employee_id = uuid4(), uuid4()
    policy_value = policy(company_id)
    authority = compensation(company_id, employee_id)
    snapshot = time_input(company_id, employee_id, 600)
    with pytest.raises(GrossPayCalculationError, match="scope mismatch"):
        calculate(policy_value, authority, snapshot, company_id=uuid4())
    with pytest.raises(GrossPayCalculationError, match="cross-currency"):
        calculate(policy_value, authority, snapshot, currency="EUR")
    with pytest.raises(PayrollAuthorizationError):
        calculate(policy_value, authority, snapshot, actor_permissions=frozenset())


def test_mid_period_changes_and_salary_frequency_conversion_fail_closed() -> None:
    company_id, employee_id = uuid4(), uuid4()
    policy_value = policy(company_id)
    snapshot = time_input(company_id, employee_id, 600)
    partial = compensation(
        company_id, employee_id, effective_start=date(2026, 9, 1)
    )
    ready_for_partial = admitted(policy_value, partial, snapshot)
    with pytest.raises(GrossPayCalculationError, match="proration policy"):
        calculate(
            policy_value, partial, snapshot, admission=ready_for_partial
        )
    salary = compensation(
        company_id,
        employee_id,
        kind=CompensationType.SALARIED,
        rate=Decimal(78000),
    )
    salary = replace(
        salary,
        salary_frequency="annual",
        authority_digest="",
    )
    salary = replace(
        salary, authority_digest=canonical_digest(salary.canonical_content())
    )
    with pytest.raises(GrossPayCalculationError, match="proration policy"):
        calculate(policy_value, salary, snapshot)


def test_result_is_sensitive_domain_output_not_timecard_or_event_payload() -> None:
    company_id, employee_id = uuid4(), uuid4()
    policy_value = policy(company_id)
    authority = compensation(company_id, employee_id)
    snapshot = time_input(company_id, employee_id, 600)
    result = calculate(policy_value, authority, snapshot)
    assert "gross_pay_total" not in snapshot.canonical_content()
    assert "hourly_rate" not in snapshot.canonical_content()
    safe_reference = {
        "result_id": result.result_id,
        "calculation_digest": result.calculation_digest,
        "status": "calculated_not_finalized",
    }
    assert "gross_pay_total" not in safe_reference
    assert "compensation" not in safe_reference
