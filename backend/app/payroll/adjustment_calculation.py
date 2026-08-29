"""Pure deterministic Payroll adjustment calculation over approved authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.models import Journal
from app.platform.permissions.authorization import AuthorizationContext

from .adjustments import PayrollCorrectionType
from .contracts import PayrollAuthorizationError, PayrollConflictError, canonical_digest
from .models import (
    PayrollAdjustmentAuthorityRecord,
    PayrollGrossCalculationResultRecord,
    PayrollPaymentExecutionEvidenceRecord,
    PayrollPaymentExecutionRecord,
    PayrollPaymentReleaseRecord,
    PayrollRunRecord,
    PayrollTaxDeductionResultRecord,
)
from .permissions import PayrollPermission

ADJUSTMENT_CALCULATION_VERSION = "payroll.adjustment-calculation.v1"


class AdjustmentCalculationError(PayrollConflictError):
    pass


class RuleEnvironment(StrEnum):
    TEST = "test"
    PRODUCTION = "production"


class AdjustmentConsequenceType(StrEnum):
    SUCCESSOR_PAYROLL_REQUIRED = "successor_payroll_required"
    OFF_CYCLE_PAYROLL_REQUIRED = "off_cycle_payroll_required"
    TAX_SUCCESSOR_REQUIRED = "tax_successor_required"
    DEDUCTION_SUCCESSOR_REQUIRED = "deduction_successor_required"
    PAYMENT_REISSUE_REQUIRED = "payment_reissue_required"
    PAYMENT_RECOVERY_REQUIRED = "payment_recovery_required"
    SETTLEMENT_RECONCILIATION_REQUIRED = "settlement_reconciliation_required"
    ACCOUNTING_ADJUSTMENT_REQUIRED = "accounting_adjustment_required"
    UNPOSTED_POSTING_FACT_SUPERSESSION = "unposted_posting_fact_supersession"


class RecognitionEffect(StrEnum):
    ACCRUAL_DELTA = "accrual_delta"
    TAX_LIABILITY_DELTA = "tax_liability_delta"
    DEDUCTION_LIABILITY_DELTA = "deduction_liability_delta"
    SETTLEMENT_DELTA = "settlement_delta"
    NO_POSTING_EFFECT = "no_posting_effect"
    ACCOUNTING_ADJUSTMENT = "accounting_adjustment"


@dataclass(frozen=True)
class AdjustmentRuleRequest:
    classification: PayrollCorrectionType
    component: str
    authorized_delta: Decimal
    currency: str
    adjustment_digest: str


@dataclass(frozen=True)
class AdjustmentRuleOutput:
    delta: Decimal
    rule_evidence_digest: str


class AdjustmentRuleProvider(Protocol):
    provider_id: str
    provider_version: str
    environment: RuleEnvironment
    synthetic: bool

    def calculate(self, request: AdjustmentRuleRequest) -> AdjustmentRuleOutput: ...


@dataclass(frozen=True)
class AuthorizedDeltaRuleProvider:
    """Versioned pass-through rule: authority already supplies the signed delta."""

    provider_id: str = "payroll.authorized-delta"
    provider_version: str = "authorized-delta.v1"
    environment: RuleEnvironment = RuleEnvironment.PRODUCTION
    synthetic: bool = False

    def calculate(self, request: AdjustmentRuleRequest) -> AdjustmentRuleOutput:
        return AdjustmentRuleOutput(
            delta=request.authorized_delta,
            rule_evidence_digest=canonical_digest(
                {
                    "provider_id": self.provider_id,
                    "provider_version": self.provider_version,
                    "classification": request.classification.value,
                    "component": request.component,
                    "authorized_delta": str(request.authorized_delta),
                    "currency": request.currency,
                    "adjustment_digest": request.adjustment_digest,
                }
            ),
        )


@dataclass(frozen=True)
class SyntheticTaxAdjustmentProvider(AuthorizedDeltaRuleProvider):
    """Qualification-only tax correction provider; never valid in production."""

    provider_id: str = "synthetic.payroll-tax-adjustment"
    provider_version: str = "synthetic-tax-adjustment.v1"
    environment: RuleEnvironment = RuleEnvironment.TEST
    synthetic: bool = True


@dataclass(frozen=True)
class CalculatedAdjustmentComponent:
    component: str
    delta: Decimal
    currency: str
    recognition_effect: RecognitionEffect
    provider_id: str
    provider_version: str
    rule_evidence_digest: str

    def canonical_content(self) -> dict[str, object]:
        return {
            "component": self.component,
            "delta": str(self.delta),
            "currency": self.currency,
            "recognition_effect": self.recognition_effect.value,
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "rule_evidence_digest": self.rule_evidence_digest,
        }


@dataclass(frozen=True)
class PayrollAdjustmentCalculationCandidate:
    result_identity: str
    definition_version: str
    company_id: UUID
    employee_id: UUID | None
    original_pay_period_id: UUID | None
    correction_pay_period_id: UUID | None
    adjustment_id: UUID
    adjustment_digest: str
    source_type: str
    source_id: UUID
    source_digest: str
    classification: PayrollCorrectionType
    currency: str
    components: tuple[CalculatedAdjustmentComponent, ...]
    consequences: tuple[AdjustmentConsequenceType, ...]
    calculation_digest: str
    calculated_at: datetime

    def canonical_content(self) -> dict[str, object]:
        return {
            "definition_version": self.definition_version,
            "company_id": str(self.company_id),
            "employee_id": str(self.employee_id) if self.employee_id else None,
            "original_pay_period_id": (
                str(self.original_pay_period_id) if self.original_pay_period_id else None
            ),
            "correction_pay_period_id": (
                str(self.correction_pay_period_id)
                if self.correction_pay_period_id
                else None
            ),
            "adjustment_id": str(self.adjustment_id),
            "adjustment_digest": self.adjustment_digest,
            "source_type": self.source_type,
            "source_id": str(self.source_id),
            "source_digest": self.source_digest,
            "classification": self.classification.value,
            "currency": self.currency,
            "components": tuple(item.canonical_content() for item in self.components),
            "consequences": tuple(item.value for item in self.consequences),
        }

    def verify(self) -> None:
        digest = canonical_digest(self.canonical_content())
        if self.calculation_digest != digest or self.result_identity != f"payroll-adjustment-calculation:{digest}":
            raise AdjustmentCalculationError("Payroll adjustment candidate is invalid")


class PayrollAdjustmentCalculationService:
    """Calculates a candidate only; it persists nothing and emits no events."""

    def __init__(self, *, runtime_environment: RuleEnvironment) -> None:
        self.runtime_environment = runtime_environment

    async def calculate(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        adjustment_id: UUID,
        provider: AdjustmentRuleProvider,
    ) -> PayrollAdjustmentCalculationCandidate:
        self._require(context, PayrollPermission.ADJUSTMENT_CALCULATE)
        adjustment = await session.scalar(
            select(PayrollAdjustmentAuthorityRecord).where(
                PayrollAdjustmentAuthorityRecord.company_id == context.company.id,
                PayrollAdjustmentAuthorityRecord.id == adjustment_id,
                PayrollAdjustmentAuthorityRecord.lifecycle == "approved",
            )
        )
        if adjustment is None:
            raise AdjustmentCalculationError("approved Payroll adjustment is required")
        classification = PayrollCorrectionType(adjustment.classification)
        if provider.synthetic and self.runtime_environment is not RuleEnvironment.TEST:
            raise AdjustmentCalculationError(
                "synthetic adjustment provider is prohibited outside test runtime"
            )
        await self._verify_source(session, adjustment)
        self._verify_authority_digest(adjustment)
        components = tuple(
            self._component(adjustment, classification, item, provider)
            for item in sorted(adjustment.delta_components, key=lambda value: str(value["component"]))
        )
        consequences = self._consequences(adjustment, classification)
        content = {
            "definition_version": ADJUSTMENT_CALCULATION_VERSION,
            "company_id": str(adjustment.company_id),
            "employee_id": str(adjustment.employee_id) if adjustment.employee_id else None,
            "original_pay_period_id": str(adjustment.original_pay_period_id) if adjustment.original_pay_period_id else None,
            "correction_pay_period_id": str(adjustment.off_cycle_pay_period_id) if adjustment.off_cycle_pay_period_id else None,
            "adjustment_id": str(adjustment.id),
            "adjustment_digest": adjustment.adjustment_digest,
            "source_type": adjustment.source_type,
            "source_id": str(adjustment.source_id),
            "source_digest": adjustment.source_digest,
            "classification": classification.value,
            "currency": adjustment.currency,
            "components": tuple(item.canonical_content() for item in components),
            "consequences": tuple(item.value for item in consequences),
        }
        digest = canonical_digest(content)
        result = PayrollAdjustmentCalculationCandidate(
            result_identity=f"payroll-adjustment-calculation:{digest}",
            definition_version=ADJUSTMENT_CALCULATION_VERSION,
            company_id=adjustment.company_id,
            employee_id=adjustment.employee_id,
            original_pay_period_id=adjustment.original_pay_period_id,
            correction_pay_period_id=adjustment.off_cycle_pay_period_id,
            adjustment_id=adjustment.id,
            adjustment_digest=adjustment.adjustment_digest,
            source_type=adjustment.source_type,
            source_id=adjustment.source_id,
            source_digest=adjustment.source_digest,
            classification=classification,
            currency=adjustment.currency,
            components=components,
            consequences=consequences,
            calculation_digest=digest,
            calculated_at=datetime.now(timezone.utc),
        )
        result.verify()
        return result

    @staticmethod
    def _component(
        adjustment: PayrollAdjustmentAuthorityRecord,
        classification: PayrollCorrectionType,
        raw: dict[str, object],
        provider: AdjustmentRuleProvider,
    ) -> CalculatedAdjustmentComponent:
        component = str(raw["component"])
        try:
            authorized_delta = Decimal(str(raw["amount"]))
        except Exception as exc:
            raise AdjustmentCalculationError("adjustment delta is invalid") from exc
        if not authorized_delta.is_finite() or authorized_delta == 0:
            raise AdjustmentCalculationError("zero or invalid adjustment delta is prohibited")
        PayrollAdjustmentCalculationService._validate_component(classification, component)
        output = provider.calculate(
            AdjustmentRuleRequest(
                classification=classification,
                component=component,
                authorized_delta=authorized_delta,
                currency=adjustment.currency,
                adjustment_digest=adjustment.adjustment_digest,
            )
        )
        if output.delta != authorized_delta or not output.delta.is_finite():
            raise AdjustmentCalculationError(
                "calculation rule cannot alter the approved adjustment delta"
            )
        return CalculatedAdjustmentComponent(
            component=component,
            delta=output.delta,
            currency=adjustment.currency,
            recognition_effect=PayrollAdjustmentCalculationService._recognition(
                adjustment, classification, component
            ),
            provider_id=provider.provider_id,
            provider_version=provider.provider_version,
            rule_evidence_digest=output.rule_evidence_digest,
        )

    @staticmethod
    async def _verify_source(
        session: AsyncSession, adjustment: PayrollAdjustmentAuthorityRecord
    ) -> None:
        definitions: dict[str, tuple[Any, str]] = {
            "gross_result": (PayrollGrossCalculationResultRecord, "calculation_digest"),
            "tax_result": (PayrollTaxDeductionResultRecord, "calculation_digest"),
            "payroll_run": (PayrollRunRecord, "run_digest"),
            "payment_release": (PayrollPaymentReleaseRecord, "package_digest"),
            "payment_execution": (PayrollPaymentExecutionRecord, "execution_digest"),
            "settlement_evidence": (PayrollPaymentExecutionEvidenceRecord, "evidence_digest"),
        }
        if adjustment.source_type == "posted_accounting_journal":
            value = await session.scalar(
                select(Journal).where(
                    Journal.company_id == adjustment.company_id,
                    Journal.id == adjustment.source_id,
                    Journal.status == "posted",
                    Journal.source_digest == adjustment.source_digest,
                )
            )
        else:
            definition = definitions.get(adjustment.source_type)
            if definition is None:
                if adjustment.source_type == "payroll_posting_fact_candidate" and adjustment.source_evidence.get("posted") is False:
                    return
                raise AdjustmentCalculationError("adjustment source type is unsupported")
            model, digest_field = definition
            value = await session.scalar(
                select(model).where(
                    model.company_id == adjustment.company_id,
                    model.id == adjustment.source_id,
                    getattr(model, digest_field) == adjustment.source_digest,
                )
            )
        if value is None:
            raise AdjustmentCalculationError("adjustment source evidence is stale or unavailable")
        source_employee_id = getattr(value, "employee_id", None)
        if adjustment.employee_id and source_employee_id and adjustment.employee_id != source_employee_id:
            raise AdjustmentCalculationError("adjustment Employee scope mismatch")
        source_period_id = getattr(value, "pay_period_id", None)
        if adjustment.original_pay_period_id and source_period_id and adjustment.original_pay_period_id != source_period_id:
            raise AdjustmentCalculationError("adjustment pay-period scope mismatch")
        source_currency = getattr(value, "currency", None)
        if source_currency and adjustment.currency != source_currency:
            raise AdjustmentCalculationError("adjustment currency mismatch")

    @staticmethod
    def _verify_authority_digest(adjustment: PayrollAdjustmentAuthorityRecord) -> None:
        canonical = {
            "company_id": str(adjustment.company_id),
            "classification": adjustment.classification,
            "reason_code": adjustment.reason_code,
            "source_type": adjustment.source_type,
            "source_id": str(adjustment.source_id),
            "source_digest": adjustment.source_digest,
            "currency": adjustment.currency,
            "effective_date": adjustment.effective_date.isoformat(),
            "evidence_digest": adjustment.evidence_digest,
            "deltas": tuple(
                (str(item["component"]), str(item["amount"]))
                for item in sorted(adjustment.delta_components, key=lambda value: str(value["component"]))
            ),
            "employee_id": str(adjustment.employee_id) if adjustment.employee_id else None,
            "original_pay_period_id": str(adjustment.original_pay_period_id) if adjustment.original_pay_period_id else None,
            "off_cycle_pay_period_id": str(adjustment.off_cycle_pay_period_id) if adjustment.off_cycle_pay_period_id else None,
            "supersedes_adjustment_id": str(adjustment.supersedes_adjustment_id) if adjustment.supersedes_adjustment_id else None,
            "definition_version": adjustment.definition_version,
        }
        if canonical_digest(canonical) != adjustment.adjustment_digest:
            raise AdjustmentCalculationError("approved adjustment authority failed integrity verification")

    @staticmethod
    def _validate_component(classification: PayrollCorrectionType, component: str) -> None:
        tax = {"employee_tax_withholding", "employee_payroll_tax", "employer_payroll_tax"}
        deductions = {"employee_deduction", "employer_contribution"}
        settlement = {"wage_settlement", "net_pay_settlement"}
        if classification is PayrollCorrectionType.TAX_CORRECTION and component not in tax:
            raise AdjustmentCalculationError("tax correction component is invalid")
        if classification is PayrollCorrectionType.DEDUCTION_CORRECTION and component not in deductions:
            raise AdjustmentCalculationError("deduction correction component is invalid")
        if classification in {
            PayrollCorrectionType.PAYMENT_RETURN,
            PayrollCorrectionType.PAYMENT_REJECTION,
            PayrollCorrectionType.PAYMENT_REVERSAL,
            PayrollCorrectionType.SETTLEMENT_CORRECTION,
        } and component not in settlement:
            raise AdjustmentCalculationError(
                "payment correction cannot recreate Payroll accrual components"
            )

    @staticmethod
    def _recognition(
        adjustment: PayrollAdjustmentAuthorityRecord,
        classification: PayrollCorrectionType,
        component: str,
    ) -> RecognitionEffect:
        if adjustment.source_type == "posted_accounting_journal":
            return RecognitionEffect.ACCOUNTING_ADJUSTMENT
        if classification is PayrollCorrectionType.PAYMENT_REJECTION:
            return RecognitionEffect.NO_POSTING_EFFECT
        if classification in {
            PayrollCorrectionType.PAYMENT_RETURN,
            PayrollCorrectionType.PAYMENT_REVERSAL,
            PayrollCorrectionType.SETTLEMENT_CORRECTION,
        }:
            return RecognitionEffect.SETTLEMENT_DELTA
        if "tax" in component:
            return RecognitionEffect.TAX_LIABILITY_DELTA
        if "deduction" in component or "contribution" in component:
            return RecognitionEffect.DEDUCTION_LIABILITY_DELTA
        return RecognitionEffect.ACCRUAL_DELTA

    @staticmethod
    def _consequences(
        adjustment: PayrollAdjustmentAuthorityRecord,
        classification: PayrollCorrectionType,
    ) -> tuple[AdjustmentConsequenceType, ...]:
        mapping = {
            PayrollCorrectionType.PRE_PAYMENT_PAYROLL_CORRECTION: AdjustmentConsequenceType.SUCCESSOR_PAYROLL_REQUIRED,
            PayrollCorrectionType.RETROACTIVE_EARNINGS: AdjustmentConsequenceType.SUCCESSOR_PAYROLL_REQUIRED,
            PayrollCorrectionType.OFF_CYCLE_PAYROLL: AdjustmentConsequenceType.OFF_CYCLE_PAYROLL_REQUIRED,
            PayrollCorrectionType.TAX_CORRECTION: AdjustmentConsequenceType.TAX_SUCCESSOR_REQUIRED,
            PayrollCorrectionType.DEDUCTION_CORRECTION: AdjustmentConsequenceType.DEDUCTION_SUCCESSOR_REQUIRED,
            PayrollCorrectionType.PAYMENT_REJECTION: AdjustmentConsequenceType.PAYMENT_REISSUE_REQUIRED,
            PayrollCorrectionType.PAYMENT_RETURN: AdjustmentConsequenceType.PAYMENT_RECOVERY_REQUIRED,
            PayrollCorrectionType.PAYMENT_REVERSAL: AdjustmentConsequenceType.PAYMENT_RECOVERY_REQUIRED,
            PayrollCorrectionType.SETTLEMENT_CORRECTION: AdjustmentConsequenceType.SETTLEMENT_RECONCILIATION_REQUIRED,
            PayrollCorrectionType.ACCOUNTING_ADJUSTMENT_REQUIRED: AdjustmentConsequenceType.ACCOUNTING_ADJUSTMENT_REQUIRED,
        }
        values = [mapping[classification]]
        if adjustment.source_type == "posted_accounting_journal" and AdjustmentConsequenceType.ACCOUNTING_ADJUSTMENT_REQUIRED not in values:
            values.append(AdjustmentConsequenceType.ACCOUNTING_ADJUSTMENT_REQUIRED)
        if adjustment.source_type == "payroll_posting_fact_candidate":
            values.append(AdjustmentConsequenceType.UNPOSTED_POSTING_FACT_SUPERSESSION)
        return tuple(values)

    @staticmethod
    def _require(context: AuthorizationContext, permission: str) -> None:
        if not context.has_permission(permission):
            raise PayrollAuthorizationError("Payroll adjustment calculation permission denied")
