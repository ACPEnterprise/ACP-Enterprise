"""Immutable contracts for Payroll policy, compensation, and admission."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from app.timekeeping.contracts import (
    PAYROLL_TIME_INPUT_VERSION,
    PayrollTimeInputSnapshot,
    WorkdayTimeError,
)

PAYROLL_POLICY_DEFINITION_VERSION = "payroll.company-policy.v1"
COMPENSATION_AUTHORITY_DEFINITION_VERSION = "payroll.compensation-authority.v1"
PAYROLL_ADMISSION_DEFINITION_VERSION = "payroll.calculation-admission.v1"


class PayrollAuthorityError(ValueError):
    pass


class PayrollAuthorizationError(PermissionError):
    pass


class PayrollConflictError(PayrollAuthorityError):
    pass


class AuthorityLifecycle(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    SUPERSEDED = "superseded"
    RETIRED = "retired"


class CompensationType(StrEnum):
    HOURLY = "hourly"
    SALARIED = "salaried"


class SalariedTimeRequirement(StrEnum):
    REQUIRED = "required"
    NOT_REQUIRED = "not_required"
    POLICY_DEPENDENT = "policy_dependent"


class CorrectionTiming(StrEnum):
    BEFORE_FINALIZATION = "before_finalization"
    AFTER_FINALIZATION = "after_finalization"
    AFTER_PAYMENT = "after_payment"


class OvertimeExceptionScope(StrEnum):
    EMPLOYEE = "employee"
    WORKER_CLASS = "worker_class"


class OvertimePremiumTreatment(StrEnum):
    COMPANY_STANDARD = "company_standard"
    STRAIGHT_TIME_ALL_APPROVED_HOURS = "straight_time_all_approved_hours"


class PayrollAdmissionState(StrEnum):
    READY_FOR_CALCULATION = "ready_for_calculation"
    BLOCKED_IDENTITY = "blocked_identity"
    BLOCKED_TIME = "blocked_time"
    BLOCKED_COMPENSATION = "blocked_compensation"
    BLOCKED_POLICY = "blocked_policy"
    BLOCKED_APPROVAL = "blocked_approval"
    CONFLICTING = "conflicting"


def canonical_digest(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class OvertimePolicy:
    weekly_threshold_minutes: int | None
    daily_threshold_minutes: int | None
    multiplier: Decimal | None
    double_time_threshold_minutes: int | None
    double_time_multiplier: Decimal | None
    workweek_start_day: int
    workweek_start_time: str
    included_earning_categories: tuple[str, ...]
    excluded_earning_categories: tuple[str, ...]
    scoped_exceptions: tuple[ScopedOvertimeException, ...] = ()

    def canonical_content(self) -> dict[str, object]:
        content: dict[str, object] = {
            "weekly_threshold_minutes": self.weekly_threshold_minutes,
            "daily_threshold_minutes": self.daily_threshold_minutes,
            "multiplier": str(self.multiplier) if self.multiplier is not None else None,
            "double_time_threshold_minutes": self.double_time_threshold_minutes,
            "double_time_multiplier": (
                str(self.double_time_multiplier)
                if self.double_time_multiplier is not None
                else None
            ),
            "workweek_start_day": self.workweek_start_day,
            "workweek_start_time": self.workweek_start_time,
            "included_earning_categories": self.included_earning_categories,
            "excluded_earning_categories": self.excluded_earning_categories,
        }
        if self.scoped_exceptions:
            content["scoped_exceptions"] = tuple(
                item.canonical_content() for item in self.scoped_exceptions
            )
        return content

    def validate(self) -> None:
        if self.workweek_start_day not in range(7):
            raise PayrollAuthorityError("workweek start day must be 0-6")
        for threshold in (
            self.weekly_threshold_minutes,
            self.daily_threshold_minutes,
            self.double_time_threshold_minutes,
        ):
            if threshold is not None and threshold <= 0:
                raise PayrollAuthorityError("overtime thresholds must be positive")
        for multiplier in (self.multiplier, self.double_time_multiplier):
            if multiplier is not None and multiplier <= 0:
                raise PayrollAuthorityError("overtime multipliers must be positive")
        for item in self.scoped_exceptions:
            item.validate()


@dataclass(frozen=True)
class ScopedOvertimeException:
    exception_id: str
    scope: OvertimeExceptionScope
    employee_id: UUID | None
    worker_class_reference: str | None
    treatment: OvertimePremiumTreatment
    effective_start: date
    effective_end: date | None
    decision_evidence_digest: str
    legal_compliance_review_required: bool
    definition_version: str = "payroll.overtime-exception.v1"

    def canonical_content(self) -> dict[str, object]:
        return {
            "definition_version": self.definition_version,
            "exception_id": self.exception_id,
            "scope": self.scope.value,
            "employee_id": str(self.employee_id) if self.employee_id else None,
            "worker_class_reference": self.worker_class_reference,
            "treatment": self.treatment.value,
            "effective_start": self.effective_start.isoformat(),
            "effective_end": self.effective_end.isoformat()
            if self.effective_end
            else None,
            "decision_evidence_digest": self.decision_evidence_digest,
            "legal_compliance_review_required": self.legal_compliance_review_required,
        }

    def validate(self) -> None:
        if self.definition_version != "payroll.overtime-exception.v1":
            raise PayrollAuthorityError("unsupported overtime exception version")
        if (
            self.effective_end is not None
            and self.effective_end <= self.effective_start
        ):
            raise PayrollAuthorityError("invalid overtime exception interval")
        if self.scope is OvertimeExceptionScope.EMPLOYEE:
            if self.employee_id is None or self.worker_class_reference is not None:
                raise PayrollAuthorityError("Employee exception scope is malformed")
        elif self.employee_id is not None or not self.worker_class_reference:
            raise PayrollAuthorityError("worker-class exception scope is malformed")
        if self.treatment is OvertimePremiumTreatment.COMPANY_STANDARD:
            raise PayrollAuthorityError(
                "scoped exception cannot restate Company standard"
            )


@dataclass(frozen=True)
class ResolvedOvertimeTreatment:
    source: str
    treatment: OvertimePremiumTreatment
    exception_id: str | None
    weekly_threshold_minutes: int | None
    premium_multiplier: Decimal | None
    all_approved_minutes_regular_rate_payable: bool
    legal_compliance_review_required: bool


@dataclass(frozen=True)
class OvertimeMinuteQualification:
    approved_hours_worked_minutes: int
    regular_rate_payable_minutes: int
    premium_eligible_minutes: int
    premium_multiplier: Decimal | None


def resolve_overtime_treatment(
    policy: OvertimePolicy,
    *,
    as_of: date,
    employee_id: UUID | None,
    worker_class_reference: str | None,
) -> ResolvedOvertimeTreatment:
    """Resolve an approved scope without asserting statutory eligibility."""
    policy.validate()
    applicable = tuple(
        item
        for item in policy.scoped_exceptions
        if item.effective_start <= as_of
        and (item.effective_end is None or as_of < item.effective_end)
        and (
            (
                item.scope is OvertimeExceptionScope.EMPLOYEE
                and item.employee_id == employee_id
            )
            or (
                item.scope is OvertimeExceptionScope.WORKER_CLASS
                and item.worker_class_reference == worker_class_reference
            )
        )
    )
    employee_matches = tuple(
        item for item in applicable if item.scope is OvertimeExceptionScope.EMPLOYEE
    )
    class_matches = tuple(
        item for item in applicable if item.scope is OvertimeExceptionScope.WORKER_CLASS
    )
    selected = employee_matches or class_matches
    if len(selected) > 1:
        raise PayrollConflictError("overtime exception resolution is ambiguous")
    if selected:
        exception = selected[0]
        return ResolvedOvertimeTreatment(
            source=f"scoped_exception:{exception.scope.value}",
            treatment=exception.treatment,
            exception_id=exception.exception_id,
            weekly_threshold_minutes=None,
            premium_multiplier=None,
            all_approved_minutes_regular_rate_payable=True,
            legal_compliance_review_required=exception.legal_compliance_review_required,
        )
    return ResolvedOvertimeTreatment(
        source="company_policy",
        treatment=OvertimePremiumTreatment.COMPANY_STANDARD,
        exception_id=None,
        weekly_threshold_minutes=policy.weekly_threshold_minutes,
        premium_multiplier=policy.multiplier,
        all_approved_minutes_regular_rate_payable=True,
        legal_compliance_review_required=False,
    )


def qualify_overtime_minutes(
    approved_hours_worked_minutes: int,
    treatment: ResolvedOvertimeTreatment,
) -> OvertimeMinuteQualification:
    """Qualify synthetic time only; this does not calculate monetary Payroll."""
    if approved_hours_worked_minutes < 0:
        raise PayrollAuthorityError("approved minutes cannot be negative")
    premium_minutes = 0
    if (
        treatment.treatment is OvertimePremiumTreatment.COMPANY_STANDARD
        and treatment.weekly_threshold_minutes is not None
    ):
        premium_minutes = max(
            0, approved_hours_worked_minutes - treatment.weekly_threshold_minutes
        )
    return OvertimeMinuteQualification(
        approved_hours_worked_minutes=approved_hours_worked_minutes,
        regular_rate_payable_minutes=approved_hours_worked_minutes,
        premium_eligible_minutes=premium_minutes,
        premium_multiplier=treatment.premium_multiplier,
    )


@dataclass(frozen=True)
class CompanyPayrollPolicyDefinition:
    pay_frequency: str
    schedule_definition_id: str
    schedule_version: int
    regular_earning_categories: tuple[str, ...]
    overtime: OvertimePolicy | None
    break_treatment: str
    leave_category_refs: tuple[str, ...]
    holiday_policy_ref: str | None
    pto_policy_ref: str | None
    salaried_time_requirement: SalariedTimeRequirement
    minimum_increment_minutes: int | None
    rounding_rule: str | None
    pre_finalization_correction_treatment: str
    post_finalization_adjustment_treatment: str
    post_payment_adjustment_treatment: str
    cutoff_rule: str
    required_time_approvals: int
    compensation_authority_required: bool

    def canonical_content(self) -> dict[str, object]:
        return {
            "definition_version": PAYROLL_POLICY_DEFINITION_VERSION,
            "pay_frequency": self.pay_frequency,
            "schedule_definition_id": self.schedule_definition_id,
            "schedule_version": self.schedule_version,
            "regular_earning_categories": self.regular_earning_categories,
            "overtime": self.overtime.canonical_content() if self.overtime else None,
            "break_treatment": self.break_treatment,
            "leave_category_refs": self.leave_category_refs,
            "holiday_policy_ref": self.holiday_policy_ref,
            "pto_policy_ref": self.pto_policy_ref,
            "salaried_time_requirement": self.salaried_time_requirement.value,
            "minimum_increment_minutes": self.minimum_increment_minutes,
            "rounding_rule": self.rounding_rule,
            "pre_finalization_correction_treatment": self.pre_finalization_correction_treatment,
            "post_finalization_adjustment_treatment": self.post_finalization_adjustment_treatment,
            "post_payment_adjustment_treatment": self.post_payment_adjustment_treatment,
            "cutoff_rule": self.cutoff_rule,
            "required_time_approvals": self.required_time_approvals,
            "compensation_authority_required": self.compensation_authority_required,
        }

    def validate(self) -> None:
        if not self.pay_frequency or not self.schedule_definition_id:
            raise PayrollAuthorityError(
                "pay frequency and schedule identity are required"
            )
        if self.schedule_version < 1 or self.required_time_approvals < 1:
            raise PayrollAuthorityError(
                "schedule version and approvals must be positive"
            )
        if (
            self.minimum_increment_minutes is not None
            and self.minimum_increment_minutes <= 0
        ):
            raise PayrollAuthorityError("minimum increment must be positive")
        if bool(self.minimum_increment_minutes) != bool(self.rounding_rule):
            raise PayrollAuthorityError(
                "rounding increment and rule must be configured together"
            )
        if self.overtime is not None:
            self.overtime.validate()


@dataclass(frozen=True)
class ApprovedPayrollPolicy:
    policy_id: UUID
    company_id: UUID
    policy_version: int
    effective_start: date
    effective_end: date | None
    definition: CompanyPayrollPolicyDefinition
    approved_by_user_id: UUID
    approved_at: datetime
    decision_evidence_digest: str
    authority_digest: str

    def canonical_content(self) -> dict[str, object]:
        return {
            "definition_version": PAYROLL_POLICY_DEFINITION_VERSION,
            "policy_id": str(self.policy_id),
            "company_id": str(self.company_id),
            "policy_version": self.policy_version,
            "effective_start": self.effective_start.isoformat(),
            "effective_end": self.effective_end.isoformat()
            if self.effective_end
            else None,
            "definition": self.definition.canonical_content(),
            "approved_by_user_id": str(self.approved_by_user_id),
            "approved_at": self.approved_at.isoformat(),
            "decision_evidence_digest": self.decision_evidence_digest,
        }

    def verify(self) -> None:
        self.definition.validate()
        if self.authority_digest != canonical_digest(self.canonical_content()):
            raise PayrollAuthorityError("Payroll policy authority digest mismatch")


@dataclass(frozen=True)
class ApprovedCompensationAuthority:
    authority_id: UUID
    company_id: UUID
    employee_id: UUID
    authority_version: int
    effective_start: date
    effective_end: date | None
    compensation_type: CompensationType
    hourly_rate: Decimal | None
    salary_amount: Decimal | None
    salary_frequency: str | None
    worker_class_reference: str | None
    additional_earning_types: tuple[str, ...]
    recurring_components: tuple[dict[str, object], ...]
    approved_by_user_id: UUID
    approved_at: datetime
    decision_evidence_digest: str
    authority_digest: str

    def canonical_content(self) -> dict[str, object]:
        return {
            "definition_version": COMPENSATION_AUTHORITY_DEFINITION_VERSION,
            "authority_id": str(self.authority_id),
            "company_id": str(self.company_id),
            "employee_id": str(self.employee_id),
            "authority_version": self.authority_version,
            "effective_start": self.effective_start.isoformat(),
            "effective_end": self.effective_end.isoformat()
            if self.effective_end
            else None,
            "compensation_type": self.compensation_type.value,
            "hourly_rate": str(self.hourly_rate)
            if self.hourly_rate is not None
            else None,
            "salary_amount": str(self.salary_amount)
            if self.salary_amount is not None
            else None,
            "salary_frequency": self.salary_frequency,
            "worker_class_reference": self.worker_class_reference,
            "additional_earning_types": self.additional_earning_types,
            "recurring_components": self.recurring_components,
            "approved_by_user_id": str(self.approved_by_user_id),
            "approved_at": self.approved_at.isoformat(),
            "decision_evidence_digest": self.decision_evidence_digest,
        }

    def verify(self) -> None:
        self.validate_shape()
        if self.authority_digest != canonical_digest(self.canonical_content()):
            raise PayrollAuthorityError("compensation authority digest mismatch")

    def validate_shape(self) -> None:
        if self.compensation_type is CompensationType.HOURLY:
            if self.hourly_rate is None or self.salary_amount is not None:
                raise PayrollAuthorityError(
                    "hourly authority requires only hourly rate"
                )
        elif (
            self.salary_amount is None
            or not self.salary_frequency
            or self.hourly_rate is not None
        ):
            raise PayrollAuthorityError(
                "salaried authority requires salary amount/frequency, not hourly rate"
            )


@dataclass(frozen=True)
class PayrollAdmissionResult:
    admission_id: str
    definition_version: str
    company_id: UUID
    employee_id: UUID | None
    pay_period_id: UUID | None
    state: PayrollAdmissionState
    blockers: tuple[str, ...]
    policy_id: UUID | None
    policy_digest: str | None
    compensation_authority_id: UUID | None
    compensation_digest: str | None
    time_snapshot_id: str | None
    time_snapshot_digest: str | None
    pay_period_schedule_definition_id: str | None
    pay_period_schedule_version: int | None
    admission_digest: str

    def canonical_content(self) -> dict[str, object]:
        return {
            "definition_version": self.definition_version,
            "company_id": str(self.company_id),
            "employee_id": str(self.employee_id) if self.employee_id else None,
            "pay_period_id": str(self.pay_period_id) if self.pay_period_id else None,
            "state": self.state.value,
            "blockers": self.blockers,
            "policy_id": str(self.policy_id) if self.policy_id else None,
            "policy_digest": self.policy_digest,
            "compensation_authority_id": (
                str(self.compensation_authority_id)
                if self.compensation_authority_id
                else None
            ),
            "compensation_digest": self.compensation_digest,
            "time_snapshot_id": self.time_snapshot_id,
            "time_snapshot_digest": self.time_snapshot_digest,
            "pay_period_schedule_definition_id": self.pay_period_schedule_definition_id,
            "pay_period_schedule_version": self.pay_period_schedule_version,
        }

    def verify(self) -> None:
        digest = canonical_digest(self.canonical_content())
        if self.admission_digest != digest:
            raise PayrollAuthorityError("Payroll admission digest mismatch")
        if self.admission_id != f"payroll-admission:{digest}":
            raise PayrollAuthorityError("Payroll admission identity mismatch")


def evaluate_payroll_admission(
    *,
    company_id: UUID,
    identity_resolved: bool,
    policy: ApprovedPayrollPolicy | None,
    compensation: ApprovedCompensationAuthority | None,
    time_input: PayrollTimeInputSnapshot | None,
    pay_period_schedule_definition_id: str | None = None,
    pay_period_schedule_version: int | None = None,
    resolution_conflict: bool = False,
) -> PayrollAdmissionResult:
    blockers: list[str] = []
    state = PayrollAdmissionState.READY_FOR_CALCULATION
    authority_integrity_failed = False
    try:
        if policy is not None:
            policy.verify()
        if compensation is not None:
            compensation.verify()
    except PayrollAuthorityError:
        authority_integrity_failed = True
    if authority_integrity_failed:
        state = PayrollAdmissionState.CONFLICTING
        blockers.append("payroll_authority_integrity_failed")
    elif resolution_conflict:
        state = PayrollAdmissionState.CONFLICTING
        blockers.append("payroll_authority_resolution_conflict")
    elif not identity_resolved:
        state = PayrollAdmissionState.BLOCKED_IDENTITY
        blockers.append("employee_identity_unresolved")
    elif policy is None:
        state = PayrollAdmissionState.BLOCKED_POLICY
        blockers.append("approved_effective_payroll_policy_missing")
    elif (
        pay_period_schedule_definition_id != policy.definition.schedule_definition_id
        or pay_period_schedule_version != policy.definition.schedule_version
    ):
        state = PayrollAdmissionState.BLOCKED_POLICY
        blockers.append("pay_period_schedule_policy_mismatch")
    elif compensation is None and policy.definition.compensation_authority_required:
        state = PayrollAdmissionState.BLOCKED_COMPENSATION
        blockers.append("approved_effective_compensation_authority_missing")
    elif time_input is None:
        state = PayrollAdmissionState.BLOCKED_TIME
        blockers.append("sealed_approved_time_input_missing")
    else:
        try:
            time_input.verify()
        except WorkdayTimeError:
            state = PayrollAdmissionState.BLOCKED_TIME
            blockers.append("time_input_integrity_failed")
        if state is PayrollAdmissionState.READY_FOR_CALCULATION and (
            time_input.version != PAYROLL_TIME_INPUT_VERSION
            or time_input.company_id != company_id
            or (
                compensation is not None
                and time_input.employee_id != compensation.employee_id
            )
        ):
            state = PayrollAdmissionState.CONFLICTING
            blockers.append("time_policy_compensation_scope_conflict")
        if state is PayrollAdmissionState.READY_FOR_CALCULATION and policy is not None:
            if len(time_input.approved_entries) == 0:
                state = PayrollAdmissionState.BLOCKED_TIME
                blockers.append("approved_time_evidence_empty")
            elif policy.definition.required_time_approvals > 1:
                state = PayrollAdmissionState.BLOCKED_APPROVAL
                blockers.append("additional_time_approval_evidence_required")
    content = {
        "definition_version": PAYROLL_ADMISSION_DEFINITION_VERSION,
        "company_id": str(company_id),
        "employee_id": (
            str(time_input.employee_id)
            if time_input is not None
            else str(compensation.employee_id)
            if compensation is not None
            else None
        ),
        "pay_period_id": str(time_input.pay_period_id) if time_input else None,
        "state": state.value,
        "blockers": tuple(sorted(blockers)),
        "policy_id": str(policy.policy_id) if policy else None,
        "policy_digest": policy.authority_digest if policy else None,
        "pay_period_schedule_definition_id": pay_period_schedule_definition_id,
        "pay_period_schedule_version": pay_period_schedule_version,
        "compensation_authority_id": (
            str(compensation.authority_id) if compensation else None
        ),
        "compensation_digest": compensation.authority_digest if compensation else None,
        "time_snapshot_id": time_input.snapshot_id if time_input else None,
        "time_snapshot_digest": time_input.snapshot_digest if time_input else None,
    }
    digest = canonical_digest(content)
    result = PayrollAdmissionResult(
        admission_id=f"payroll-admission:{digest}",
        definition_version=PAYROLL_ADMISSION_DEFINITION_VERSION,
        company_id=company_id,
        employee_id=(
            time_input.employee_id
            if time_input is not None
            else compensation.employee_id
            if compensation is not None
            else None
        ),
        pay_period_id=time_input.pay_period_id if time_input else None,
        state=state,
        blockers=tuple(sorted(blockers)),
        policy_id=policy.policy_id if policy else None,
        policy_digest=policy.authority_digest if policy else None,
        compensation_authority_id=(compensation.authority_id if compensation else None),
        compensation_digest=compensation.authority_digest if compensation else None,
        time_snapshot_id=time_input.snapshot_id if time_input else None,
        time_snapshot_digest=time_input.snapshot_digest if time_input else None,
        pay_period_schedule_definition_id=pay_period_schedule_definition_id,
        pay_period_schedule_version=pay_period_schedule_version,
        admission_digest=digest,
    )
    result.verify()
    return result
