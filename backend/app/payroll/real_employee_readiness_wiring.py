"""Deterministic Employee setup → readiness → calculation-preview assembly.

This module has no persistence, approval, Payroll execution, filing, posting, or
payment authority. Sensitive values enter only after authenticated server-side
decryption and never appear in returned readiness evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Final
from uuid import UUID

from app.business_economics.launch_evidence_readiness import SourcePopulationState

from .contracts import PayrollAuthorityError, canonical_digest
from .federal_tax_rules_2026 import (
    PROVIDER_VERSION,
    Federal2026TaxRuleProvider,
    FederalComponent,
    FederalTaxContext,
    FilingStatus,
    PayFrequency,
    W4Election,
    florida_state_income_tax_applicability,
)
from .real_input_readiness import (
    EmployeePayrollEvidence,
    EmployeePayrollStatus,
    EvidenceValueState,
    PayrollEvidenceField,
    PayrollReadinessPacket,
    build_payroll_readiness_packet,
)
from .tax_authority import (
    AuthorityRequirement,
    AuthorityResolution,
    PayrollInputDomain,
    TaxDeductionAdmissionState,
)
from .tax_calculation import TaxResponsibility, TaxRuleRequest

ASSEMBLY_VERSION: Final = "payroll.real-employee-readiness-assembly.v1"
REFERENCE_VERSION: Final = "payroll.federal-tax-2026-reconciliation.v1"


class AssemblyState(StrEnum):
    READINESS = "READINESS"
    CALCULATION_PREVIEW = "CALCULATION_PREVIEW"


@dataclass(frozen=True, slots=True)
class SetupValue:
    key: str
    employee_id: UUID
    payroll_year: int
    effective_from: date
    effective_to: date | None
    authority_id: UUID
    authority_version: int
    authority_digest: str
    protected_input_digest: str
    value: object


@dataclass(frozen=True, slots=True)
class AssemblyEvidence:
    company_id: UUID
    branch_id: UUID | None
    employee_id: UUID
    employee_active: bool
    period_start: date | None
    period_end: date | None
    pay_frequency: str | None
    compensation_basis: str | None
    compensation_authority_id: UUID | None
    compensation_effective_from: date | None
    compensation_effective_to: date | None
    accepted_time_employee_id: UUID | None
    accepted_time_digest: str | None
    setup_values: tuple[SetupValue, ...]
    independent_reference_version: str | None


@dataclass(frozen=True, slots=True)
class PreviewComponent:
    component: str
    amount: Decimal
    taxable_basis: Decimal
    provider_version: str
    evidence_digest: str


@dataclass(frozen=True, slots=True)
class RealEmployeeAssembly:
    state: AssemblyState
    readiness: PayrollReadinessPacket
    exact_blockers: tuple[str, ...]
    provider_version: str | None
    preview: tuple[PreviewComponent, ...]
    assembly_digest: str


_SETUP_KEYS: Final = (
    "w4_filing_status",
    "w4_step_2",
    "w4_step_3",
    "w4_step_4a",
    "w4_step_4b",
    "w4_step_4c",
    "work_jurisdiction",
    "residence_jurisdiction",
    "state_local_withholding_configuration",
    "unemployment_workforce_jurisdiction",
    "deduction_configuration",
    "deduction_tax_treatment",
    "deduction_effective_date",
    "deduction_limits",
    "social_security_wages_ytd",
    "social_security_tax_ytd",
    "social_security_applicability",
    "medicare_wages_ytd",
    "medicare_tax_ytd",
    "medicare_applicability",
    "additional_medicare_prerequisites",
    "federal_withholding_ytd",
    "prior_payroll_coverage",
)


def assemble_real_employee_readiness(
    evidence: AssemblyEvidence, *, allow_fixture_preview: bool = False
) -> RealEmployeeAssembly:
    year = evidence.period_end.year if evidence.period_end else None
    resolved, conflicts = _resolve_values(evidence, year)
    values = {key: item.value for key, item in resolved.items()}
    fields = _setup_fields(resolved)
    fields.extend(_operating_fields(evidence))
    if year == 2026 and evidence.period_end:
        fields.extend(_provider_fields(evidence.period_end))
    if (
        values.get("work_jurisdiction") == "US-FL"
        and values.get("residence_jurisdiction") == "US-FL"
    ):
        florida_state_income_tax_applicability(
            work_jurisdiction="US-FL", residence_jurisdiction="US-FL"
        )
        fields.extend(
            (
                _not_applicable("state_local_withholding_configuration"),
                _not_applicable("state_local_tax_table"),
            )
        )
    for key in conflicts:
        fields = [item for item in fields if item.key != key]
        fields.append(
            PayrollEvidenceField(
                key, EvidenceValueState.CONFLICTING, None, None, None, None, None
            )
        )
    packet = build_payroll_readiness_packet(
        employees=(
            EmployeePayrollEvidence(
                str(evidence.employee_id),
                str(evidence.company_id),
                str(evidence.branch_id) if evidence.branch_id else None,
                evidence.employee_active,
                evidence.compensation_basis,
                tuple(fields),
            ),
        ),
        source_population_state=SourcePopulationState.SOURCE_CURRENT,
        independently_accepted_reference_reconciled=evidence.independent_reference_version
        == REFERENCE_VERSION,
    )
    employee = packet.employees[0]
    preview: tuple[PreviewComponent, ...] = ()
    state = AssemblyState.READINESS
    if allow_fixture_preview and employee.status is EmployeePayrollStatus.PAYROLL_READY:
        preview = _preview(evidence, values)
        state = AssemblyState.CALCULATION_PREVIEW
    body = {
        "version": ASSEMBLY_VERSION,
        "employee": str(evidence.employee_id),
        "packet": packet.packet_digest,
        "state": state,
        "provider": PROVIDER_VERSION if year == 2026 else None,
        "preview": tuple(
            (v.component, str(v.amount), v.evidence_digest) for v in preview
        ),
    }
    return RealEmployeeAssembly(
        state,
        packet,
        employee.exact_blockers,
        PROVIDER_VERSION if year == 2026 else None,
        preview,
        canonical_digest(body),
    )


def _resolve_values(
    evidence: AssemblyEvidence, year: int | None
) -> tuple[dict[str, SetupValue], tuple[str, ...]]:
    selected: dict[str, list[SetupValue]] = {}
    if year is None or evidence.period_end is None:
        return {}, ()
    for value in evidence.setup_values:
        if value.employee_id != evidence.employee_id or value.payroll_year != year:
            selected.setdefault(value.key, []).append(value)
            continue
        if value.effective_from <= evidence.period_end and (
            value.effective_to is None
            or evidence.period_start is not None
            and value.effective_to >= evidence.period_start
        ):
            selected.setdefault(value.key, []).append(value)
    conflicts = tuple(
        sorted(
            key
            for key, rows in selected.items()
            if len(rows) != 1
            or rows[0].employee_id != evidence.employee_id
            or rows[0].payroll_year != year
        )
    )
    return (
        {
            key: rows[0]
            for key, rows in selected.items()
            if key not in conflicts and len(rows) == 1
        },
        conflicts,
    )


def _field(key: str, value: SetupValue) -> PayrollEvidenceField:
    state = (
        EvidenceValueState.AUTHORITATIVE_ZERO
        if _is_zero(value.value)
        else EvidenceValueState.AVAILABLE
    )
    return PayrollEvidenceField(
        key,
        state,
        "payroll_input_authority",
        str(value.authority_id),
        str(value.authority_version),
        value.effective_from.isoformat(),
        value.authority_digest,
    )


def _setup_fields(values: dict[str, SetupValue]) -> list[PayrollEvidenceField]:
    result = []
    for key in _SETUP_KEYS:
        if key in values:
            result.append(_field(key, values[key]))
    return result


def _is_zero(value: object) -> bool:
    return isinstance(value, (bool, int, Decimal, str)) and value in {
        0,
        Decimal(0),
        "0",
        "0.00",
    }


def _operating_fields(value: AssemblyEvidence) -> list[PayrollEvidenceField]:
    result = []

    def add(key: str, available: bool, digest: str | None = None) -> None:
        if available:
            result.append(
                PayrollEvidenceField(
                    key,
                    EvidenceValueState.AVAILABLE,
                    "payroll_operating_authority",
                    f"resolved:{key}",
                    "effective",
                    value.period_end.isoformat() if value.period_end else "unknown",
                    digest
                    or canonical_digest(
                        {"key": key, "employee": str(value.employee_id)}
                    ),
                )
            )

    compensation_active = bool(
        value.period_start
        and value.period_end
        and value.compensation_authority_id
        and value.compensation_effective_from
        and value.compensation_effective_from <= value.period_end
        and (
            value.compensation_effective_to is None
            or value.compensation_effective_to >= value.period_start
        )
    )
    for key in (
        "compensation_basis",
        "compensation_rate",
        "compensation_effective_date",
        "compensation_revision_state",
    ):
        add(key, compensation_active)
    time_ready = (
        value.accepted_time_employee_id == value.employee_id
        and value.accepted_time_digest is not None
    )
    for key in (
        "accepted_paid_time",
        "timecard_status",
        "time_correction_revision",
        "overtime_applicability",
    ):
        add(key, time_ready, value.accepted_time_digest)
    add("accepted_job_specific_time", time_ready, value.accepted_time_digest)
    add(
        "payroll_period_assignment",
        value.period_start is not None and value.period_end is not None,
    )
    return result


def _provider_fields(effective_on: date) -> list[PayrollEvidenceField]:
    return [
        PayrollEvidenceField(
            key,
            EvidenceValueState.AVAILABLE,
            "official_2026_federal_tax_provider",
            PROVIDER_VERSION,
            PROVIDER_VERSION,
            effective_on.isoformat(),
            canonical_digest(
                {"provider": PROVIDER_VERSION, "key": key, "effective_on": effective_on}
            ),
        )
        for key in (
            "federal_tax_table",
            "tax_table_source_version",
            "tax_table_effective_date",
        )
    ]


def _not_applicable(key: str) -> PayrollEvidenceField:
    return PayrollEvidenceField(
        key,
        EvidenceValueState.NOT_APPLICABLE,
        "Florida Department of Revenue",
        key,
        "2026",
        "2026-01-01",
        canonical_digest({"key": key, "jurisdiction": "US-FL"}),
    )


def _preview(
    evidence: AssemblyEvidence, values: dict[str, object]
) -> tuple[PreviewComponent, ...]:
    if evidence.pay_frequency is None:
        raise PayrollAuthorityError("calculation preview pay frequency is missing")
    gross = Decimal(str(values.get("fixture_gross_wages", "1000")))
    context = FederalTaxContext(
        effective_on=evidence.period_end or date.min,
        pay_frequency=PayFrequency(evidence.pay_frequency),
        w4=W4Election(
            FilingStatus(str(values["w4_filing_status"])),
            bool(values["w4_step_2"]),
            Decimal(str(values["w4_step_3"])),
            Decimal(str(values["w4_step_4a"])),
            Decimal(str(values["w4_step_4b"])),
            Decimal(str(values["w4_step_4c"])),
        ),
        social_security_wages_ytd=Decimal(str(values["social_security_wages_ytd"])),
        medicare_wages_ytd=Decimal(str(values["medicare_wages_ytd"])),
    )
    result = []
    for component, responsibility in (
        (FederalComponent.FEDERAL_INCOME_TAX, TaxResponsibility.EMPLOYEE_WITHHOLDING),
        (
            FederalComponent.SOCIAL_SECURITY_EMPLOYEE,
            TaxResponsibility.EMPLOYEE_PAYROLL_TAX,
        ),
        (
            FederalComponent.SOCIAL_SECURITY_EMPLOYER,
            TaxResponsibility.EMPLOYER_PAYROLL_TAX,
        ),
        (FederalComponent.MEDICARE_EMPLOYEE, TaxResponsibility.EMPLOYEE_PAYROLL_TAX),
        (FederalComponent.MEDICARE_EMPLOYER, TaxResponsibility.EMPLOYER_PAYROLL_TAX),
        (
            FederalComponent.ADDITIONAL_MEDICARE_EMPLOYEE,
            TaxResponsibility.EMPLOYEE_PAYROLL_TAX,
        ),
    ):
        authority = AuthorityResolution(
            AuthorityRequirement(
                PayrollInputDomain.TAX, component.value, evidence.employee_id
            ),
            TaxDeductionAdmissionState.READY,
            UUID(int=1),
            canonical_digest(
                {"employee": str(evidence.employee_id), "component": component}
            ),
            canonical_digest({"setup": str(evidence.employee_id)}),
            (),
        )
        output = Federal2026TaxRuleProvider(context, component).calculate(
            TaxRuleRequest(
                component.value,
                responsibility,
                authority,
                "US-FEDERAL",
                gross,
                "USD",
                True,
            )
        )
        result.append(
            PreviewComponent(
                component.value,
                output.amount,
                output.taxable_basis,
                output.provider_version,
                output.evidence_digest,
            )
        )
    return tuple(result)
