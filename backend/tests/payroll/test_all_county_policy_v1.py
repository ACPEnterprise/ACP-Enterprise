from datetime import datetime, timezone
from uuid import uuid4

from app.payroll.company_policy_configurations.all_county_v1 import (
    CONFIGURATION_ID,
    INTENDED_EMPLOYEES,
    build_all_county_payroll_policy_v1,
)
from app.payroll.contracts import (
    PayrollAdmissionState,
    SalariedTimeRequirement,
    evaluate_payroll_admission,
)


def test_all_county_policy_v1_is_deterministic_and_company_scoped() -> None:
    company_id = uuid4()
    approver_id = uuid4()
    approved_at = datetime(2026, 8, 28, 16, 0, tzinfo=timezone.utc)
    first = build_all_county_payroll_policy_v1(
        company_id=company_id,
        approver_user_id=approver_id,
        approved_at=approved_at,
    )
    replay = build_all_county_payroll_policy_v1(
        company_id=company_id,
        approver_user_id=approver_id,
        approved_at=approved_at,
    )
    other = build_all_county_payroll_policy_v1(
        company_id=uuid4(),
        approver_user_id=approver_id,
        approved_at=approved_at,
    )

    assert first == replay
    assert first.configuration_id == CONFIGURATION_ID
    assert first.policy.authority_digest == replay.policy.authority_digest
    assert first.policy.policy_id != other.policy.policy_id
    assert first.policy.authority_digest != other.policy.authority_digest
    first.policy.verify()


def test_owner_decisions_encode_without_employee_compensation_or_inference() -> None:
    bundle = build_all_county_payroll_policy_v1(
        company_id=uuid4(),
        approver_user_id=uuid4(),
        approved_at=datetime(2026, 8, 28, 16, 0, tzinfo=timezone.utc),
    )
    definition = bundle.policy.definition
    overtime = definition.overtime

    assert definition.pay_frequency == "weekly"
    assert definition.regular_earning_categories == ("approved_hours_worked",)
    assert overtime is not None
    assert overtime.weekly_threshold_minutes == 2400
    assert overtime.daily_threshold_minutes is None
    assert overtime.double_time_threshold_minutes is None
    assert overtime.workweek_start_day == 5
    assert overtime.workweek_start_time == "00:00"
    assert "pto" in overtime.excluded_earning_categories
    assert "automatic_deduction_prohibited" in definition.break_treatment
    assert definition.minimum_increment_minutes is None
    assert definition.rounding_rule is None
    assert definition.leave_category_refs == ()
    assert definition.salaried_time_requirement is SalariedTimeRequirement.NOT_REQUIRED
    assert definition.compensation_authority_required
    assert bundle.first_period.period_start.isoformat() == "2026-08-29"
    assert bundle.first_period.period_end.isoformat() == "2026-09-04"
    assert bundle.first_period.processing_date.isoformat() == "2026-09-10"
    assert bundle.first_period.payday.isoformat() == "2026-09-11"
    assert bundle.first_period.timezone == "America/New_York"

    assert tuple(item.intended_name for item in bundle.employee_readiness) == (
        INTENDED_EMPLOYEES
    )
    assert all(item.phone_login_intended for item in bundle.employee_readiness)
    assert all(
        item.pay_type_state == "unresolved" for item in bundle.employee_readiness
    )
    assert all(
        item.employee_identity_state == "owner_runtime_resolution_required"
        for item in bundle.employee_readiness
    )
    assert all(item.disposition == "deferred" for item in bundle.deferred_leave)
    assert all(
        not item.counts_toward_overtime_threshold for item in bundle.deferred_leave
    )


def test_unresolved_employee_authority_keeps_payroll_admission_closed() -> None:
    bundle = build_all_county_payroll_policy_v1(
        company_id=uuid4(),
        approver_user_id=uuid4(),
        approved_at=datetime(2026, 8, 28, 16, 0, tzinfo=timezone.utc),
    )
    result = bundle.admission_without_employee_authority()

    assert result.state is PayrollAdmissionState.BLOCKED_IDENTITY
    assert result.blockers == ("employee_identity_unresolved",)
    assert result.compensation_authority_id is None
    assert result.time_snapshot_id is None
    result.verify()

    identity_only = evaluate_payroll_admission(
        company_id=bundle.company_id,
        identity_resolved=True,
        policy=bundle.policy,
        compensation=None,
        time_input=None,
        pay_period_schedule_definition_id=bundle.first_period.schedule_definition_id,
        pay_period_schedule_version=bundle.first_period.schedule_version,
    )
    assert identity_only.state is PayrollAdmissionState.BLOCKED_COMPENSATION
    assert identity_only.blockers == (
        "approved_effective_compensation_authority_missing",
    )
