from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.payroll.company_policy_configurations.all_county_v1_1 import (
    HOURLY_SUPERVISOR,
    build_all_county_payroll_policy_v1_1,
)
from app.payroll.contracts import (
    OvertimePremiumTreatment,
    qualify_overtime_minutes,
    resolve_overtime_treatment,
)
from app.payroll.service import PayrollAuthorityService


def test_hourly_supervisor_exception_is_straight_time_without_lost_hours() -> None:
    company_id = uuid4()
    bundle = build_all_county_payroll_policy_v1_1(
        company_id=company_id,
        approver_user_id=uuid4(),
        approved_at=datetime(2026, 8, 28, 18, 0, tzinfo=timezone.utc),
    )
    overtime = bundle.policy.definition.overtime
    assert overtime is not None

    treatment = resolve_overtime_treatment(
        overtime,
        as_of=date(2026, 9, 4),
        employee_id=uuid4(),
        worker_class_reference=HOURLY_SUPERVISOR,
    )
    qualified = qualify_overtime_minutes(45 * 60, treatment)

    assert treatment.source == "scoped_exception:worker_class"
    assert (
        treatment.treatment is OvertimePremiumTreatment.STRAIGHT_TIME_ALL_APPROVED_HOURS
    )
    assert treatment.weekly_threshold_minutes is None
    assert treatment.premium_multiplier is None
    assert treatment.legal_compliance_review_required
    assert qualified.regular_rate_payable_minutes == 45 * 60
    assert qualified.premium_eligible_minutes == 0
    assert qualified.premium_multiplier is None


def test_ordinary_hourly_worker_retains_company_overtime_rule() -> None:
    bundle = build_all_county_payroll_policy_v1_1(
        company_id=uuid4(),
        approver_user_id=uuid4(),
        approved_at=datetime(2026, 8, 28, 18, 0, tzinfo=timezone.utc),
    )
    overtime = bundle.policy.definition.overtime
    assert overtime is not None

    treatment = resolve_overtime_treatment(
        overtime,
        as_of=date(2026, 9, 4),
        employee_id=uuid4(),
        worker_class_reference="hourly_labor",
    )
    qualified = qualify_overtime_minutes(45 * 60, treatment)

    assert treatment.source == "company_policy"
    assert treatment.treatment is OvertimePremiumTreatment.COMPANY_STANDARD
    assert treatment.weekly_threshold_minutes == 40 * 60
    assert treatment.premium_multiplier == Decimal("1.5")
    assert qualified.regular_rate_payable_minutes == 45 * 60
    assert qualified.premium_eligible_minutes == 5 * 60
    assert qualified.premium_multiplier == Decimal("1.5")


def test_exception_is_effective_dated_versioned_and_preserves_predecessor() -> None:
    company_id = uuid4()
    bundle = build_all_county_payroll_policy_v1_1(
        company_id=company_id,
        approver_user_id=uuid4(),
        approved_at=datetime(2026, 8, 28, 18, 0, tzinfo=timezone.utc),
    )
    overtime = bundle.policy.definition.overtime
    assert overtime is not None

    before = resolve_overtime_treatment(
        overtime,
        as_of=date(2026, 8, 28),
        employee_id=uuid4(),
        worker_class_reference=HOURLY_SUPERVISOR,
    )
    alex = next(
        item
        for item in bundle.base.employee_readiness
        if item.intended_name == "Alex Donahue"
    )

    assert before.treatment is OvertimePremiumTreatment.COMPANY_STANDARD
    assert bundle.policy.policy_version == 2
    assert bundle.policy.policy_id != bundle.supersedes_policy_id
    assert bundle.policy.authority_digest != bundle.base.policy.authority_digest
    assert alex.pay_type_state == "hourly"
    assert alex.worker_classification_state == HOURLY_SUPERVISOR
    assert alex.employee_identity_state == "owner_runtime_resolution_required"
    restored = PayrollAuthorityService._definition(
        bundle.policy.definition.canonical_content()
    )
    assert restored == bundle.policy.definition
    bundle.base.policy.verify()
    bundle.policy.verify()
