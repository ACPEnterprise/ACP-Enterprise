"""Owner-approved All County Payroll Policy v1 activation candidate.

The factory requires authoritative Company and approver identities. Importing
this module never activates policy, resolves an Employee, or creates
compensation authority.
"""

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from typing import Final
from uuid import UUID, uuid5

from ..contracts import (
    PAYROLL_POLICY_DEFINITION_VERSION,
    ApprovedPayrollPolicy,
    CompanyPayrollPolicyDefinition,
    OvertimePolicy,
    PayrollAdmissionResult,
    SalariedTimeRequirement,
    canonical_digest,
    evaluate_payroll_admission,
)

CONFIGURATION_ID: Final = "all-county.payroll-policy.v1"
COMPANY_REFERENCE: Final = "all-county-plumbing-and-leak"
POLICY_VERSION: Final = 1
EFFECTIVE_START: Final = date(2026, 8, 29)

INTENDED_EMPLOYEES: Final = (
    "Michael Fouse",
    "Lianne Hernandez",
    "Alex Donahue",
    "Melvin Santiago",
    "Adam Mari",
    "Dareis Montgomery",
    "Dakota Wilcox",
    "Jason Calci",
)


@dataclass(frozen=True)
class FirstPayPeriodEvidence:
    period_start: date
    period_end: date
    processing_date: date
    payday: date
    timezone: str
    schedule_definition_id: str
    schedule_version: int


@dataclass(frozen=True)
class EmployeePayrollReadiness:
    intended_name: str
    employee_identity_state: str
    user_membership_state: str
    phone_login_intended: bool
    pay_type_state: str
    effective_date_state: str
    additional_earning_categories_state: str
    worker_classification_state: str
    compensation_approver_role: str
    admission_blocker: str


@dataclass(frozen=True)
class DeferredLeaveCategory:
    category: str
    disposition: str
    entitlement_evidence_required: bool
    counts_toward_overtime_threshold: bool


@dataclass(frozen=True)
class AllCountyPayrollPolicyV1Bundle:
    configuration_id: str
    company_reference: str
    company_id: UUID
    approver_user_id: UUID
    approved_at: datetime
    effective_start: date
    decision_digest: str
    policy: ApprovedPayrollPolicy
    first_period: FirstPayPeriodEvidence
    deferred_leave: tuple[DeferredLeaveCategory, ...]
    employee_readiness: tuple[EmployeePayrollReadiness, ...]

    def admission_without_employee_authority(self) -> PayrollAdmissionResult:
        """Prove unresolved identity remains the first fail-closed gate."""
        return evaluate_payroll_admission(
            company_id=self.company_id,
            identity_resolved=False,
            policy=self.policy,
            compensation=None,
            time_input=None,
            pay_period_schedule_definition_id=self.first_period.schedule_definition_id,
            pay_period_schedule_version=self.first_period.schedule_version,
        )


def build_all_county_payroll_policy_v1(
    *, company_id: UUID, approver_user_id: UUID, approved_at: datetime
) -> AllCountyPayrollPolicyV1Bundle:
    """Seal approved policy intent for supplied authoritative identities."""
    first_period = FirstPayPeriodEvidence(
        period_start=date(2026, 8, 29),
        period_end=date(2026, 9, 4),
        processing_date=date(2026, 9, 10),
        payday=date(2026, 9, 11),
        timezone="America/New_York",
        schedule_definition_id="all-county.weekly-saturday-friday.v1",
        schedule_version=1,
    )
    definition = CompanyPayrollPolicyDefinition(
        pay_frequency="weekly",
        schedule_definition_id=first_period.schedule_definition_id,
        schedule_version=first_period.schedule_version,
        regular_earning_categories=("approved_hours_worked",),
        overtime=OvertimePolicy(
            weekly_threshold_minutes=2400,
            daily_threshold_minutes=None,
            multiplier=Decimal("1.5"),
            double_time_threshold_minutes=None,
            double_time_multiplier=None,
            workweek_start_day=5,
            workweek_start_time="00:00",
            included_earning_categories=("approved_hours_worked",),
            excluded_earning_categories=(
                "pto",
                "vacation",
                "sick",
                "holiday",
                "other_leave",
            ),
        ),
        break_treatment=(
            "exclude_recorded_approved_unpaid_breaks;paid_breaks_not_used;"
            "automatic_deduction_prohibited"
        ),
        leave_category_refs=(),
        holiday_policy_ref=None,
        pto_policy_ref=None,
        salaried_time_requirement=SalariedTimeRequirement.NOT_REQUIRED,
        minimum_increment_minutes=None,
        rounding_rule=None,
        pre_finalization_correction_treatment=(
            "append_only_correction_reapproval_and_reseal"
        ),
        post_finalization_adjustment_treatment=(
            "append_only_retroactive_adjustment_required"
        ),
        post_payment_adjustment_treatment=(
            "append_only_post_payment_adjustment_required"
        ),
        cutoff_rule=(
            "all_time_submitted_and_manager_approved_before_calculation;"
            "blocked_employee_only;disclose_all_blocked_employees"
        ),
        required_time_approvals=1,
        compensation_authority_required=True,
    )
    definition.validate()
    decision = {
        "configuration_id": CONFIGURATION_ID,
        "company_reference": COMPANY_REFERENCE,
        "effective_start": EFFECTIVE_START.isoformat(),
        "definition": definition.canonical_content(),
        "first_period": {
            "period_start": first_period.period_start.isoformat(),
            "period_end": first_period.period_end.isoformat(),
            "processing_date": first_period.processing_date.isoformat(),
            "payday": first_period.payday.isoformat(),
            "timezone": first_period.timezone,
        },
        "manual_time": "accepted_only_with_authorized_manual_entry_provenance_and_approval",
        "appointment_and_job_duration": "not_payroll_authority",
        "double_time": "not_used",
        "leave": "deferred_without_entitlement_or_approval_evidence",
        "salaried_timecard": "attendance_only_unless_later_policy_requires_admission",
        "blocked_employee_scope": "employee_only",
        "decision_source": "all-county-payroll-policy-v1-owner-response",
    }
    decision_digest = canonical_digest(decision)
    policy_id = uuid5(company_id, f"{CONFIGURATION_ID}:policy:v{POLICY_VERSION}")
    policy = ApprovedPayrollPolicy(
        policy_id=policy_id,
        company_id=company_id,
        policy_version=POLICY_VERSION,
        effective_start=EFFECTIVE_START,
        effective_end=None,
        definition=definition,
        approved_by_user_id=approver_user_id,
        approved_at=approved_at,
        decision_evidence_digest=decision_digest,
        authority_digest="",
    )
    policy = replace(
        policy, authority_digest=canonical_digest(policy.canonical_content())
    )
    policy.verify()
    deferred_leave = tuple(
        DeferredLeaveCategory(category, "deferred", True, False)
        for category in ("pto", "vacation", "sick", "holiday", "other_leave")
    )
    employee_readiness = tuple(
        EmployeePayrollReadiness(
            intended_name=name,
            employee_identity_state="owner_runtime_resolution_required",
            user_membership_state="owner_runtime_resolution_required",
            phone_login_intended=True,
            pay_type_state="unresolved",
            effective_date_state="unresolved",
            additional_earning_categories_state="unresolved",
            worker_classification_state="unresolved",
            compensation_approver_role="owner_or_authorized_finance_approver",
            admission_blocker="blocked_identity",
        )
        for name in INTENDED_EMPLOYEES
    )
    return AllCountyPayrollPolicyV1Bundle(
        CONFIGURATION_ID,
        COMPANY_REFERENCE,
        company_id,
        approver_user_id,
        approved_at,
        EFFECTIVE_START,
        decision_digest,
        policy,
        first_period,
        deferred_leave,
        employee_readiness,
    )


assert PAYROLL_POLICY_DEFINITION_VERSION == "payroll.company-policy.v1"
