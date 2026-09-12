"""Independent 2026 Payroll tax reconciliation and deployment-readiness packet."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Final
from uuid import UUID

from .contracts import canonical_digest
from .federal_tax_rules_2026 import (
    FLORIDA_SOURCE,
    IRS_15_SOURCE,
    IRS_15T_SOURCE,
    Federal2026TaxRuleProvider,
    FederalComponent,
    FederalTaxContext,
    FilingStatus,
    PayFrequency,
    W4Election,
    florida_state_income_tax_applicability,
)
from .tax_authority import (
    AuthorityRequirement,
    AuthorityResolution,
    PayrollInputDomain,
    TaxDeductionAdmissionState,
)
from .tax_calculation import TaxResponsibility, TaxRuleRequest

RECONCILIATION_VERSION: Final = "payroll.federal-tax-2026-reconciliation.v1"
READINESS_VERSION: Final = "payroll.real-employee-tax-reconciliation-readiness.v1"


@dataclass(frozen=True, slots=True)
class ReferenceCase:
    case_id: str
    source_authority: str
    source_version_year: str
    component: FederalComponent
    gross_wages: Decimal
    context: FederalTaxContext
    expected_result: Decimal
    expected_taxable_basis: Decimal


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    case_id: str
    source_authority: str
    source_version_year: str
    expected_result: Decimal
    acp_result: Decimal
    exact_variance: Decimal
    expected_taxable_basis: Decimal
    acp_taxable_basis: Decimal
    passed: bool
    evidence_digest: str


@dataclass(frozen=True, slots=True)
class RealEmployeeReadinessPacket:
    version: str
    employee_reference: str
    state: str
    prerequisites: tuple[str, ...]
    prohibited_inferences: tuple[str, ...]
    execution_steps: tuple[str, ...]
    packet_digest: str


def _context(
    status: FilingStatus = FilingStatus.SINGLE_OR_MARRIED_FILING_SEPARATELY,
    *,
    step_2: bool = False,
    step_3: str = "0",
    step_4a: str = "0",
    step_4b: str = "0",
    step_4c: str = "0",
    ss_ytd: str = "0",
    medicare_ytd: str = "0",
    pretax_federal: str = "0",
    pretax_fica: str = "0",
) -> FederalTaxContext:
    return FederalTaxContext(
        effective_on=date(2026, 6, 30),
        pay_frequency=PayFrequency.WEEKLY,
        w4=W4Election(
            filing_status=status,
            step_2_checked=step_2,
            step_3_credits=Decimal(step_3),
            step_4a_other_income=Decimal(step_4a),
            step_4b_deductions=Decimal(step_4b),
            step_4c_extra_withholding=Decimal(step_4c),
        ),
        social_security_wages_ytd=Decimal(ss_ytd),
        medicare_wages_ytd=Decimal(medicare_ytd),
        pretax_federal_deductions=Decimal(pretax_federal),
        pretax_fica_deductions=Decimal(pretax_fica),
    )


# Expected amounts below are independently worked from IRS Publication 15-T
# Worksheet 1A / annual schedules and Publication 15 FICA rules. They are data,
# never computed through ACP production rule functions.
REFERENCE_CASES: Final = (
    ReferenceCase(
        "single_weekly",
        "IRS",
        "Publication 15-T (2026)",
        FederalComponent.FEDERAL_INCOME_TAX,
        Decimal(1000),
        _context(),
        Decimal("78.08"),
        Decimal(1000),
    ),
    ReferenceCase(
        "married_filing_jointly_weekly",
        "IRS",
        "Publication 15-T (2026)",
        FederalComponent.FEDERAL_INCOME_TAX,
        Decimal(1500),
        _context(FilingStatus.MARRIED_FILING_JOINTLY),
        Decimal("96.15"),
        Decimal(1500),
    ),
    ReferenceCase(
        "head_of_household_weekly",
        "IRS",
        "Publication 15-T (2026)",
        FederalComponent.FEDERAL_INCOME_TAX,
        Decimal(1300),
        _context(FilingStatus.HEAD_OF_HOUSEHOLD),
        Decimal("93.46"),
        Decimal(1300),
    ),
    ReferenceCase(
        "step_2_off",
        "IRS",
        "Publication 15-T (2026)",
        FederalComponent.FEDERAL_INCOME_TAX,
        Decimal(1000),
        _context(),
        Decimal("78.08"),
        Decimal(1000),
    ),
    ReferenceCase(
        "step_2_on",
        "IRS",
        "Publication 15-T (2026)",
        FederalComponent.FEDERAL_INCOME_TAX,
        Decimal(1000),
        _context(step_2=True),
        Decimal("135.10"),
        Decimal(1000),
    ),
    ReferenceCase(
        "step_3_credit",
        "IRS",
        "Publication 15-T (2026)",
        FederalComponent.FEDERAL_INCOME_TAX,
        Decimal(1000),
        _context(step_3="2600"),
        Decimal("28.08"),
        Decimal(1000),
    ),
    ReferenceCase(
        "step_4a_other_income",
        "IRS",
        "Publication 15-T (2026)",
        FederalComponent.FEDERAL_INCOME_TAX,
        Decimal(1000),
        _context(step_4a="5200"),
        Decimal("90.08"),
        Decimal(1000),
    ),
    ReferenceCase(
        "step_4b_deductions",
        "IRS",
        "Publication 15-T (2026)",
        FederalComponent.FEDERAL_INCOME_TAX,
        Decimal(1000),
        _context(step_4b="5200"),
        Decimal("66.08"),
        Decimal(1000),
    ),
    ReferenceCase(
        "step_4c_extra",
        "IRS",
        "Publication 15-T (2026)",
        FederalComponent.FEDERAL_INCOME_TAX,
        Decimal(1000),
        _context(step_4c="25"),
        Decimal("103.08"),
        Decimal(1000),
    ),
    ReferenceCase(
        "low_wage_zero",
        "IRS",
        "Publication 15-T (2026)",
        FederalComponent.FEDERAL_INCOME_TAX,
        Decimal(100),
        _context(),
        Decimal("0.00"),
        Decimal(100),
    ),
    ReferenceCase(
        "high_wage",
        "IRS",
        "Publication 15-T (2026)",
        FederalComponent.FEDERAL_INCOME_TAX,
        Decimal(20000),
        _context(),
        Decimal("6438.47"),
        Decimal(20000),
    ),
    ReferenceCase(
        "social_security_base_crossing_employee",
        "IRS/SSA",
        "Publication 15 (2026); SSA 2026 CBB",
        FederalComponent.SOCIAL_SECURITY_EMPLOYEE,
        Decimal(1000),
        _context(ss_ytd="184000"),
        Decimal("31.00"),
        Decimal(500),
    ),
    ReferenceCase(
        "social_security_base_crossing_employer",
        "IRS/SSA",
        "Publication 15 (2026); SSA 2026 CBB",
        FederalComponent.SOCIAL_SECURITY_EMPLOYER,
        Decimal(1000),
        _context(ss_ytd="184000"),
        Decimal("31.00"),
        Decimal(500),
    ),
    ReferenceCase(
        "medicare_employee",
        "IRS",
        "Publication 15 (2026)",
        FederalComponent.MEDICARE_EMPLOYEE,
        Decimal(1000),
        _context(),
        Decimal("14.50"),
        Decimal(1000),
    ),
    ReferenceCase(
        "medicare_employer",
        "IRS",
        "Publication 15 (2026)",
        FederalComponent.MEDICARE_EMPLOYER,
        Decimal(1000),
        _context(),
        Decimal("14.50"),
        Decimal(1000),
    ),
    ReferenceCase(
        "additional_medicare_crossing",
        "IRS",
        "Publication 15 (2026)",
        FederalComponent.ADDITIONAL_MEDICARE_EMPLOYEE,
        Decimal(1000),
        _context(medicare_ytd="199750"),
        Decimal("6.75"),
        Decimal(750),
    ),
    ReferenceCase(
        "ytd_social_security_exhausted",
        "IRS/SSA",
        "Publication 15 (2026); SSA 2026 CBB",
        FederalComponent.SOCIAL_SECURITY_EMPLOYEE,
        Decimal(1000),
        _context(ss_ytd="184500"),
        Decimal("0.00"),
        Decimal(0),
    ),
    ReferenceCase(
        "ytd_additional_medicare_prior_payroll",
        "IRS",
        "Publication 15 (2026)",
        FederalComponent.ADDITIONAL_MEDICARE_EMPLOYEE,
        Decimal(1000),
        _context(medicare_ytd="200000"),
        Decimal("9.00"),
        Decimal(1000),
    ),
    ReferenceCase(
        "pretax_federal_reduction",
        "IRS",
        "Publication 15-T (2026)",
        FederalComponent.FEDERAL_INCOME_TAX,
        Decimal(1000),
        _context(pretax_federal="100"),
        Decimal("66.08"),
        Decimal(900),
    ),
    ReferenceCase(
        "pretax_fica_social_security",
        "IRS",
        "Publication 15 (2026)",
        FederalComponent.SOCIAL_SECURITY_EMPLOYEE,
        Decimal(1000),
        _context(pretax_fica="100"),
        Decimal("55.80"),
        Decimal(900),
    ),
    ReferenceCase(
        "pretax_fica_medicare",
        "IRS",
        "Publication 15 (2026)",
        FederalComponent.MEDICARE_EMPLOYEE,
        Decimal(1000),
        _context(pretax_fica="100"),
        Decimal("13.05"),
        Decimal(900),
    ),
    ReferenceCase(
        "minor_unit_half_up_boundary",
        "IRS",
        "Publication 15 (2026)",
        FederalComponent.SOCIAL_SECURITY_EMPLOYEE,
        Decimal("1000.09"),
        _context(),
        Decimal("62.01"),
        Decimal("1000.09"),
    ),
)


def reconcile_2026_reference_cases() -> tuple[ReconciliationResult, ...]:
    return tuple(_reconcile(item) for item in REFERENCE_CASES)


def _reconcile(item: ReferenceCase) -> ReconciliationResult:
    responsibility = {
        FederalComponent.FEDERAL_INCOME_TAX: TaxResponsibility.EMPLOYEE_WITHHOLDING,
        FederalComponent.SOCIAL_SECURITY_EMPLOYEE: TaxResponsibility.EMPLOYEE_PAYROLL_TAX,
        FederalComponent.SOCIAL_SECURITY_EMPLOYER: TaxResponsibility.EMPLOYER_PAYROLL_TAX,
        FederalComponent.MEDICARE_EMPLOYEE: TaxResponsibility.EMPLOYEE_PAYROLL_TAX,
        FederalComponent.MEDICARE_EMPLOYER: TaxResponsibility.EMPLOYER_PAYROLL_TAX,
        FederalComponent.ADDITIONAL_MEDICARE_EMPLOYEE: TaxResponsibility.EMPLOYEE_PAYROLL_TAX,
    }[item.component]
    authority_digest = canonical_digest({"reference_case": item.case_id})
    authority = AuthorityResolution(
        requirement=AuthorityRequirement(
            PayrollInputDomain.TAX, item.component.value, UUID(int=2)
        ),
        state=TaxDeductionAdmissionState.READY,
        authority_id=UUID(int=1),
        authority_digest=authority_digest,
        protected_input_digest=canonical_digest(
            {"synthetic_reference_case": item.case_id}
        ),
        limitations=(),
    )
    output = Federal2026TaxRuleProvider(item.context, item.component).calculate(
        TaxRuleRequest(
            item.component.value,
            responsibility,
            authority,
            "US-FEDERAL",
            item.gross_wages,
            "USD",
            True,
        )
    )
    variance = output.amount - item.expected_result
    passed = variance == 0 and output.taxable_basis == item.expected_taxable_basis
    evidence = {
        "version": RECONCILIATION_VERSION,
        "case": item.case_id,
        "source": item.source_version_year,
        "expected": str(item.expected_result),
        "actual": str(output.amount),
        "variance": str(variance),
        "expected_basis": str(item.expected_taxable_basis),
        "actual_basis": str(output.taxable_basis),
        "passed": passed,
    }
    return ReconciliationResult(
        item.case_id,
        item.source_authority,
        item.source_version_year,
        item.expected_result,
        output.amount,
        variance,
        item.expected_taxable_basis,
        output.taxable_basis,
        passed,
        canonical_digest(evidence),
    )


def validate_florida_reference_case() -> ReconciliationResult:
    state, _ = florida_state_income_tax_applicability(
        work_jurisdiction="US-FL", residence_jurisdiction="US-FL"
    )
    passed = state == "NOT_APPLICABLE"
    evidence = {"source": asdict(FLORIDA_SOURCE), "state": state, "passed": passed}
    return ReconciliationResult(
        "florida_explicit_jurisdiction",
        FLORIDA_SOURCE.source_authority,
        FLORIDA_SOURCE.source_publication_version,
        Decimal(0),
        Decimal(0),
        Decimal(0),
        Decimal(0),
        Decimal(0),
        passed,
        canonical_digest(evidence),
    )


def build_lianne_readiness_packet() -> RealEmployeeReadinessPacket:
    prerequisites = (
        "PR #223 Employee Payroll setup deployed",
        "PR #228 2026 federal tax provider deployed",
        "Payroll protected-envelope encryption keys configured",
        "Lianne identity resolved inside the authorized Company",
        "effective 2026 W-4 election entered and approved",
        "2026 Social Security and Medicare wages YTD entered and approved",
        "prior-payroll coverage and applicable pre-tax deductions entered and approved",
        "explicit work and residence jurisdiction entered and approved",
        "approved compensation, accepted time, and pay period available",
    )
    prohibited = (
        "do not infer any W-4 election from filing history or identity",
        "do not infer missing YTD wages or taxes as zero",
        "do not calculate while readiness is BLOCKED_FOR_PAYROLL",
        "do not transmit Payroll, file/pay tax, post Accounting, or move money",
    )
    steps = (
        "run the Company-scoped Payroll readiness evaluator",
        "confirm Lianne is READY_FOR_PAYROLL with no exact blockers",
        "calculate a non-transmitting candidate using the admitted 2026 rules",
        "independently reconcile component amounts and taxable bases",
        "record source versions, evidence digests, variance, and owner review state",
    )
    body = {
        "version": READINESS_VERSION,
        "employee_reference": "Lianne",
        "prerequisites": prerequisites,
        "prohibited": prohibited,
        "steps": steps,
    }
    return RealEmployeeReadinessPacket(
        READINESS_VERSION,
        "Lianne",
        "BLOCKED_PENDING_AUTHORIZED_REAL_INPUTS",
        prerequisites,
        prohibited,
        steps,
        canonical_digest(body),
    )


OFFICIAL_SOURCE_DIGESTS: Final = (
    IRS_15T_SOURCE.source_sha256,
    IRS_15_SOURCE.source_sha256,
    FLORIDA_SOURCE.source_sha256,
)
