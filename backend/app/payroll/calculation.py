"""Deterministic gross-pay calculation over admitted Payroll evidence.

This module creates immutable calculation candidates. It does not finalize Payroll,
calculate tax or deductions, pay an Employee, or post Accounting entries.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from enum import StrEnum
from uuid import UUID

from app.timekeeping.contracts import PayrollTimeInputSnapshot

from .contracts import (
    ApprovedCompensationAuthority,
    ApprovedPayrollPolicy,
    CompensationType,
    PayrollAdmissionResult,
    PayrollAdmissionState,
    PayrollAuthorityError,
    PayrollAuthorizationError,
    canonical_digest,
    qualify_overtime_minutes,
    resolve_overtime_treatment,
)
from .permissions import PayrollPermission

GROSS_PAY_CALCULATION_VERSION = "payroll.gross-pay-calculation.v1"
MONEY_ROUNDING_VERSION = "money.currency-minor-unit-half-even.v1"


class GrossPayCalculationError(PayrollAuthorityError):
    pass


class EarningsComponentType(StrEnum):
    REGULAR = "regular"
    OVERTIME_PREMIUM = "overtime_premium"
    SALARY = "salary"
    ADDITIONAL = "additional"


@dataclass(frozen=True)
class PayPeriodCalculationContext:
    pay_period_id: UUID
    period_start: date
    period_end: date
    schedule_definition_id: str
    schedule_version: int

    def canonical_content(self) -> dict[str, object]:
        return {
            "pay_period_id": str(self.pay_period_id),
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "schedule_definition_id": self.schedule_definition_id,
            "schedule_version": self.schedule_version,
        }


@dataclass(frozen=True)
class ApprovedAdditionalEarning:
    earning_id: str
    category: str
    amount: Decimal
    currency: str
    evidence_digest: str

    def canonical_content(self) -> dict[str, object]:
        return {
            "earning_id": self.earning_id,
            "category": self.category,
            "amount": str(self.amount),
            "currency": self.currency,
            "evidence_digest": self.evidence_digest,
        }


@dataclass(frozen=True)
class GrossPayEarningComponent:
    component_type: EarningsComponentType
    category: str
    payable_minutes: int | None
    rate: Decimal | None
    multiplier: Decimal | None
    amount: Decimal
    currency: str
    evidence_digests: tuple[str, ...]

    def canonical_content(self) -> dict[str, object]:
        return {
            "component_type": self.component_type.value,
            "category": self.category,
            "payable_minutes": self.payable_minutes,
            "rate": str(self.rate) if self.rate is not None else None,
            "multiplier": str(self.multiplier)
            if self.multiplier is not None
            else None,
            "amount": str(self.amount),
            "currency": self.currency,
            "evidence_digests": self.evidence_digests,
        }


@dataclass(frozen=True)
class GrossPayCalculationResult:
    result_id: str
    definition_version: str
    company_id: UUID
    employee_id: UUID
    pay_period: PayPeriodCalculationContext
    currency: str
    admission_id: str
    admission_digest: str
    policy_id: UUID
    policy_digest: str
    compensation_authority_id: UUID
    compensation_digest: str
    time_snapshot_id: str | None
    time_snapshot_digest: str | None
    components: tuple[GrossPayEarningComponent, ...]
    gross_pay_total: Decimal
    money_rounding_version: str
    calculation_digest: str
    calculated_at: datetime
    supersedes_result_id: str | None = None

    def canonical_economic_content(self) -> dict[str, object]:
        return {
            "definition_version": self.definition_version,
            "company_id": str(self.company_id),
            "employee_id": str(self.employee_id),
            "pay_period": self.pay_period.canonical_content(),
            "currency": self.currency,
            "admission_id": self.admission_id,
            "admission_digest": self.admission_digest,
            "policy_id": str(self.policy_id),
            "policy_digest": self.policy_digest,
            "compensation_authority_id": str(self.compensation_authority_id),
            "compensation_digest": self.compensation_digest,
            "time_snapshot_id": self.time_snapshot_id,
            "time_snapshot_digest": self.time_snapshot_digest,
            "components": tuple(item.canonical_content() for item in self.components),
            "gross_pay_total": str(self.gross_pay_total),
            "money_rounding_version": self.money_rounding_version,
            "supersedes_result_id": self.supersedes_result_id,
        }

    def verify(self) -> None:
        digest = canonical_digest(self.canonical_economic_content())
        if digest != self.calculation_digest:
            raise GrossPayCalculationError("gross-pay calculation digest mismatch")
        if self.result_id != f"gross-pay-calculation:{digest}":
            raise GrossPayCalculationError("gross-pay calculation identity mismatch")
        if self.gross_pay_total != sum(
            (item.amount for item in self.components), start=Decimal(0)
        ):
            raise GrossPayCalculationError("gross-pay component total mismatch")
        if any(item.currency != self.currency for item in self.components):
            raise GrossPayCalculationError("cross-currency calculation is prohibited")


def _currency_quantum(currency: str) -> Decimal:
    if currency != "USD":
        raise GrossPayCalculationError("unsupported or cross-currency calculation")
    return Decimal("0.01")


def _money(value: Decimal, currency: str) -> Decimal:
    return value.quantize(_currency_quantum(currency), rounding=ROUND_HALF_EVEN)


def _covers_period(
    effective_start: date, effective_end: date | None, period: PayPeriodCalculationContext
) -> bool:
    return effective_start <= period.period_start and (
        effective_end is None or period.period_end < effective_end
    )


def _validate_inputs(
    *,
    company_id: UUID,
    employee_id: UUID,
    period: PayPeriodCalculationContext,
    admission: PayrollAdmissionResult,
    policy: ApprovedPayrollPolicy,
    compensation: ApprovedCompensationAuthority,
    time_input: PayrollTimeInputSnapshot | None,
) -> None:
    admission.verify()
    policy.verify()
    compensation.verify()
    if admission.state is not PayrollAdmissionState.READY_FOR_CALCULATION:
        raise GrossPayCalculationError("Payroll calculation admission is not ready")
    if (
        company_id != policy.company_id
        or company_id != compensation.company_id
        or employee_id != compensation.employee_id
        or admission.company_id != company_id
        or admission.employee_id != employee_id
        or admission.pay_period_id != period.pay_period_id
        or admission.policy_id != policy.policy_id
        or admission.policy_digest != policy.authority_digest
        or admission.compensation_authority_id != compensation.authority_id
        or admission.compensation_digest != compensation.authority_digest
    ):
        raise GrossPayCalculationError("Payroll calculation authority scope mismatch")
    if (
        period.schedule_definition_id != policy.definition.schedule_definition_id
        or period.schedule_version != policy.definition.schedule_version
        or admission.pay_period_schedule_definition_id
        != period.schedule_definition_id
        or admission.pay_period_schedule_version != period.schedule_version
    ):
        raise GrossPayCalculationError("pay-period schedule authority mismatch")
    if not _covers_period(policy.effective_start, policy.effective_end, period):
        raise GrossPayCalculationError("mid-period policy change requires proration policy")
    if not _covers_period(
        compensation.effective_start, compensation.effective_end, period
    ):
        raise GrossPayCalculationError(
            "mid-period compensation change requires proration policy"
        )
    if time_input is not None:
        time_input.verify()
        if (
            time_input.company_id != company_id
            or time_input.employee_id != employee_id
            or time_input.pay_period_id != period.pay_period_id
            or time_input.period_start != period.period_start
            or time_input.period_end != period.period_end
            or admission.time_snapshot_id != time_input.snapshot_id
            or admission.time_snapshot_digest != time_input.snapshot_digest
        ):
            raise GrossPayCalculationError("Payroll Time Input scope mismatch")
    elif compensation.compensation_type is CompensationType.HOURLY:
        raise GrossPayCalculationError("hourly calculation requires approved time")


class PayrollGrossCalculationEngine:
    def calculate(
        self,
        *,
        actor_permissions: frozenset[str],
        company_id: UUID,
        employee_id: UUID,
        period: PayPeriodCalculationContext,
        admission: PayrollAdmissionResult,
        policy: ApprovedPayrollPolicy,
        compensation: ApprovedCompensationAuthority,
        time_input: PayrollTimeInputSnapshot | None,
        currency: str,
        calculated_at: datetime,
        additional_earnings: tuple[ApprovedAdditionalEarning, ...] = (),
        supersedes_result_id: str | None = None,
    ) -> GrossPayCalculationResult:
        if PayrollPermission.CALCULATION_EXECUTE not in actor_permissions:
            raise PayrollAuthorizationError("Payroll calculation authority is required")
        _validate_inputs(
            company_id=company_id,
            employee_id=employee_id,
            period=period,
            admission=admission,
            policy=policy,
            compensation=compensation,
            time_input=time_input,
        )
        if policy.definition.minimum_increment_minutes is not None:
            raise GrossPayCalculationError("configured time rounding is unsupported")
        if compensation.recurring_components:
            raise GrossPayCalculationError(
                "recurring earning calculation requires accepted earning evidence"
            )
        components: list[GrossPayEarningComponent] = []
        if compensation.compensation_type is CompensationType.HOURLY:
            assert compensation.hourly_rate is not None and time_input is not None
            overtime = policy.definition.overtime
            if overtime is None:
                raise GrossPayCalculationError("hourly overtime policy is unresolved")
            treatment = resolve_overtime_treatment(
                overtime,
                as_of=period.period_start,
                employee_id=employee_id,
                worker_class_reference=compensation.worker_class_reference,
            )
            qualified = qualify_overtime_minutes(
                time_input.total_approved_minutes, treatment
            )
            evidence = (time_input.snapshot_digest, compensation.authority_digest)
            components.append(
                GrossPayEarningComponent(
                    EarningsComponentType.REGULAR,
                    "approved_hours_worked",
                    qualified.regular_rate_payable_minutes,
                    compensation.hourly_rate,
                    Decimal(1),
                    _money(
                        compensation.hourly_rate
                        * Decimal(qualified.regular_rate_payable_minutes)
                        / Decimal(60),
                        currency,
                    ),
                    currency,
                    evidence,
                )
            )
            if qualified.premium_eligible_minutes:
                if qualified.premium_multiplier is None:
                    raise GrossPayCalculationError("premium multiplier is unresolved")
                incremental_multiplier = qualified.premium_multiplier - Decimal(1)
                if incremental_multiplier < 0:
                    raise GrossPayCalculationError("premium multiplier is invalid")
                components.append(
                    GrossPayEarningComponent(
                        EarningsComponentType.OVERTIME_PREMIUM,
                        "approved_hours_worked_overtime_premium",
                        qualified.premium_eligible_minutes,
                        compensation.hourly_rate,
                        incremental_multiplier,
                        _money(
                            compensation.hourly_rate
                            * Decimal(qualified.premium_eligible_minutes)
                            / Decimal(60)
                            * incremental_multiplier,
                            currency,
                        ),
                        currency,
                        evidence,
                    )
                )
        else:
            assert compensation.salary_amount is not None
            if compensation.salary_frequency != policy.definition.pay_frequency:
                raise GrossPayCalculationError(
                    "salary frequency conversion requires approved proration policy"
                )
            components.append(
                GrossPayEarningComponent(
                    EarningsComponentType.SALARY,
                    "salary",
                    None,
                    None,
                    None,
                    _money(compensation.salary_amount, currency),
                    currency,
                    (compensation.authority_digest,),
                )
            )
        allowed_additional = set(compensation.additional_earning_types)
        for earning in sorted(additional_earnings, key=lambda item: item.earning_id):
            if (
                earning.category not in allowed_additional
                or earning.amount < 0
                or not earning.evidence_digest
            ):
                raise GrossPayCalculationError("additional earning is not authorized")
            if earning.currency != currency:
                raise GrossPayCalculationError("cross-currency calculation is prohibited")
            components.append(
                GrossPayEarningComponent(
                    EarningsComponentType.ADDITIONAL,
                    earning.category,
                    None,
                    None,
                    None,
                    _money(earning.amount, currency),
                    currency,
                    (earning.evidence_digest,),
                )
            )
        gross = sum((item.amount for item in components), start=Decimal(0))
        draft = GrossPayCalculationResult(
            "",
            GROSS_PAY_CALCULATION_VERSION,
            company_id,
            employee_id,
            period,
            currency,
            admission.admission_id,
            admission.admission_digest,
            policy.policy_id,
            policy.authority_digest,
            compensation.authority_id,
            compensation.authority_digest,
            time_input.snapshot_id if time_input else None,
            time_input.snapshot_digest if time_input else None,
            tuple(components),
            gross,
            MONEY_ROUNDING_VERSION,
            "",
            calculated_at,
            supersedes_result_id,
        )
        digest = canonical_digest(draft.canonical_economic_content())
        result = GrossPayCalculationResult(
            **{
                **draft.__dict__,
                "result_id": f"gross-pay-calculation:{digest}",
                "calculation_digest": digest,
            }
        )
        result.verify()
        return result
