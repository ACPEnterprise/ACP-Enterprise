"""Deterministic tax, deduction, and net-pay candidates over approved evidence.

This module does not persist results, file/remit taxes, pay Employees, or post
Accounting entries. Provider rules supplied here are evidence-bound inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from .calculation import GrossPayCalculationResult
from .contracts import (
    PayrollAuthorityError,
    PayrollAuthorizationError,
    canonical_digest,
)
from .permissions import PayrollPermission
from .tax_authority import (
    AuthorityResolution,
    PayrollInputDomain,
    TaxDeductionAdmissionResult,
    TaxDeductionAdmissionState,
)

TAX_DEDUCTION_CALCULATION_VERSION = "payroll.tax-deduction-calculation.v1"
TAX_CALCULATION_MONEY_VERSION = "money.currency-minor-unit-provider-rounding.v1"


class TaxDeductionCalculationError(PayrollAuthorityError):
    pass


class ProviderEnvironment(StrEnum):
    TEST = "test"
    PRODUCTION = "production"


class TaxResponsibility(StrEnum):
    EMPLOYEE_WITHHOLDING = "employee_withholding"
    EMPLOYEE_PAYROLL_TAX = "employee_payroll_tax"
    EMPLOYER_PAYROLL_TAX = "employer_payroll_tax"


class ComponentKind(StrEnum):
    TAX = "tax"
    EMPLOYEE_DEDUCTION = "employee_deduction"
    EMPLOYER_CONTRIBUTION = "employer_contribution"


class DeductionBasis(StrEnum):
    FIXED_AMOUNT = "fixed_amount"
    PERCENTAGE_OF_GROSS = "percentage_of_gross"
    SUPPLIED_CALCULATION_REFERENCE = "supplied_calculation_reference"


@dataclass(frozen=True)
class ApprovedGrossPayEvidence:
    """Verified projection binding a persisted approved row to its candidate."""

    persisted_result_id: UUID
    persisted_lifecycle: str
    persisted_company_id: UUID
    persisted_employee_id: UUID
    persisted_pay_period_id: UUID
    persisted_calculation_digest: str
    persisted_currency: str
    persisted_gross_pay_total: Decimal
    candidate: GrossPayCalculationResult

    def verify(self) -> None:
        self.candidate.verify()
        if self.persisted_lifecycle != "approved":
            raise TaxDeductionCalculationError(
                "approved persisted gross-pay result is required"
            )
        if (
            self.persisted_company_id != self.candidate.company_id
            or self.persisted_employee_id != self.candidate.employee_id
            or self.persisted_pay_period_id != self.candidate.pay_period.pay_period_id
            or self.persisted_calculation_digest != self.candidate.calculation_digest
            or self.persisted_currency != self.candidate.currency
            or self.persisted_gross_pay_total != self.candidate.gross_pay_total
        ):
            raise TaxDeductionCalculationError(
                "persisted gross-pay evidence does not match verified candidate"
            )


@dataclass(frozen=True)
class TaxRuleRequest:
    component_key: str
    responsibility: TaxResponsibility
    authority: AuthorityResolution
    jurisdiction_reference: str
    taxable_basis: Decimal
    currency: str
    requires_protected_input: bool


@dataclass(frozen=True)
class TaxRuleOutput:
    amount: Decimal
    provider_version: str
    rounding_rule: str
    taxable_basis: Decimal
    evidence_digest: str


class TaxRuleProvider(Protocol):
    provider_id: str
    provider_version: str
    environment: ProviderEnvironment

    def calculate(self, request: TaxRuleRequest) -> TaxRuleOutput: ...


@dataclass(frozen=True)
class SyntheticRateTaxProvider:
    """Explicitly test-only rate provider; production execution rejects it."""

    provider_id: str
    provider_version: str
    rate: Decimal
    rounding_rule: str = "currency_minor_unit_half_even"
    environment: ProviderEnvironment = ProviderEnvironment.TEST

    def calculate(self, request: TaxRuleRequest) -> TaxRuleOutput:
        if self.rate < 0:
            raise TaxDeductionCalculationError("synthetic provider rate is invalid")
        amount = _money(request.taxable_basis * self.rate, request.currency)
        return TaxRuleOutput(
            amount=amount,
            provider_version=self.provider_version,
            rounding_rule=self.rounding_rule,
            taxable_basis=request.taxable_basis,
            evidence_digest=canonical_digest(
                {
                    "provider_id": self.provider_id,
                    "provider_version": self.provider_version,
                    "environment": self.environment.value,
                    "rate": str(self.rate),
                    "rounding_rule": self.rounding_rule,
                    "request": {
                        "component_key": request.component_key,
                        "responsibility": request.responsibility.value,
                        "authority_digest": request.authority.authority_digest,
                        "protected_input_digest": (
                            request.authority.protected_input_digest
                        ),
                        "jurisdiction_reference": request.jurisdiction_reference,
                        "taxable_basis": str(request.taxable_basis),
                        "currency": request.currency,
                    },
                }
            ),
        )


@dataclass(frozen=True)
class TaxComponentInstruction:
    component_key: str
    responsibility: TaxResponsibility
    authority_id: UUID
    authority_digest: str
    jurisdiction_reference: str
    requires_protected_input: bool
    provider: TaxRuleProvider


@dataclass(frozen=True)
class DeductionInstruction:
    component_key: str
    authority_id: UUID
    authority_digest: str
    basis: DeductionBasis
    priority: int
    currency: str
    fixed_amount: Decimal | None = None
    percentage: Decimal | None = None
    cap_amount: Decimal | None = None
    supplied_reference: str | None = None


@dataclass(frozen=True)
class EmployerContributionInstruction:
    component_key: str
    authority_id: UUID
    authority_digest: str
    basis: DeductionBasis
    priority: int
    currency: str
    fixed_amount: Decimal | None = None
    percentage: Decimal | None = None
    cap_amount: Decimal | None = None


@dataclass(frozen=True)
class TaxDeductionComponent:
    component_key: str
    kind: ComponentKind
    responsibility: str
    authority_id: UUID
    authority_digest: str
    provider_id: str | None
    provider_version: str | None
    jurisdiction_reference: str | None
    calculation_basis: str
    basis_amount: Decimal
    amount: Decimal
    currency: str
    priority: int
    rounding_rule: str
    evidence_digest: str

    def canonical_content(self) -> dict[str, object]:
        return {
            "component_key": self.component_key,
            "kind": self.kind.value,
            "responsibility": self.responsibility,
            "authority_id": str(self.authority_id),
            "authority_digest": self.authority_digest,
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "jurisdiction_reference": self.jurisdiction_reference,
            "calculation_basis": self.calculation_basis,
            "basis_amount": str(self.basis_amount),
            "amount": str(self.amount),
            "currency": self.currency,
            "priority": self.priority,
            "rounding_rule": self.rounding_rule,
            "evidence_digest": self.evidence_digest,
        }


@dataclass(frozen=True)
class TaxDeductionCalculationResult:
    result_id: str
    definition_version: str
    company_id: UUID
    employee_id: UUID
    pay_period_id: UUID
    gross_result_id: UUID
    gross_calculation_digest: str
    currency: str
    admission_digest: str
    components: tuple[TaxDeductionComponent, ...]
    gross_pay: Decimal
    total_employee_taxes: Decimal
    total_employee_deductions: Decimal
    total_employer_contributions: Decimal
    net_pay_candidate: Decimal
    money_version: str
    calculation_digest: str
    calculated_at: datetime
    supersedes_result_id: str | None = None

    def canonical_economic_content(self) -> dict[str, object]:
        return {
            "definition_version": self.definition_version,
            "company_id": str(self.company_id),
            "employee_id": str(self.employee_id),
            "pay_period_id": str(self.pay_period_id),
            "gross_result_id": str(self.gross_result_id),
            "gross_calculation_digest": self.gross_calculation_digest,
            "currency": self.currency,
            "admission_digest": self.admission_digest,
            "components": tuple(item.canonical_content() for item in self.components),
            "gross_pay": str(self.gross_pay),
            "total_employee_taxes": str(self.total_employee_taxes),
            "total_employee_deductions": str(self.total_employee_deductions),
            "total_employer_contributions": str(
                self.total_employer_contributions
            ),
            "net_pay_candidate": str(self.net_pay_candidate),
            "money_version": self.money_version,
            "supersedes_result_id": self.supersedes_result_id,
        }

    def verify(self) -> None:
        digest = canonical_digest(self.canonical_economic_content())
        if digest != self.calculation_digest:
            raise TaxDeductionCalculationError("tax calculation digest mismatch")
        if self.result_id != f"tax-deduction-calculation:{digest}":
            raise TaxDeductionCalculationError("tax calculation identity mismatch")
        employee_tax = sum(
            (
                item.amount
                for item in self.components
                if item.kind is ComponentKind.TAX
                and item.responsibility
                in {
                    TaxResponsibility.EMPLOYEE_WITHHOLDING.value,
                    TaxResponsibility.EMPLOYEE_PAYROLL_TAX.value,
                }
            ),
            Decimal(0),
        )
        deductions = sum(
            (
                item.amount
                for item in self.components
                if item.kind is ComponentKind.EMPLOYEE_DEDUCTION
            ),
            Decimal(0),
        )
        employer = sum(
            (
                item.amount
                for item in self.components
                if item.kind is ComponentKind.EMPLOYER_CONTRIBUTION
                or (
                    item.kind is ComponentKind.TAX
                    and item.responsibility
                    == TaxResponsibility.EMPLOYER_PAYROLL_TAX.value
                )
            ),
            Decimal(0),
        )
        if (
            employee_tax != self.total_employee_taxes
            or deductions != self.total_employee_deductions
            or employer != self.total_employer_contributions
            or self.net_pay_candidate
            != self.gross_pay - employee_tax - deductions
            or self.net_pay_candidate < 0
            or any(item.currency != self.currency for item in self.components)
        ):
            raise TaxDeductionCalculationError(
                "tax/deduction component reconciliation failed"
            )

    def safe_event_evidence(self) -> dict[str, object]:
        """Broad audit/event-safe evidence; deliberately excludes all amounts."""
        return {
            "result_id": self.result_id,
            "calculation_digest": self.calculation_digest,
            "definition_version": self.definition_version,
            "gross_result_id": str(self.gross_result_id),
            "state": "calculated_candidate",
        }


def _money(value: Decimal, currency: str) -> Decimal:
    if currency != "USD":
        raise TaxDeductionCalculationError(
            "unsupported or cross-currency composition"
        )
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


def _resolution(
    admission: TaxDeductionAdmissionResult,
    *,
    domain: PayrollInputDomain,
    authority_id: UUID,
    authority_digest: str,
) -> AuthorityResolution:
    matches = tuple(
        item
        for item in admission.resolutions
        if item.requirement.domain is domain
        and item.authority_id == authority_id
        and item.authority_digest == authority_digest
    )
    if len(matches) != 1 or matches[0].state is not TaxDeductionAdmissionState.READY:
        raise TaxDeductionCalculationError(
            "component is not backed by one ready admitted authority"
        )
    return matches[0]


def _bounded_amount(
    *,
    basis: DeductionBasis,
    gross: Decimal,
    currency: str,
    fixed_amount: Decimal | None,
    percentage: Decimal | None,
    cap_amount: Decimal | None,
) -> Decimal:
    if basis is DeductionBasis.FIXED_AMOUNT:
        if fixed_amount is None or fixed_amount < 0 or percentage is not None:
            raise TaxDeductionCalculationError("fixed authority shape is invalid")
        amount = fixed_amount
    elif basis is DeductionBasis.PERCENTAGE_OF_GROSS:
        if percentage is None or percentage < 0 or fixed_amount is not None:
            raise TaxDeductionCalculationError("percentage authority shape is invalid")
        amount = gross * percentage
    else:
        raise TaxDeductionCalculationError(
            "supplied calculation reference requires an authorized provider"
        )
    if cap_amount is not None:
        if cap_amount < 0:
            raise TaxDeductionCalculationError("component cap is invalid")
        amount = min(amount, cap_amount)
    return _money(amount, currency)


class PayrollTaxDeductionCalculationEngine:
    def __init__(self, *, runtime_environment: ProviderEnvironment) -> None:
        self.runtime_environment = runtime_environment

    def calculate(
        self,
        *,
        actor_permissions: frozenset[str],
        gross: ApprovedGrossPayEvidence,
        admission: TaxDeductionAdmissionResult,
        tax_instructions: tuple[TaxComponentInstruction, ...] = (),
        deduction_instructions: tuple[DeductionInstruction, ...] = (),
        employer_contribution_instructions: tuple[
            EmployerContributionInstruction, ...
        ] = (),
        calculated_at: datetime,
        supersedes_result_id: str | None = None,
    ) -> TaxDeductionCalculationResult:
        if PayrollPermission.TAX_CALCULATION_EXECUTE not in actor_permissions:
            raise PayrollAuthorizationError(
                "tax/deduction calculation authority is required"
            )
        gross.verify()
        admission.verify()
        if admission.state not in {
            TaxDeductionAdmissionState.READY,
            TaxDeductionAdmissionState.NOT_APPLICABLE,
        }:
            raise TaxDeductionCalculationError(
                "tax/deduction admission is not ready"
            )
        if (
            admission.company_id != gross.persisted_company_id
            or admission.employee_id != gross.persisted_employee_id
            or admission.gross_result_id != gross.persisted_result_id
            or admission.gross_calculation_digest
            != gross.persisted_calculation_digest
        ):
            raise TaxDeductionCalculationError(
                "tax/deduction admission gross-pay scope mismatch"
            )
        if admission.state is TaxDeductionAdmissionState.NOT_APPLICABLE and (
            tax_instructions
            or deduction_instructions
            or employer_contribution_instructions
        ):
            raise TaxDeductionCalculationError(
                "not-applicable admission cannot produce components"
            )
        currency = gross.persisted_currency
        gross_amount = _money(gross.persisted_gross_pay_total, currency)
        components: list[TaxDeductionComponent] = []
        for tax_instruction in sorted(
            tax_instructions,
            key=lambda item: (item.responsibility.value, item.component_key),
        ):
            resolution = _resolution(
                admission,
                domain=PayrollInputDomain.TAX,
                authority_id=tax_instruction.authority_id,
                authority_digest=tax_instruction.authority_digest,
            )
            if (
                tax_instruction.requires_protected_input
                and not resolution.protected_input_digest
            ):
                raise TaxDeductionCalculationError(
                    "required protected tax input evidence is missing"
                )
            provider = tax_instruction.provider
            if (
                provider.environment is ProviderEnvironment.TEST
                and self.runtime_environment is not ProviderEnvironment.TEST
            ):
                raise TaxDeductionCalculationError(
                    "synthetic tax provider is prohibited outside test runtime"
                )
            output = provider.calculate(
                TaxRuleRequest(
                    component_key=tax_instruction.component_key,
                    responsibility=tax_instruction.responsibility,
                    authority=resolution,
                    jurisdiction_reference=tax_instruction.jurisdiction_reference,
                    taxable_basis=gross_amount,
                    currency=currency,
                    requires_protected_input=tax_instruction.requires_protected_input,
                )
            )
            if output.amount < 0 or output.taxable_basis != gross_amount:
                raise TaxDeductionCalculationError("tax provider output is invalid")
            components.append(
                TaxDeductionComponent(
                    component_key=tax_instruction.component_key,
                    kind=ComponentKind.TAX,
                    responsibility=tax_instruction.responsibility.value,
                    authority_id=tax_instruction.authority_id,
                    authority_digest=tax_instruction.authority_digest,
                    provider_id=provider.provider_id,
                    provider_version=output.provider_version,
                    jurisdiction_reference=tax_instruction.jurisdiction_reference,
                    calculation_basis="approved_gross_pay",
                    basis_amount=gross_amount,
                    amount=output.amount,
                    currency=currency,
                    priority=0,
                    rounding_rule=output.rounding_rule,
                    evidence_digest=output.evidence_digest,
                )
            )
        for deduction_instruction in sorted(
            deduction_instructions,
            key=lambda item: (item.priority, item.component_key),
        ):
            _resolution(
                admission,
                domain=PayrollInputDomain.DEDUCTION,
                authority_id=deduction_instruction.authority_id,
                authority_digest=deduction_instruction.authority_digest,
            )
            if deduction_instruction.currency != currency:
                raise TaxDeductionCalculationError("deduction currency mismatch")
            amount = _bounded_amount(
                basis=deduction_instruction.basis,
                gross=gross_amount,
                currency=currency,
                fixed_amount=deduction_instruction.fixed_amount,
                percentage=deduction_instruction.percentage,
                cap_amount=deduction_instruction.cap_amount,
            )
            components.append(
                self._non_tax_component(
                    instruction=deduction_instruction,
                    kind=ComponentKind.EMPLOYEE_DEDUCTION,
                    amount=amount,
                    gross=gross_amount,
                )
            )
        for employer_instruction in sorted(
            employer_contribution_instructions,
            key=lambda item: (item.priority, item.component_key),
        ):
            _resolution(
                admission,
                domain=PayrollInputDomain.EMPLOYER_CONTRIBUTION,
                authority_id=employer_instruction.authority_id,
                authority_digest=employer_instruction.authority_digest,
            )
            if employer_instruction.currency != currency:
                raise TaxDeductionCalculationError(
                    "employer contribution currency mismatch"
                )
            amount = _bounded_amount(
                basis=employer_instruction.basis,
                gross=gross_amount,
                currency=currency,
                fixed_amount=employer_instruction.fixed_amount,
                percentage=employer_instruction.percentage,
                cap_amount=employer_instruction.cap_amount,
            )
            components.append(
                self._non_tax_component(
                    instruction=employer_instruction,
                    kind=ComponentKind.EMPLOYER_CONTRIBUTION,
                    amount=amount,
                    gross=gross_amount,
                )
            )
        ordered = tuple(
            sorted(
                components,
                key=lambda item: (item.kind.value, item.priority, item.component_key),
            )
        )
        employee_taxes = _money(
            sum(
                (
                    item.amount
                    for item in ordered
                    if item.kind is ComponentKind.TAX
                    and item.responsibility
                    in {
                        TaxResponsibility.EMPLOYEE_WITHHOLDING.value,
                        TaxResponsibility.EMPLOYEE_PAYROLL_TAX.value,
                    }
                ),
                Decimal(0),
            ),
            currency,
        )
        employee_deductions = _money(
            sum(
                (
                    item.amount
                    for item in ordered
                    if item.kind is ComponentKind.EMPLOYEE_DEDUCTION
                ),
                Decimal(0),
            ),
            currency,
        )
        employer_total = _money(
            sum(
                (
                    item.amount
                    for item in ordered
                    if item.kind is ComponentKind.EMPLOYER_CONTRIBUTION
                    or (
                        item.kind is ComponentKind.TAX
                        and item.responsibility
                        == TaxResponsibility.EMPLOYER_PAYROLL_TAX.value
                    )
                ),
                Decimal(0),
            ),
            currency,
        )
        net = _money(gross_amount - employee_taxes - employee_deductions, currency)
        if net < 0:
            raise TaxDeductionCalculationError(
                "taxes and deductions would produce negative net pay"
            )
        provisional = TaxDeductionCalculationResult(
            result_id="",
            definition_version=TAX_DEDUCTION_CALCULATION_VERSION,
            company_id=gross.persisted_company_id,
            employee_id=gross.persisted_employee_id,
            pay_period_id=gross.persisted_pay_period_id,
            gross_result_id=gross.persisted_result_id,
            gross_calculation_digest=gross.persisted_calculation_digest,
            currency=currency,
            admission_digest=admission.admission_digest,
            components=ordered,
            gross_pay=gross_amount,
            total_employee_taxes=employee_taxes,
            total_employee_deductions=employee_deductions,
            total_employer_contributions=employer_total,
            net_pay_candidate=net,
            money_version=TAX_CALCULATION_MONEY_VERSION,
            calculation_digest="",
            calculated_at=calculated_at,
            supersedes_result_id=supersedes_result_id,
        )
        digest = canonical_digest(provisional.canonical_economic_content())
        result = TaxDeductionCalculationResult(
            **{
                **provisional.__dict__,
                "result_id": f"tax-deduction-calculation:{digest}",
                "calculation_digest": digest,
            }
        )
        result.verify()
        return result

    @staticmethod
    def _non_tax_component(
        *,
        instruction: DeductionInstruction | EmployerContributionInstruction,
        kind: ComponentKind,
        amount: Decimal,
        gross: Decimal,
    ) -> TaxDeductionComponent:
        return TaxDeductionComponent(
            component_key=instruction.component_key,
            kind=kind,
            responsibility=kind.value,
            authority_id=instruction.authority_id,
            authority_digest=instruction.authority_digest,
            provider_id=None,
            provider_version=None,
            jurisdiction_reference=None,
            calculation_basis=instruction.basis.value,
            basis_amount=gross,
            amount=amount,
            currency=instruction.currency,
            priority=instruction.priority,
            rounding_rule="currency_minor_unit_half_even",
            evidence_digest=canonical_digest(
                {
                    "authority_id": str(instruction.authority_id),
                    "authority_digest": instruction.authority_digest,
                    "basis": instruction.basis.value,
                    "basis_amount": str(gross),
                    "amount": str(amount),
                    "cap_amount": (
                        str(instruction.cap_amount)
                        if instruction.cap_amount is not None
                        else None
                    ),
                }
            ),
        )
