"""Independent cases transcribed from the official 2026 IRS worksheets/tables."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from app.payroll.contracts import canonical_digest
from app.payroll.federal_tax_rules_2026 import (
    FLORIDA_SOURCE,
    IRS_15T_SOURCE,
    Federal2026TaxRuleProvider,
    FederalComponent,
    FederalTaxContext,
    FilingStatus,
    PayFrequency,
    W4Election,
    florida_state_income_tax_applicability,
)
from app.payroll.tax_authority import (
    AuthorityRequirement,
    AuthorityResolution,
    PayrollInputDomain,
    TaxDeductionAdmissionState,
)
from app.payroll.tax_calculation import (
    TaxDeductionCalculationError,
    TaxResponsibility,
    TaxRuleRequest,
)


def context(
    filing_status: FilingStatus = FilingStatus.SINGLE_OR_MARRIED_FILING_SEPARATELY,
    *,
    frequency: PayFrequency = PayFrequency.BIWEEKLY,
    step_2: bool = False,
    step_3: str = "0",
    step_4a: str = "0",
    step_4b: str = "0",
    step_4c: str = "0",
    ss_ytd: str = "0",
    medicare_ytd: str = "0",
) -> FederalTaxContext:
    return FederalTaxContext(
        effective_on=date(2026, 6, 30),
        pay_frequency=frequency,
        w4=W4Election(
            filing_status=filing_status,
            step_2_checked=step_2,
            step_3_credits=Decimal(step_3),
            step_4a_other_income=Decimal(step_4a),
            step_4b_deductions=Decimal(step_4b),
            step_4c_extra_withholding=Decimal(step_4c),
        ),
        social_security_wages_ytd=Decimal(ss_ytd),
        medicare_wages_ytd=Decimal(medicare_ytd),
    )


def request(
    component: FederalComponent,
    gross: str,
    *,
    protected: bool = True,
) -> TaxRuleRequest:
    responsibility = {
        FederalComponent.FEDERAL_INCOME_TAX: TaxResponsibility.EMPLOYEE_WITHHOLDING,
        FederalComponent.SOCIAL_SECURITY_EMPLOYEE: TaxResponsibility.EMPLOYEE_PAYROLL_TAX,
        FederalComponent.SOCIAL_SECURITY_EMPLOYER: TaxResponsibility.EMPLOYER_PAYROLL_TAX,
        FederalComponent.MEDICARE_EMPLOYEE: TaxResponsibility.EMPLOYEE_PAYROLL_TAX,
        FederalComponent.MEDICARE_EMPLOYER: TaxResponsibility.EMPLOYER_PAYROLL_TAX,
        FederalComponent.ADDITIONAL_MEDICARE_EMPLOYEE: TaxResponsibility.EMPLOYEE_PAYROLL_TAX,
    }[component]
    authority = AuthorityResolution(
        requirement=AuthorityRequirement(
            PayrollInputDomain.TAX, component.value, uuid4()
        ),
        state=TaxDeductionAdmissionState.READY,
        authority_id=uuid4(),
        authority_digest=canonical_digest({"official-case": component.value}),
        protected_input_digest=canonical_digest({"w4-ytd-case": component.value})
        if protected
        else None,
        limitations=(),
    )
    return TaxRuleRequest(
        component.value,
        responsibility,
        authority,
        "US-FEDERAL",
        Decimal(gross),
        "USD",
        protected,
    )


def calculate(component: FederalComponent, gross: str, value: FederalTaxContext):
    return Federal2026TaxRuleProvider(value, component).calculate(
        request(component, gross)
    )


def test_publication_15t_single_biweekly_percentage_method() -> None:
    # Worksheet 1A: 2,000*26 - 8,600 = 43,400; 1,240 + 12%*(43,400-19,900); /26.
    assert calculate(
        FederalComponent.FEDERAL_INCOME_TAX, "2000", context()
    ).amount == Decimal("156.15")


def test_publication_15t_step_2_uses_checkbox_schedule() -> None:
    # Worksheet 1A: 2,500*52 = 130,000; 17,966 + 24%*(130,000-121,800); /52.
    value = context(
        FilingStatus.MARRIED_FILING_JOINTLY, frequency=PayFrequency.WEEKLY, step_2=True
    )
    assert calculate(
        FederalComponent.FEDERAL_INCOME_TAX, "2500", value
    ).amount == Decimal("383.35")


def test_publication_15t_head_of_household_all_step_adjustments() -> None:
    # Annual adjusted wages 61,000; annual tentative tax 5,100; /12 - 200 credit + 25 extra.
    value = context(
        FilingStatus.HEAD_OF_HOUSEHOLD,
        frequency=PayFrequency.MONTHLY,
        step_3="2400",
        step_4a="12000",
        step_4b="2400",
        step_4c="25",
    )
    assert calculate(
        FederalComponent.FEDERAL_INCOME_TAX, "5000", value
    ).amount == Decimal("250.00")


def test_publication_15_social_security_wage_base_crossing_both_shares() -> None:
    value = context(ss_ytd="184000")
    employee = calculate(FederalComponent.SOCIAL_SECURITY_EMPLOYEE, "1000", value)
    employer = calculate(FederalComponent.SOCIAL_SECURITY_EMPLOYER, "1000", value)
    assert employee.taxable_basis == employer.taxable_basis == Decimal(500)
    assert employee.amount == employer.amount == Decimal("31.00")


def test_publication_15_medicare_and_additional_medicare_threshold() -> None:
    value = context(medicare_ytd="199800")
    assert calculate(
        FederalComponent.MEDICARE_EMPLOYEE, "500", value
    ).amount == Decimal("7.25")
    assert calculate(
        FederalComponent.MEDICARE_EMPLOYER, "500", value
    ).amount == Decimal("7.25")
    additional = calculate(FederalComponent.ADDITIONAL_MEDICARE_EMPLOYEE, "500", value)
    assert additional.taxable_basis == Decimal(300)
    assert additional.amount == Decimal("2.70")


def test_unchanged_evidence_is_deterministic_and_source_bound() -> None:
    value = context(step_4c="10")
    first = calculate(FederalComponent.FEDERAL_INCOME_TAX, "2000", value)
    second = calculate(FederalComponent.FEDERAL_INCOME_TAX, "2000", value)
    assert first == second
    assert first.evidence_digest == second.evidence_digest
    assert (
        IRS_15T_SOURCE.source_sha256
        == "31b3e2428628e8d2e40f6266c2c8f1b9b0b6ccd24607895f9b3be3d9d306d3fb"
    )


def test_missing_protected_election_evidence_fails_closed() -> None:
    provider = Federal2026TaxRuleProvider(
        context(), FederalComponent.FEDERAL_INCOME_TAX
    )
    with pytest.raises(
        TaxDeductionCalculationError, match="election evidence is missing"
    ):
        provider.calculate(
            request(FederalComponent.FEDERAL_INCOME_TAX, "2000", protected=False)
        )


def test_out_of_effective_date_and_negative_ytd_fail_closed() -> None:
    with pytest.raises(TaxDeductionCalculationError, match="not effective"):
        calculate(
            FederalComponent.FEDERAL_INCOME_TAX,
            "2000",
            replace(context(), effective_on=date(2027, 1, 1)),
        )
    with pytest.raises(TaxDeductionCalculationError, match="cannot be negative"):
        calculate(
            FederalComponent.SOCIAL_SECURITY_EMPLOYEE,
            "2000",
            replace(context(), social_security_wages_ytd=Decimal(-1)),
        )


def test_florida_not_applicable_requires_explicit_jurisdiction_evidence() -> None:
    state, source = florida_state_income_tax_applicability(
        work_jurisdiction="US-FL", residence_jurisdiction="US-FL"
    )
    assert state == "NOT_APPLICABLE"
    assert source == FLORIDA_SOURCE
    with pytest.raises(TaxDeductionCalculationError, match="explicit US-FL"):
        florida_state_income_tax_applicability(
            work_jurisdiction="US-FL", residence_jurisdiction="UNKNOWN"
        )
