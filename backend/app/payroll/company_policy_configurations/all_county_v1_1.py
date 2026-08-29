"""All County Payroll Policy v1.1 overtime correction activation candidate."""

from dataclasses import dataclass, replace
from datetime import date, datetime
from uuid import UUID, uuid5

from ..contracts import (
    ApprovedPayrollPolicy,
    OvertimeExceptionScope,
    OvertimePremiumTreatment,
    ScopedOvertimeException,
    canonical_digest,
)
from .all_county_v1 import (
    CONFIGURATION_ID as PREDECESSOR_CONFIGURATION_ID,
)
from .all_county_v1 import (
    AllCountyPayrollPolicyV1Bundle,
    build_all_county_payroll_policy_v1,
)

CONFIGURATION_ID = "all-county.payroll-policy.v1.1"
POLICY_VERSION = 2
EFFECTIVE_START = date(2026, 8, 29)
HOURLY_SUPERVISOR = "hourly_supervisor"


@dataclass(frozen=True)
class AllCountyPayrollPolicyV11Bundle:
    configuration_id: str
    supersedes_configuration_id: str
    supersedes_policy_id: UUID
    policy: ApprovedPayrollPolicy
    base: AllCountyPayrollPolicyV1Bundle


def build_all_county_payroll_policy_v1_1(
    *, company_id: UUID, approver_user_id: UUID, approved_at: datetime
) -> AllCountyPayrollPolicyV11Bundle:
    """Seal the correction without activating policy or compensation."""
    base = build_all_county_payroll_policy_v1(
        company_id=company_id,
        approver_user_id=approver_user_id,
        approved_at=approved_at,
    )
    correction_evidence_digest = canonical_digest(
        {
            "configuration_id": CONFIGURATION_ID,
            "scope": "worker_class",
            "worker_class_reference": HOURLY_SUPERVISOR,
            "compensation_type": "hourly",
            "treatment": "straight_time_all_approved_hours",
            "weekly_premium_threshold": None,
            "daily_overtime": "not_used",
            "premium_multiplier": None,
            "legal_exemption_asserted": False,
            "effective_start": EFFECTIVE_START.isoformat(),
            "decision_source": "alex-donahue-overtime-owner-correction",
        }
    )
    exception = ScopedOvertimeException(
        exception_id="all-county.hourly-supervisor.straight-time.v1",
        scope=OvertimeExceptionScope.WORKER_CLASS,
        employee_id=None,
        worker_class_reference=HOURLY_SUPERVISOR,
        treatment=OvertimePremiumTreatment.STRAIGHT_TIME_ALL_APPROVED_HOURS,
        effective_start=EFFECTIVE_START,
        effective_end=None,
        decision_evidence_digest=correction_evidence_digest,
        legal_compliance_review_required=True,
    )
    assert base.policy.definition.overtime is not None
    overtime = replace(
        base.policy.definition.overtime,
        scoped_exceptions=(exception,),
    )
    definition = replace(base.policy.definition, overtime=overtime)
    policy = ApprovedPayrollPolicy(
        policy_id=uuid5(company_id, f"{CONFIGURATION_ID}:policy:v{POLICY_VERSION}"),
        company_id=company_id,
        policy_version=POLICY_VERSION,
        effective_start=EFFECTIVE_START,
        effective_end=None,
        definition=definition,
        approved_by_user_id=approver_user_id,
        approved_at=approved_at,
        decision_evidence_digest=correction_evidence_digest,
        authority_digest="",
    )
    policy = replace(
        policy,
        authority_digest=canonical_digest(policy.canonical_content()),
    )
    policy.verify()
    corrected_readiness = tuple(
        replace(
            item,
            pay_type_state="hourly",
            worker_classification_state=HOURLY_SUPERVISOR,
        )
        if item.intended_name == "Alex Donahue"
        else item
        for item in base.employee_readiness
    )
    corrected_base = replace(base, employee_readiness=corrected_readiness)
    return AllCountyPayrollPolicyV11Bundle(
        CONFIGURATION_ID,
        PREDECESSOR_CONFIGURATION_ID,
        base.policy.policy_id,
        policy,
        corrected_base,
    )
