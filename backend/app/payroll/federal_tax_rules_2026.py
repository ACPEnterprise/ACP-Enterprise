"""Official 2026 US federal Payroll tax rules.

This is a calculation-only provider. It does not infer employee elections,
persist Payroll results, file taxes, or move money. Callers must admit the
effective W-4 and YTD evidence before constructing a provider.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Final

from .contracts import canonical_digest
from .tax_calculation import (
    ProviderEnvironment,
    TaxDeductionCalculationError,
    TaxResponsibility,
    TaxRuleOutput,
    TaxRuleRequest,
)

CALCULATION_METHOD_VERSION: Final = "irs-2026-percentage-method-automated.v1"
PROVIDER_VERSION: Final = "us-federal-payroll-tax-rules.2026.v1"
ROUNDING_RULE: Final = "currency_minor_unit_half_up"


@dataclass(frozen=True, slots=True)
class RuleSource:
    jurisdiction: str
    tax_type: str
    source_authority: str
    source_publication_version: str
    effective_from: date
    effective_to: date | None
    source_reference: str
    source_sha256: str
    calculation_method_version: str


IRS_15T_SOURCE: Final = RuleSource(
    jurisdiction="US-FEDERAL",
    tax_type="federal_income_tax_withholding",
    source_authority="United States Internal Revenue Service",
    source_publication_version="Publication 15-T (2026)",
    effective_from=date(2026, 1, 1),
    effective_to=date(2026, 12, 31),
    source_reference="https://www.irs.gov/pub/irs-prior/p15t--2026.pdf",
    source_sha256="31b3e2428628e8d2e40f6266c2c8f1b9b0b6ccd24607895f9b3be3d9d306d3fb",
    calculation_method_version=CALCULATION_METHOD_VERSION,
)
IRS_15_SOURCE: Final = RuleSource(
    jurisdiction="US-FEDERAL",
    tax_type="fica",
    source_authority="United States Internal Revenue Service",
    source_publication_version="Publication 15 (2026), Circular E",
    effective_from=date(2026, 1, 1),
    effective_to=date(2026, 12, 31),
    source_reference="https://www.irs.gov/pub/irs-prior/p15--2026.pdf",
    source_sha256="b46c3622439d8521e3a0faca4cd5b5ece3451b526f65f06a5e38d5c9f804c88b",
    calculation_method_version=CALCULATION_METHOD_VERSION,
)
FLORIDA_SOURCE: Final = RuleSource(
    jurisdiction="US-FL",
    tax_type="employee_state_income_tax_withholding",
    source_authority="Florida Department of Revenue",
    source_publication_version="Florida DOR FAQ ID 1466",
    effective_from=date(2026, 1, 1),
    effective_to=date(2026, 12, 31),
    source_reference="https://floridarevenue.com/faq/Pages/FAQDetails.aspx?FAQID=1466",
    source_sha256="842a381379c6bfcce4ef753ce52651702c17510ace35885dee86e8b60ff65bd8",
    calculation_method_version="florida-individual-income-tax-applicability.2026.v1",
)


class FilingStatus(StrEnum):
    MARRIED_FILING_JOINTLY = "married_filing_jointly"
    SINGLE_OR_MARRIED_FILING_SEPARATELY = "single_or_married_filing_separately"
    HEAD_OF_HOUSEHOLD = "head_of_household"


class PayFrequency(StrEnum):
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    SEMIMONTHLY = "semimonthly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMIANNUALLY = "semiannually"
    ANNUALLY = "annually"


PERIODS: Final = {
    PayFrequency.WEEKLY: Decimal(52),
    PayFrequency.BIWEEKLY: Decimal(26),
    PayFrequency.SEMIMONTHLY: Decimal(24),
    PayFrequency.MONTHLY: Decimal(12),
    PayFrequency.QUARTERLY: Decimal(4),
    PayFrequency.SEMIANNUALLY: Decimal(2),
    PayFrequency.ANNUALLY: Decimal(1),
}


@dataclass(frozen=True, slots=True)
class W4Election:
    filing_status: FilingStatus
    step_2_checked: bool
    step_3_credits: Decimal
    step_4a_other_income: Decimal
    step_4b_deductions: Decimal
    step_4c_extra_withholding: Decimal
    form_year: int = 2026

    def validate(self) -> None:
        if self.form_year < 2020 or any(
            value < 0
            for value in (
                self.step_3_credits,
                self.step_4a_other_income,
                self.step_4b_deductions,
                self.step_4c_extra_withholding,
            )
        ):
            raise TaxDeductionCalculationError("unsupported or invalid W-4 election")


@dataclass(frozen=True, slots=True)
class FederalTaxContext:
    effective_on: date
    pay_frequency: PayFrequency
    w4: W4Election
    social_security_wages_ytd: Decimal
    medicare_wages_ytd: Decimal
    pretax_federal_deductions: Decimal = Decimal(0)
    pretax_fica_deductions: Decimal = Decimal(0)

    def validate(self) -> None:
        self.w4.validate()
        if not IRS_15T_SOURCE.effective_from <= self.effective_on <= date(2026, 12, 31):
            raise TaxDeductionCalculationError(
                "2026 federal rules are not effective for calculation date"
            )
        if any(
            value < 0
            for value in (
                self.social_security_wages_ytd,
                self.medicare_wages_ytd,
                self.pretax_federal_deductions,
                self.pretax_fica_deductions,
            )
        ):
            raise TaxDeductionCalculationError(
                "federal tax context amounts cannot be negative"
            )


@dataclass(frozen=True, slots=True)
class _Bracket:
    floor: Decimal
    ceiling: Decimal | None
    base_tax: Decimal
    rate: Decimal


def _brackets(*rows: tuple[str, str | None, str, str]) -> tuple[_Bracket, ...]:
    return tuple(
        _Bracket(
            Decimal(low), Decimal(high) if high else None, Decimal(base), Decimal(rate)
        )
        for low, high, base, rate in rows
    )


_STANDARD: Final = {
    FilingStatus.MARRIED_FILING_JOINTLY: _brackets(
        ("0", "19300", "0", "0"),
        ("19300", "44100", "0", ".10"),
        ("44100", "120100", "2480", ".12"),
        ("120100", "230700", "11600", ".22"),
        ("230700", "422850", "35932", ".24"),
        ("422850", "531750", "82048", ".32"),
        ("531750", "788000", "116896", ".35"),
        ("788000", None, "206583.50", ".37"),
    ),
    FilingStatus.SINGLE_OR_MARRIED_FILING_SEPARATELY: _brackets(
        ("0", "7500", "0", "0"),
        ("7500", "19900", "0", ".10"),
        ("19900", "57900", "1240", ".12"),
        ("57900", "113200", "5800", ".22"),
        ("113200", "209275", "17966", ".24"),
        ("209275", "263725", "41024", ".32"),
        ("263725", "648100", "58448", ".35"),
        ("648100", None, "192979.25", ".37"),
    ),
    FilingStatus.HEAD_OF_HOUSEHOLD: _brackets(
        ("0", "15550", "0", "0"),
        ("15550", "33250", "0", ".10"),
        ("33250", "83000", "1770", ".12"),
        ("83000", "121250", "7740", ".22"),
        ("121250", "217300", "16155", ".24"),
        ("217300", "271750", "39207", ".32"),
        ("271750", "656150", "56631", ".35"),
        ("656150", None, "191171", ".37"),
    ),
}
_STEP2: Final = {
    FilingStatus.MARRIED_FILING_JOINTLY: _brackets(
        ("0", "16100", "0", "0"),
        ("16100", "28500", "0", ".10"),
        ("28500", "66500", "1240", ".12"),
        ("66500", "121800", "5800", ".22"),
        ("121800", "217875", "17966", ".24"),
        ("217875", "272325", "41024", ".32"),
        ("272325", "400450", "58448", ".35"),
        ("400450", None, "103291.75", ".37"),
    ),
    FilingStatus.SINGLE_OR_MARRIED_FILING_SEPARATELY: _brackets(
        ("0", "8050", "0", "0"),
        ("8050", "14250", "0", ".10"),
        ("14250", "33250", "620", ".12"),
        ("33250", "60900", "2900", ".22"),
        ("60900", "108938", "8983", ".24"),
        ("108938", "136163", "20512", ".32"),
        ("136163", "328350", "29224", ".35"),
        ("328350", None, "96489.63", ".37"),
    ),
    FilingStatus.HEAD_OF_HOUSEHOLD: _brackets(
        ("0", "12075", "0", "0"),
        ("12075", "20925", "0", ".10"),
        ("20925", "45800", "885", ".12"),
        ("45800", "64925", "3870", ".22"),
        ("64925", "112950", "8077.50", ".24"),
        ("112950", "140175", "19603.50", ".32"),
        ("140175", "332375", "28315.50", ".35"),
        ("332375", None, "95585.50", ".37"),
    ),
}

SOCIAL_SECURITY_RATE: Final = Decimal("0.062")
SOCIAL_SECURITY_WAGE_BASE: Final = Decimal(184500)
MEDICARE_RATE: Final = Decimal("0.0145")
ADDITIONAL_MEDICARE_RATE: Final = Decimal("0.009")
ADDITIONAL_MEDICARE_WITHHOLDING_THRESHOLD: Final = Decimal(200000)


class FederalComponent(StrEnum):
    FEDERAL_INCOME_TAX = "federal_income_tax_withholding"
    SOCIAL_SECURITY_EMPLOYEE = "social_security_employee"
    SOCIAL_SECURITY_EMPLOYER = "social_security_employer"
    MEDICARE_EMPLOYEE = "medicare_employee"
    MEDICARE_EMPLOYER = "medicare_employer"
    ADDITIONAL_MEDICARE_EMPLOYEE = "additional_medicare_employee"


@dataclass(frozen=True, slots=True)
class Federal2026TaxRuleProvider:
    context: FederalTaxContext
    component: FederalComponent
    provider_id: str = "acp.official-us-federal-tax-rule-provider"
    provider_version: str = PROVIDER_VERSION
    environment: ProviderEnvironment = ProviderEnvironment.PRODUCTION

    def calculate(self, request: TaxRuleRequest) -> TaxRuleOutput:
        self.context.validate()
        self._validate_request(request)
        gross = request.taxable_basis
        federal_wages = max(Decimal(0), gross - self.context.pretax_federal_deductions)
        fica_wages = max(Decimal(0), gross - self.context.pretax_fica_deductions)
        source = (
            IRS_15T_SOURCE
            if self.component is FederalComponent.FEDERAL_INCOME_TAX
            else IRS_15_SOURCE
        )
        if self.component is FederalComponent.FEDERAL_INCOME_TAX:
            amount = self._federal_withholding(federal_wages)
            basis = federal_wages
        elif self.component in {
            FederalComponent.SOCIAL_SECURITY_EMPLOYEE,
            FederalComponent.SOCIAL_SECURITY_EMPLOYER,
        }:
            basis = min(
                fica_wages,
                max(
                    Decimal(0),
                    SOCIAL_SECURITY_WAGE_BASE - self.context.social_security_wages_ytd,
                ),
            )
            amount = _money(basis * SOCIAL_SECURITY_RATE)
        elif self.component in {
            FederalComponent.MEDICARE_EMPLOYEE,
            FederalComponent.MEDICARE_EMPLOYER,
        }:
            basis = fica_wages
            amount = _money(basis * MEDICARE_RATE)
        else:
            before = max(
                Decimal(0),
                self.context.medicare_wages_ytd
                - ADDITIONAL_MEDICARE_WITHHOLDING_THRESHOLD,
            )
            after = max(
                Decimal(0),
                self.context.medicare_wages_ytd
                + fica_wages
                - ADDITIONAL_MEDICARE_WITHHOLDING_THRESHOLD,
            )
            basis = after - before
            amount = _money(basis * ADDITIONAL_MEDICARE_RATE)
        return TaxRuleOutput(
            amount=amount,
            provider_version=self.provider_version,
            rounding_rule=ROUNDING_RULE,
            taxable_basis=basis,
            evidence_digest=canonical_digest(
                {
                    "provider_id": self.provider_id,
                    "provider_version": self.provider_version,
                    "component": self.component.value,
                    "source": asdict(source),
                    "context": asdict(self.context),
                    "request_authority_digest": request.authority.authority_digest,
                    "protected_input_digest": request.authority.protected_input_digest,
                    "amount": str(amount),
                    "taxable_basis": str(basis),
                    "rounding_rule": ROUNDING_RULE,
                }
            ),
        )

    def _federal_withholding(self, taxable_wages: Decimal) -> Decimal:
        periods = PERIODS[self.context.pay_frequency]
        w4 = self.context.w4
        offset = (
            Decimal(0)
            if w4.step_2_checked
            else (
                Decimal(12900)
                if w4.filing_status is FilingStatus.MARRIED_FILING_JOINTLY
                else Decimal(8600)
            )
        )
        adjusted_annual = max(
            Decimal(0),
            taxable_wages * periods
            + w4.step_4a_other_income
            - w4.step_4b_deductions
            - offset,
        )
        table = (_STEP2 if w4.step_2_checked else _STANDARD)[w4.filing_status]
        bracket = next(
            row
            for row in table
            if adjusted_annual >= row.floor
            and (row.ceiling is None or adjusted_annual < row.ceiling)
        )
        annual_tax = bracket.base_tax + (adjusted_annual - bracket.floor) * bracket.rate
        per_period = max(Decimal(0), annual_tax / periods - w4.step_3_credits / periods)
        return _money(per_period + w4.step_4c_extra_withholding)

    def _validate_request(self, request: TaxRuleRequest) -> None:
        expected_responsibility = {
            FederalComponent.FEDERAL_INCOME_TAX: TaxResponsibility.EMPLOYEE_WITHHOLDING,
            FederalComponent.SOCIAL_SECURITY_EMPLOYEE: TaxResponsibility.EMPLOYEE_PAYROLL_TAX,
            FederalComponent.SOCIAL_SECURITY_EMPLOYER: TaxResponsibility.EMPLOYER_PAYROLL_TAX,
            FederalComponent.MEDICARE_EMPLOYEE: TaxResponsibility.EMPLOYEE_PAYROLL_TAX,
            FederalComponent.MEDICARE_EMPLOYER: TaxResponsibility.EMPLOYER_PAYROLL_TAX,
            FederalComponent.ADDITIONAL_MEDICARE_EMPLOYEE: TaxResponsibility.EMPLOYEE_PAYROLL_TAX,
        }[self.component]
        if (
            request.component_key != self.component.value
            or request.currency != "USD"
            or request.responsibility is not expected_responsibility
        ):
            raise TaxDeductionCalculationError("federal tax request contract mismatch")
        if not request.authority.protected_input_digest:
            raise TaxDeductionCalculationError(
                "federal tax election evidence is missing"
            )


def florida_state_income_tax_applicability(
    *, work_jurisdiction: str, residence_jurisdiction: str
) -> tuple[str, RuleSource]:
    """Return NOT_APPLICABLE only from explicit Florida jurisdiction evidence."""
    if work_jurisdiction != "US-FL" or residence_jurisdiction != "US-FL":
        raise TaxDeductionCalculationError(
            "Florida state withholding requires explicit US-FL work and residence evidence"
        )
    return "NOT_APPLICABLE", FLORIDA_SOURCE


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
