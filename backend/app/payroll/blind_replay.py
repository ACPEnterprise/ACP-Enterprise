"""Independent, non-transmitting historical Payroll replay.

This module deliberately separates calculation inputs from a later QBO answer key.
It creates shadow evidence only: no Payroll run, payment, filing, Employee YTD update,
or authoritative Accounting journal is produced here.
"""

from __future__ import annotations

import csv
import html
import io
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Final
from uuid import UUID, uuid4

from app.payroll.contracts import canonical_digest
from app.payroll.federal_tax_rules_2026 import (
    PROVIDER_VERSION,
    Federal2026TaxRuleProvider,
    FederalComponent,
    FederalTaxContext,
    FilingStatus,
    PayFrequency,
    W4Election,
)
from app.payroll.tax_authority import (
    AuthorityRequirement,
    AuthorityResolution,
    PayrollInputDomain,
    TaxDeductionAdmissionState,
)
from app.payroll.tax_calculation import (
    TaxResponsibility,
    TaxRuleRequest,
)

CONTRACT_VERSION: Final = "payroll.blind-replay-input.v1"
ENGINE_VERSION: Final = "payroll.blind-replay-engine.v1"
ANSWER_KEY_VERSION: Final = "payroll.qbo-answer-key.v1"
COMPARISON_VERSION: Final = "payroll.blind-comparison.v1"
MONEY = Decimal("0.01")
HOURS = Decimal("0.0001")


class BlindReplayError(ValueError):
    pass


class CompensationType(StrEnum):
    HOURLY = "hourly"
    SALARY = "salary"


class EmploymentStatus(StrEnum):
    ACTIVE = "active"
    TERMINATED_FINAL_PAY = "terminated_final_pay"


class AuthorityClassification(StrEnum):
    VERIFIED = "VERIFIED"
    SUPPORTED = "SUPPORTED"


class DeductionTreatment(StrEnum):
    PRE_TAX_FEDERAL_AND_FICA = "pre_tax_federal_and_fica"
    PRE_TAX_FEDERAL_ONLY = "pre_tax_federal_only"
    POST_TAX = "post_tax"


class VarianceClassification(StrEnum):
    EXACT_MATCH = "EXACT MATCH"
    ROUNDING = "ROUNDING"
    INPUT_DIFFERENCE = "INPUT DIFFERENCE"
    CONFIGURATION_DIFFERENCE = "CONFIGURATION DIFFERENCE"
    YTD_BASIS_DIFFERENCE = "YTD BASIS DIFFERENCE"
    TAX_TABLE_DIFFERENCE = "TAX TABLE DIFFERENCE"
    QBO_SOURCE_ISSUE = "QBO SOURCE ISSUE"
    TWELVEHATS_ENGINE_DEFECT = "TWELVEHATS ENGINE DEFECT"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class SourceProvenance:
    source_id: str
    effective_date: date
    evidence_digest: str
    authority_classification: AuthorityClassification

    def validate(self) -> None:
        if not self.source_id.strip() or len(self.evidence_digest) != 64:
            raise BlindReplayError("complete source provenance is required")


@dataclass(frozen=True, slots=True)
class DeductionInput:
    code: str
    amount: Decimal
    treatment: DeductionTreatment
    employer_contribution: Decimal
    provenance: SourceProvenance


@dataclass(frozen=True, slots=True)
class OpeningYTD:
    gross_wages: Decimal
    fit_taxable_wages: Decimal
    social_security_wages: Decimal
    medicare_wages: Decimal
    fit_withheld: Decimal
    social_security_withheld: Decimal
    medicare_withheld: Decimal
    futa_wages: Decimal
    suta_wages: Decimal
    state_local_bases: Mapping[str, Decimal]
    provenance: SourceProvenance


@dataclass(frozen=True, slots=True)
class EmployeeReplayInput:
    employee_id: UUID
    display_label: str
    employment_status: EmploymentStatus
    compensation_type: CompensationType
    compensation_rate: Decimal
    compensation_effective_start: date
    compensation_effective_end: date | None
    regular_hours: Decimal
    overtime_hours: Decimal
    other_paid_hours: Decimal
    overtime_multiplier: Decimal
    commission: Decimal
    bonus: Decimal
    other_authorized_earnings: Decimal
    reimbursement: Decimal
    filing_status: FilingStatus
    w4_step_2: bool
    w4_step_3: Decimal
    w4_step_4a: Decimal
    w4_step_4b: Decimal
    w4_step_4c: Decimal
    fica_applicable: bool
    work_state: str
    residence_state: str
    local_jurisdiction: str | None
    state_income_tax: Decimal
    local_income_tax: Decimal
    deductions: tuple[DeductionInput, ...]
    opening_ytd: OpeningYTD
    futa_rate: Decimal
    futa_wage_base: Decimal
    suta_rate: Decimal
    suta_wage_base: Decimal
    compensation_provenance: SourceProvenance
    time_provenance: SourceProvenance
    tax_provenance: SourceProvenance
    jurisdiction_provenance: SourceProvenance


@dataclass(frozen=True, slots=True)
class BlindReplayInput:
    company_id: UUID
    period_start: date
    period_end: date
    pay_date: date
    pay_frequency: PayFrequency
    employees: tuple[EmployeeReplayInput, ...]
    packet_provenance: SourceProvenance
    contract_version: str = CONTRACT_VERSION

    def validate(self) -> None:
        if self.contract_version != CONTRACT_VERSION:
            raise BlindReplayError("unsupported blind replay contract")
        if self.period_end < self.period_start or self.pay_date < self.period_end:
            raise BlindReplayError("invalid Payroll period or pay date")
        if not self.employees:
            raise BlindReplayError("at least one Employee input is required")
        if len({item.employee_id for item in self.employees}) != len(self.employees):
            raise BlindReplayError("duplicate Employee input")
        self.packet_provenance.validate()
        for item in self.employees:
            _validate_employee(item, self.period_start, self.period_end)


def parse_blind_replay_input(payload: Mapping[str, object]) -> BlindReplayInput:
    """Parse a protected owner packet without converting absent values to zero."""

    def required(source: Mapping[str, object], key: str) -> object:
        if key not in source or source[key] is None or source[key] == "":
            raise BlindReplayError(f"blind replay input is missing {key}")
        return source[key]

    def decimal(source: Mapping[str, object], key: str) -> Decimal:
        try:
            return Decimal(str(required(source, key)))
        except BlindReplayError:
            raise
        except Exception as error:
            raise BlindReplayError(f"blind replay input {key} is invalid") from error

    def boolean(source: Mapping[str, object], key: str) -> bool:
        value = required(source, key)
        if not isinstance(value, bool):
            raise BlindReplayError(f"blind replay input {key} must be boolean")
        return value

    def source(value: object, label: str) -> SourceProvenance:
        if not isinstance(value, Mapping):
            raise BlindReplayError(f"blind replay input is missing {label}")
        try:
            return SourceProvenance(
                str(required(value, "source_id")),
                date.fromisoformat(str(required(value, "effective_date"))),
                str(required(value, "evidence_digest")),
                AuthorityClassification(
                    str(required(value, "authority_classification"))
                ),
            )
        except ValueError as error:
            raise BlindReplayError(f"blind replay input {label} is invalid") from error

    employee_values = required(payload, "employees")
    if not isinstance(employee_values, list):
        raise BlindReplayError("blind replay employees must be a list")
    employees: list[EmployeeReplayInput] = []
    for raw in employee_values:
        if not isinstance(raw, Mapping):
            raise BlindReplayError("blind replay Employee input must be an object")
        forbidden = {
            "gross_pay",
            "federal_withholding",
            "employee_social_security",
            "employee_medicare",
            "net_pay",
            "employer_taxes",
            "payroll_journal",
            "quickbooks_results",
            "qbo_results",
        }.intersection(raw)
        if forbidden:
            raise BlindReplayError(
                "selected-period calculated outputs are forbidden before freeze: "
                + ",".join(sorted(forbidden))
            )
        opening_raw = required(raw, "opening_ytd")
        if not isinstance(opening_raw, Mapping):
            raise BlindReplayError("blind replay opening_ytd must be an object")
        state_bases = required(opening_raw, "state_local_bases")
        if not isinstance(state_bases, Mapping):
            raise BlindReplayError("opening YTD state/local bases must be an object")
        deductions_raw = required(raw, "deductions")
        if not isinstance(deductions_raw, list):
            raise BlindReplayError("deductions must be an explicit list")
        deductions = []
        for deduction in deductions_raw:
            if not isinstance(deduction, Mapping):
                raise BlindReplayError("deduction input must be an object")
            deductions.append(
                DeductionInput(
                    str(required(deduction, "code")),
                    decimal(deduction, "amount"),
                    DeductionTreatment(str(required(deduction, "treatment"))),
                    decimal(deduction, "employer_contribution"),
                    source(required(deduction, "provenance"), "deduction.provenance"),
                )
            )
        employees.append(
            EmployeeReplayInput(
                UUID(str(required(raw, "employee_id"))),
                str(required(raw, "display_label")),
                EmploymentStatus(str(required(raw, "employment_status"))),
                CompensationType(str(required(raw, "compensation_type"))),
                decimal(raw, "compensation_rate"),
                date.fromisoformat(str(required(raw, "compensation_effective_start"))),
                date.fromisoformat(str(raw["compensation_effective_end"]))
                if raw.get("compensation_effective_end")
                else None,
                decimal(raw, "regular_hours"),
                decimal(raw, "overtime_hours"),
                decimal(raw, "other_paid_hours"),
                decimal(raw, "overtime_multiplier"),
                decimal(raw, "commission"),
                decimal(raw, "bonus"),
                decimal(raw, "other_authorized_earnings"),
                decimal(raw, "reimbursement"),
                FilingStatus(str(required(raw, "filing_status"))),
                boolean(raw, "w4_step_2"),
                decimal(raw, "w4_step_3"),
                decimal(raw, "w4_step_4a"),
                decimal(raw, "w4_step_4b"),
                decimal(raw, "w4_step_4c"),
                boolean(raw, "fica_applicable"),
                str(required(raw, "work_state")),
                str(required(raw, "residence_state")),
                str(raw["local_jurisdiction"])
                if raw.get("local_jurisdiction")
                else None,
                decimal(raw, "state_income_tax"),
                decimal(raw, "local_income_tax"),
                tuple(deductions),
                OpeningYTD(
                    decimal(opening_raw, "gross_wages"),
                    decimal(opening_raw, "fit_taxable_wages"),
                    decimal(opening_raw, "social_security_wages"),
                    decimal(opening_raw, "medicare_wages"),
                    decimal(opening_raw, "fit_withheld"),
                    decimal(opening_raw, "social_security_withheld"),
                    decimal(opening_raw, "medicare_withheld"),
                    decimal(opening_raw, "futa_wages"),
                    decimal(opening_raw, "suta_wages"),
                    {
                        str(key): Decimal(str(value))
                        for key, value in state_bases.items()
                    },
                    source(
                        required(opening_raw, "provenance"), "opening_ytd.provenance"
                    ),
                ),
                decimal(raw, "futa_rate"),
                decimal(raw, "futa_wage_base"),
                decimal(raw, "suta_rate"),
                decimal(raw, "suta_wage_base"),
                source(
                    required(raw, "compensation_provenance"), "compensation_provenance"
                ),
                source(required(raw, "time_provenance"), "time_provenance"),
                source(required(raw, "tax_provenance"), "tax_provenance"),
                source(
                    required(raw, "jurisdiction_provenance"), "jurisdiction_provenance"
                ),
            )
        )
    result = BlindReplayInput(
        UUID(str(required(payload, "company_id"))),
        date.fromisoformat(str(required(payload, "period_start"))),
        date.fromisoformat(str(required(payload, "period_end"))),
        date.fromisoformat(str(required(payload, "pay_date"))),
        PayFrequency(str(required(payload, "pay_frequency"))),
        tuple(employees),
        source(required(payload, "packet_provenance"), "packet_provenance"),
        str(payload.get("contract_version", CONTRACT_VERSION)),
    )
    result.validate()
    return result


@dataclass(frozen=True, slots=True)
class ShadowJournal:
    wage_expense: Decimal
    reimbursement_expense: Decimal
    employer_payroll_tax_expense: Decimal
    employer_benefit_expense: Decimal
    fit_payable: Decimal
    social_security_payable: Decimal
    medicare_payable: Decimal
    unemployment_payable: Decimal
    deduction_benefit_liabilities: Decimal
    net_payroll_clearing: Decimal
    debits: Decimal
    credits: Decimal
    accounting_delta: Decimal


@dataclass(frozen=True, slots=True)
class EmployeeShadowResult:
    employee_id: UUID
    display_label: str
    regular_pay: Decimal
    overtime_pay: Decimal
    commission: Decimal
    bonus: Decimal
    other_earnings: Decimal
    reimbursement: Decimal
    gross_pay: Decimal
    fit_taxable_wages: Decimal
    social_security_taxable_wages: Decimal
    medicare_taxable_wages: Decimal
    federal_withholding: Decimal
    employee_social_security: Decimal
    employee_medicare: Decimal
    additional_medicare: Decimal
    state_local_taxes: Decimal
    pretax_deductions: Decimal
    posttax_deductions: Decimal
    net_pay: Decimal
    employer_social_security: Decimal
    employer_medicare: Decimal
    futa: Decimal
    suta: Decimal
    employer_contributions: Decimal
    total_employer_cost: Decimal
    journal: ShadowJournal
    result_digest: str


@dataclass(frozen=True, slots=True)
class FrozenShadowPayroll:
    calculation_id: UUID
    company_id: UUID
    period_start: date
    period_end: date
    pay_date: date
    input_digest: str
    engine_version: str
    engine_sha: str
    tax_table_version: str
    calculated_at: datetime
    employees: tuple[EmployeeShadowResult, ...]
    result_digest: str
    frozen_before_qbo_reveal: bool = True


@dataclass(frozen=True, slots=True)
class AnswerKeyEmployee:
    employee_key: str
    pay_date: date
    regular_pay: Decimal
    overtime_pay: Decimal
    commission: Decimal
    bonus: Decimal
    gross_pay: Decimal
    fit_taxable_wages: Decimal
    social_security_taxable_wages: Decimal
    medicare_taxable_wages: Decimal
    federal_withholding: Decimal
    employee_social_security: Decimal
    employee_medicare: Decimal
    other_taxes: Decimal
    pretax_deductions: Decimal
    posttax_deductions: Decimal
    net_pay: Decimal
    employer_social_security: Decimal
    employer_medicare: Decimal
    unemployment: Decimal
    employer_contributions: Decimal
    total_employer_cost: Decimal


@dataclass(frozen=True, slots=True)
class QBOAnswerKey:
    answer_key_id: UUID
    company_id: UUID
    source_file_digest: str
    report_type: str
    imported_at: datetime
    employees: tuple[AnswerKeyEmployee, ...]
    answer_key_digest: str


@dataclass(frozen=True, slots=True)
class VarianceLine:
    employee_key: str
    component: str
    twelvehats: Decimal
    quickbooks: Decimal
    variance: Decimal
    classification: VarianceClassification
    explanation: str


@dataclass(frozen=True, slots=True)
class BlindComparison:
    calculation_id: UUID
    answer_key_id: UUID
    lines: tuple[VarianceLine, ...]
    unexplained_count: int
    comparison_digest: str


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _nonnegative(name: str, value: Decimal) -> None:
    if value < 0:
        raise BlindReplayError(f"{name} cannot be negative")


def _validate_employee(item: EmployeeReplayInput, start: date, end: date) -> None:
    if not item.display_label.strip():
        raise BlindReplayError("Employee display label is required")
    if item.compensation_effective_start > start or (
        item.compensation_effective_end is not None
        and item.compensation_effective_end <= end
    ):
        raise BlindReplayError("compensation is not effective for the full period")
    for source in (
        item.compensation_provenance,
        item.time_provenance,
        item.tax_provenance,
        item.jurisdiction_provenance,
        item.opening_ytd.provenance,
    ):
        source.validate()
    if not item.work_state or not item.residence_state:
        raise BlindReplayError("explicit work and residence jurisdictions are required")
    for name in [
        "compensation_rate",
        "regular_hours",
        "overtime_hours",
        "other_paid_hours",
        "commission",
        "bonus",
        "other_authorized_earnings",
        "reimbursement",
        "w4_step_3",
        "w4_step_4a",
        "w4_step_4b",
        "w4_step_4c",
        "state_income_tax",
        "local_income_tax",
        "futa_rate",
        "futa_wage_base",
        "suta_rate",
        "suta_wage_base",
    ]:
        _nonnegative(name, getattr(item, name))
    if item.overtime_multiplier < 1:
        raise BlindReplayError("overtime multiplier must be at least one")
    if item.compensation_type is CompensationType.SALARY and (
        item.overtime_hours or item.regular_hours
    ):
        raise BlindReplayError("salary input must not silently use hourly time")
    if not item.fica_applicable and (
        item.opening_ytd.social_security_wages or item.opening_ytd.medicare_wages
    ):
        raise BlindReplayError(
            "FICA-exempt input conflicts with opening FICA wage bases"
        )
    for deduction in item.deductions:
        deduction.provenance.validate()
        _nonnegative("deduction amount", deduction.amount)
        _nonnegative("employer contribution", deduction.employer_contribution)
    for name, value in asdict(item.opening_ytd).items():
        if isinstance(value, Decimal):
            _nonnegative(f"opening YTD {name}", value)


def _tax_request(
    employee_id: UUID,
    component: FederalComponent,
    taxable_basis: Decimal,
    evidence_digest: str,
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
        AuthorityRequirement(PayrollInputDomain.TAX, component.value, employee_id),
        TaxDeductionAdmissionState.READY,
        uuid4(),
        evidence_digest,
        evidence_digest,
        (),
    )
    return TaxRuleRequest(
        component.value,
        responsibility,
        authority,
        "US-FEDERAL",
        taxable_basis,
        "USD",
        True,
    )


def calculate_shadow_payroll(
    packet: BlindReplayInput,
    *,
    engine_sha: str,
    calculated_at: datetime | None = None,
) -> FrozenShadowPayroll:
    """Calculate and freeze an independent result using no QBO output."""
    packet.validate()
    if len(engine_sha) != 40:
        raise BlindReplayError("full calculation engine SHA is required")
    when = calculated_at or datetime.now(timezone.utc)
    results = tuple(_calculate_employee(packet, item) for item in packet.employees)
    input_digest = canonical_digest(asdict(packet))
    body = {
        "company_id": str(packet.company_id),
        "period_start": packet.period_start,
        "period_end": packet.period_end,
        "pay_date": packet.pay_date,
        "input_digest": input_digest,
        "engine_version": ENGINE_VERSION,
        "engine_sha": engine_sha,
        "tax_table_version": PROVIDER_VERSION,
        "calculated_at": when,
        "employees": [asdict(item) for item in results],
        "frozen_before_qbo_reveal": True,
    }
    return FrozenShadowPayroll(
        uuid4(),
        packet.company_id,
        packet.period_start,
        packet.period_end,
        packet.pay_date,
        input_digest,
        ENGINE_VERSION,
        engine_sha,
        PROVIDER_VERSION,
        when,
        results,
        canonical_digest(body),
        True,
    )


def verify_frozen_result(value: FrozenShadowPayroll) -> None:
    body = {
        "company_id": str(value.company_id),
        "period_start": value.period_start,
        "period_end": value.period_end,
        "pay_date": value.pay_date,
        "input_digest": value.input_digest,
        "engine_version": value.engine_version,
        "engine_sha": value.engine_sha,
        "tax_table_version": value.tax_table_version,
        "calculated_at": value.calculated_at,
        "employees": [asdict(item) for item in value.employees],
        "frozen_before_qbo_reveal": value.frozen_before_qbo_reveal,
    }
    if canonical_digest(body) != value.result_digest:
        raise BlindReplayError("frozen shadow result digest is invalid")


def _calculate_employee(
    packet: BlindReplayInput, item: EmployeeReplayInput
) -> EmployeeShadowResult:
    periods = {
        PayFrequency.WEEKLY: Decimal(52),
        PayFrequency.BIWEEKLY: Decimal(26),
        PayFrequency.SEMIMONTHLY: Decimal(24),
        PayFrequency.MONTHLY: Decimal(12),
        PayFrequency.QUARTERLY: Decimal(4),
        PayFrequency.SEMIANNUALLY: Decimal(2),
        PayFrequency.ANNUALLY: Decimal(1),
    }[packet.pay_frequency]
    if item.compensation_type is CompensationType.HOURLY:
        regular = _money(
            item.compensation_rate * (item.regular_hours + item.other_paid_hours)
        )
        overtime = _money(
            item.compensation_rate * item.overtime_multiplier * item.overtime_hours
        )
    else:
        regular = _money(item.compensation_rate / periods)
        overtime = Decimal("0.00")
    gross = _money(
        regular
        + overtime
        + item.commission
        + item.bonus
        + item.other_authorized_earnings
    )
    pretax_fit = sum(
        (
            value.amount
            for value in item.deductions
            if value.treatment is not DeductionTreatment.POST_TAX
        ),
        Decimal(0),
    )
    pretax_fica = sum(
        (
            value.amount
            for value in item.deductions
            if value.treatment is DeductionTreatment.PRE_TAX_FEDERAL_AND_FICA
        ),
        Decimal(0),
    )
    posttax = sum(
        (
            value.amount
            for value in item.deductions
            if value.treatment is DeductionTreatment.POST_TAX
        ),
        Decimal(0),
    )
    employer_contributions = sum(
        (value.employer_contribution for value in item.deductions), Decimal(0)
    )
    context = FederalTaxContext(
        packet.pay_date,
        packet.pay_frequency,
        W4Election(
            item.filing_status,
            item.w4_step_2,
            item.w4_step_3,
            item.w4_step_4a,
            item.w4_step_4b,
            item.w4_step_4c,
        ),
        item.opening_ytd.social_security_wages,
        item.opening_ytd.medicare_wages,
        pretax_fit,
        pretax_fica,
    )
    values: dict[FederalComponent, Decimal] = {}
    bases: dict[FederalComponent, Decimal] = {}
    for component in FederalComponent:
        if (
            not item.fica_applicable
            and component is not FederalComponent.FEDERAL_INCOME_TAX
        ):
            values[component] = bases[component] = Decimal("0.00")
            continue
        output = Federal2026TaxRuleProvider(context, component).calculate(
            _tax_request(
                item.employee_id, component, gross, item.tax_provenance.evidence_digest
            )
        )
        values[component] = output.amount
        bases[component] = output.taxable_basis
    fit = values[FederalComponent.FEDERAL_INCOME_TAX]
    ss_employee = values[FederalComponent.SOCIAL_SECURITY_EMPLOYEE]
    ss_employer = values[FederalComponent.SOCIAL_SECURITY_EMPLOYER]
    medicare_employee = values[FederalComponent.MEDICARE_EMPLOYEE]
    medicare_employer = values[FederalComponent.MEDICARE_EMPLOYER]
    additional_medicare = values[FederalComponent.ADDITIONAL_MEDICARE_EMPLOYEE]
    futa_basis = min(
        gross,
        max(Decimal(0), item.futa_wage_base - item.opening_ytd.futa_wages),
    )
    suta_basis = min(
        gross,
        max(Decimal(0), item.suta_wage_base - item.opening_ytd.suta_wages),
    )
    futa = _money(futa_basis * item.futa_rate)
    suta = _money(suta_basis * item.suta_rate)
    state_local = _money(item.state_income_tax + item.local_income_tax)
    net = _money(
        gross
        + item.reimbursement
        - fit
        - ss_employee
        - medicare_employee
        - additional_medicare
        - state_local
        - pretax_fit
        - posttax
    )
    employer_taxes = _money(ss_employer + medicare_employer + futa + suta)
    total_cost = _money(
        gross + item.reimbursement + employer_taxes + employer_contributions
    )
    journal = _journal(
        gross=gross,
        reimbursement=item.reimbursement,
        fit=fit,
        ss_employee=ss_employee,
        ss_employer=ss_employer,
        medicare_employee=medicare_employee + additional_medicare,
        medicare_employer=medicare_employer,
        state_local=state_local,
        unemployment=futa + suta,
        deductions=pretax_fit + posttax,
        employer_contributions=employer_contributions,
        net=net,
    )
    payload = {
        "employee_id": str(item.employee_id),
        "regular_pay": regular,
        "overtime_pay": overtime,
        "gross_pay": gross,
        "net_pay": net,
        "journal": asdict(journal),
    }
    return EmployeeShadowResult(
        item.employee_id,
        item.display_label,
        regular,
        overtime,
        _money(item.commission),
        _money(item.bonus),
        _money(item.other_authorized_earnings),
        _money(item.reimbursement),
        gross,
        bases[FederalComponent.FEDERAL_INCOME_TAX],
        bases[FederalComponent.SOCIAL_SECURITY_EMPLOYEE],
        bases[FederalComponent.MEDICARE_EMPLOYEE],
        fit,
        ss_employee,
        medicare_employee,
        additional_medicare,
        state_local,
        _money(pretax_fit),
        _money(posttax),
        net,
        ss_employer,
        medicare_employer,
        futa,
        suta,
        _money(employer_contributions),
        total_cost,
        journal,
        canonical_digest(payload),
    )


def _journal(**value: Decimal) -> ShadowJournal:
    employer_tax = _money(
        value["ss_employer"] + value["medicare_employer"] + value["unemployment"]
    )
    debits = _money(
        value["gross"]
        + value["reimbursement"]
        + employer_tax
        + value["employer_contributions"]
    )
    credits = _money(
        value["fit"]
        + value["ss_employee"]
        + value["ss_employer"]
        + value["medicare_employee"]
        + value["medicare_employer"]
        + value["state_local"]
        + value["unemployment"]
        + value["deductions"]
        + value["employer_contributions"]
        + value["net"]
    )
    return ShadowJournal(
        value["gross"],
        value["reimbursement"],
        employer_tax,
        value["employer_contributions"],
        value["fit"],
        _money(value["ss_employee"] + value["ss_employer"]),
        _money(value["medicare_employee"] + value["medicare_employer"]),
        _money(value["state_local"] + value["unemployment"]),
        _money(value["deductions"] + value["employer_contributions"]),
        value["net"],
        debits,
        credits,
        _money(debits - credits),
    )


_ALIASES: Final = {
    "employee_key": ("employee", "employee name", "employee_key"),
    "pay_date": ("pay date", "paycheck date", "pay_date"),
    "regular_pay": ("regular pay", "regular wages", "regular_pay"),
    "overtime_pay": ("overtime", "overtime pay", "overtime_pay"),
    "commission": ("commission",),
    "bonus": ("bonus",),
    "gross_pay": ("gross pay", "total gross pay", "gross_pay"),
    "fit_taxable_wages": ("fit taxable wages", "federal taxable wages"),
    "social_security_taxable_wages": ("social security wages", "ss taxable wages"),
    "medicare_taxable_wages": ("medicare wages",),
    "federal_withholding": ("federal withholding", "federal income tax"),
    "employee_social_security": ("employee social security", "social security"),
    "employee_medicare": ("employee medicare", "medicare"),
    "other_taxes": ("other taxes", "state and local taxes"),
    "pretax_deductions": ("pre-tax deductions", "pretax deductions"),
    "posttax_deductions": ("post-tax deductions", "posttax deductions"),
    "net_pay": ("net pay",),
    "employer_social_security": ("employer social security",),
    "employer_medicare": ("employer medicare",),
    "unemployment": ("unemployment", "futa/suta"),
    "employer_contributions": ("employer contributions",),
    "total_employer_cost": ("total employer cost", "total payroll cost"),
}


def import_qbo_answer_key_csv(
    payload: bytes,
    *,
    company_id: UUID,
    report_type: str,
    frozen_result: FrozenShadowPayroll | None,
) -> QBOAnswerKey:
    """Normalize a read-only export, but only after a shadow result is frozen."""
    if frozen_result is None or not frozen_result.frozen_before_qbo_reveal:
        raise BlindReplayError("QBO answer key cannot be revealed before shadow freeze")
    verify_frozen_result(frozen_result)
    if frozen_result.company_id != company_id:
        raise BlindReplayError("answer key Company does not match frozen calculation")
    source_digest = canonical_digest(payload.hex())
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
    rows = tuple(reader)
    if not rows:
        raise BlindReplayError("QBO answer key export is empty")
    normalized = tuple(_answer_row(row) for row in rows)
    identities = {(item.employee_key.casefold(), item.pay_date) for item in normalized}
    if len(identities) != len(normalized):
        raise BlindReplayError("duplicate Employee/paycheck answer-key record")
    body = {
        "version": ANSWER_KEY_VERSION,
        "company_id": str(company_id),
        "source_file_digest": source_digest,
        "report_type": report_type,
        "employees": [asdict(item) for item in normalized],
    }
    return QBOAnswerKey(
        uuid4(),
        company_id,
        source_digest,
        report_type,
        datetime.now(timezone.utc),
        normalized,
        canonical_digest(body),
    )


def import_qbo_answer_key_reports(
    reports: Iterable[tuple[str, bytes]],
    *,
    company_id: UUID,
    frozen_result: FrozenShadowPayroll | None,
) -> QBOAnswerKey:
    """Merge complementary read-only QBO reports by Employee and pay date."""
    if frozen_result is None or not frozen_result.frozen_before_qbo_reveal:
        raise BlindReplayError("QBO answer key cannot be revealed before shadow freeze")
    verify_frozen_result(frozen_result)
    combined: dict[tuple[str, str], dict[str, str]] = {}
    sources: list[dict[str, str]] = []
    names: list[str] = []
    for report_type, payload in reports:
        names.append(report_type)
        sources.append(
            {"report_type": report_type, "digest": canonical_digest(payload.hex())}
        )
        for row in csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))):
            lowered = {
                key.strip().casefold(): (value or "").strip()
                for key, value in row.items()
            }
            employee_key = next(
                (
                    lowered.get(alias, "")
                    for alias in _ALIASES["employee_key"]
                    if lowered.get(alias)
                ),
                "",
            )
            pay_date = next(
                (
                    lowered.get(alias, "")
                    for alias in _ALIASES["pay_date"]
                    if lowered.get(alias)
                ),
                "",
            )
            if not employee_key or not pay_date:
                raise BlindReplayError(
                    "every QBO report row requires Employee and pay date"
                )
            identity = (employee_key.casefold(), pay_date)
            target = combined.setdefault(
                identity, {"employee": employee_key, "pay date": pay_date}
            )
            for key, value in lowered.items():
                if (
                    not value
                    or key in _ALIASES["employee_key"]
                    or key in _ALIASES["pay_date"]
                ):
                    continue
                prior = target.get(key)
                if prior is not None and prior != value:
                    raise BlindReplayError(
                        f"conflicting QBO report value for {employee_key}:{key}"
                    )
                target[key] = value
    if not combined:
        raise BlindReplayError("QBO answer-key report set is empty")
    normalized = tuple(_answer_row(row) for row in combined.values())
    source_digest = canonical_digest(sources)
    report_type = " + ".join(sorted(set(names)))
    body = {
        "version": ANSWER_KEY_VERSION,
        "company_id": str(company_id),
        "source_file_digest": source_digest,
        "report_type": report_type,
        "employees": [asdict(item) for item in normalized],
    }
    return QBOAnswerKey(
        uuid4(),
        company_id,
        source_digest,
        report_type,
        datetime.now(timezone.utc),
        normalized,
        canonical_digest(body),
    )


def _answer_row(row: Mapping[str, str]) -> AnswerKeyEmployee:
    lowered = {
        key.strip().casefold(): (value or "").strip() for key, value in row.items()
    }

    def field(name: str) -> str:
        for alias in _ALIASES[name]:
            if alias in lowered and lowered[alias] != "":
                return lowered[alias]
        raise BlindReplayError(f"QBO answer key is missing {name}")

    def amount(name: str) -> Decimal:
        try:
            return _money(Decimal(field(name).replace("$", "").replace(",", "")))
        except Exception as error:
            raise BlindReplayError(f"QBO answer key {name} is invalid") from error

    return AnswerKeyEmployee(
        field("employee_key"),
        date.fromisoformat(field("pay_date")),
        *(amount(name) for name in tuple(_ALIASES)[2:]),
    )


_COMPARISON_FIELDS: Final = (
    "regular_pay",
    "overtime_pay",
    "commission",
    "bonus",
    "gross_pay",
    "fit_taxable_wages",
    "social_security_taxable_wages",
    "medicare_taxable_wages",
    "federal_withholding",
    "employee_social_security",
    "employee_medicare",
    "pretax_deductions",
    "posttax_deductions",
    "net_pay",
    "employer_social_security",
    "employer_medicare",
    "unemployment",
    "employer_contributions",
    "total_employer_cost",
)


def compare_frozen_to_qbo(
    frozen: FrozenShadowPayroll,
    answer_key: QBOAnswerKey,
    *,
    reviewed_classifications: Mapping[
        tuple[str, str], tuple[VarianceClassification, str]
    ]
    | None = None,
) -> BlindComparison:
    if (
        not frozen.frozen_before_qbo_reveal
        or frozen.company_id != answer_key.company_id
    ):
        raise BlindReplayError("frozen calculation and answer key boundary is invalid")
    verify_frozen_result(frozen)
    answer_body = {
        "version": ANSWER_KEY_VERSION,
        "company_id": str(answer_key.company_id),
        "source_file_digest": answer_key.source_file_digest,
        "report_type": answer_key.report_type,
        "employees": [asdict(item) for item in answer_key.employees],
    }
    if canonical_digest(answer_body) != answer_key.answer_key_digest:
        raise BlindReplayError("QBO answer-key digest is invalid")
    qbo = {item.employee_key.casefold(): item for item in answer_key.employees}
    if len(qbo) != len(answer_key.employees):
        raise BlindReplayError("duplicate answer-key Employee")
    lines: list[VarianceLine] = []
    for result in frozen.employees:
        expected = qbo.get(result.display_label.casefold())
        if expected is None:
            raise BlindReplayError(
                f"answer key is missing Employee {result.display_label}"
            )
        if expected.pay_date != frozen.pay_date:
            raise BlindReplayError(
                "answer-key pay date differs from frozen calculation"
            )
        for component in _COMPARISON_FIELDS:
            actual_value = (
                result.futa + result.suta
                if component == "unemployment"
                else getattr(result, component)
            )
            expected_value = getattr(expected, component)
            variance = _money(actual_value - expected_value)
            if variance == 0:
                classification = VarianceClassification.EXACT_MATCH
                explanation = "Exact component match."
            elif abs(variance) <= Decimal("0.01"):
                classification = VarianceClassification.ROUNDING
                explanation = (
                    "Difference is within one cent; verify provider rounding order."
                )
            else:
                reviewed = (reviewed_classifications or {}).get(
                    (result.display_label, component)
                )
                classification, explanation = reviewed or (
                    VarianceClassification.UNRESOLVED,
                    "Material difference requires input, YTD, configuration, or tax-table review.",
                )
                if classification in {
                    VarianceClassification.EXACT_MATCH,
                    VarianceClassification.ROUNDING,
                }:
                    raise BlindReplayError(
                        "material variance cannot be classified as an exact or rounding match"
                    )
            lines.append(
                VarianceLine(
                    result.display_label,
                    component,
                    actual_value,
                    expected_value,
                    variance,
                    classification,
                    explanation,
                )
            )
    body = {
        "version": COMPARISON_VERSION,
        "calculation_id": str(frozen.calculation_id),
        "answer_key_id": str(answer_key.answer_key_id),
        "lines": [asdict(item) for item in lines],
    }
    return BlindComparison(
        frozen.calculation_id,
        answer_key.answer_key_id,
        tuple(lines),
        sum(item.classification is VarianceClassification.UNRESOLVED for item in lines),
        canonical_digest(body),
    )


def owner_comparison_html(comparison: BlindComparison) -> str:
    """Render an owner-readable side-by-side report; differing rows are highlighted."""
    rows = []
    for line in comparison.lines:
        css = ' class="difference"' if line.variance else ""
        rows.append(
            f"<tr{css}><td>{html.escape(line.employee_key)}</td>"
            f"<td>{html.escape(line.component.replace('_', ' ').title())}</td>"
            f"<td>${line.twelvehats:,.2f}</td><td>${line.quickbooks:,.2f}</td>"
            f"<td>${line.variance:,.2f}</td><td>{html.escape(line.classification.value)}</td>"
            f"<td>{html.escape(line.explanation)}</td></tr>"
        )
    return (
        '<!doctype html><html><head><meta charset="utf-8"><title>Blind Payroll Comparison</title>'
        "<style>body{font-family:system-ui;margin:2rem}table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #bbb;padding:.45rem;text-align:right}th:first-child,td:first-child,"
        "th:nth-child(2),td:nth-child(2),th:last-child,td:last-child{text-align:left}"
        ".difference{background:#fff2cc}</style></head><body>"
        "<h1>TwelveHats Shadow Payroll vs QuickBooks Historical Payroll</h1>"
        "<p>QuickBooks values were admitted only after the TwelveHats result was frozen.</p>"
        "<table><thead><tr><th>Employee</th><th>Component</th><th>TwelveHats</th>"
        "<th>QuickBooks</th><th>Variance</th><th>Classification</th><th>Explanation</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></body></html>"
    )


def readiness_missing_fields(
    packet: BlindReplayInput | None,
) -> dict[str, tuple[str, ...]]:
    """Return exact missing input fields without projecting protected values."""
    required = (
        "employment_status",
        "compensation_type",
        "compensation_rate",
        "compensation_effective_start",
        "regular_hours",
        "overtime_hours",
        "other_paid_hours",
        "overtime_multiplier",
        "commission",
        "bonus",
        "other_authorized_earnings",
        "reimbursement",
        "filing_status",
        "w4_step_2",
        "w4_step_3",
        "w4_step_4a",
        "w4_step_4b",
        "w4_step_4c",
        "fica_applicable",
        "work_state",
        "residence_state",
        "deductions",
        "futa_rate",
        "futa_wage_base",
        "suta_rate",
        "suta_wage_base",
        "opening_ytd.gross_wages",
        "opening_ytd.fit_taxable_wages",
        "opening_ytd.social_security_wages",
        "opening_ytd.medicare_wages",
        "opening_ytd.fit_withheld",
        "opening_ytd.social_security_withheld",
        "opening_ytd.medicare_withheld",
        "opening_ytd.futa_wages",
        "opening_ytd.suta_wages",
        "compensation_provenance.source_id",
        "compensation_provenance.effective_date",
        "compensation_provenance.evidence_digest",
        "compensation_provenance.authority_classification",
        "time_provenance.source_id",
        "time_provenance.effective_date",
        "time_provenance.evidence_digest",
        "time_provenance.authority_classification",
        "tax_provenance.source_id",
        "tax_provenance.effective_date",
        "tax_provenance.evidence_digest",
        "tax_provenance.authority_classification",
        "jurisdiction_provenance.source_id",
        "jurisdiction_provenance.effective_date",
        "jurisdiction_provenance.evidence_digest",
        "jurisdiction_provenance.authority_classification",
        "opening_ytd.provenance.source_id",
        "opening_ytd.provenance.effective_date",
        "opening_ytd.provenance.evidence_digest",
        "opening_ytd.provenance.authority_classification",
    )
    if packet is None:
        return {"PAYROLL_INPUT_PACKET": required}
    result: dict[str, tuple[str, ...]] = {}
    for employee in packet.employees:
        missing: list[str] = []
        for name in required:
            value: object = employee
            for segment in name.split("."):
                value = getattr(value, segment, None)
            if value is None or value == "":
                missing.append(name)
        result[employee.display_label] = tuple(missing)
    return result


def collect_readiness(
    employees: Iterable[Mapping[str, object]],
) -> dict[str, dict[str, str]]:
    """Return exact PRESENT/MISSING fields without projecting protected values."""
    required = readiness_missing_fields(None)["PAYROLL_INPUT_PACKET"]
    result: dict[str, dict[str, str]] = {}
    for employee in employees:
        label = str(
            employee.get("employee")
            or employee.get("employee_id")
            or "UNKNOWN_EMPLOYEE"
        )
        if label in result:
            raise BlindReplayError("duplicate readiness Employee identity")
        states: dict[str, str] = {}
        for field in required:
            value: object = employee
            for segment in field.split("."):
                value = value.get(segment) if isinstance(value, Mapping) else None
            states[field] = (
                "PRESENT" if value is not None and value != "" else "MISSING"
            )
        result[label] = states
    return result


def assert_shadow_role(permission_codes: Iterable[str]) -> None:
    allowed = {
        "COMPANY_PAYROLL_CALCULATION_EXECUTE",
        "COMPANY_PAYROLL_CALCULATION_REVIEW",
        "COMPANY_PAYROLL_ACCOUNTING_READ",
    }
    if not allowed.intersection(permission_codes):
        raise PermissionError("authorized Payroll or Accounting role is required")
