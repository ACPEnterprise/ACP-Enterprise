"""Read-only employee Payroll input readiness; no calculation or execution.

The evaluator consumes presence/state metadata from owning authorities. Sensitive
values remain in their protected domains. An authoritative zero is evidence; a
missing or blank value is not zero.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Final

from app.business_economics.launch_evidence_readiness import (
    CONTRACT_VERSION as ECO_LAUNCH_CONTRACT_VERSION,
)
from app.business_economics.launch_evidence_readiness import (
    SourcePopulationState,
)

CONTRACT_VERSION: Final = "payroll.real-input-readiness.v1"
MAX_EMPLOYEES: Final = 10_000


class EvidenceValueState(StrEnum):
    AVAILABLE = "AVAILABLE"
    AUTHORITATIVE_ZERO = "AUTHORITATIVE_ZERO"
    MISSING = "MISSING"
    CONFLICTING = "CONFLICTING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EmployeePayrollStatus(StrEnum):
    PAYROLL_READY = "PAYROLL_READY"
    BLOCKED_FOR_PAYROLL = "BLOCKED_FOR_PAYROLL"


class CalculationReadiness(StrEnum):
    INPUT_READY = "INPUT_READY"
    TIME_NOT_READY = "TIME_NOT_READY"
    COMPENSATION_NOT_READY = "COMPENSATION_NOT_READY"
    WITHHOLDING_NOT_READY = "WITHHOLDING_NOT_READY"
    DEDUCTION_NOT_READY = "DEDUCTION_NOT_READY"
    YTD_NOT_READY = "YTD_NOT_READY"
    JURISDICTION_NOT_READY = "JURISDICTION_NOT_READY"
    TAX_TABLE_NOT_READY = "TAX_TABLE_NOT_READY"
    CONFLICTING = "CONFLICTING"


@dataclass(frozen=True, slots=True)
class PayrollEvidenceField:
    key: str
    state: EvidenceValueState
    authority: str | None
    record_id: str | None
    version: str | None
    effective_at: str | None
    evidence_digest: str | None

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("Payroll evidence field key is required")
        if self.state in {
            EvidenceValueState.AVAILABLE,
            EvidenceValueState.AUTHORITATIVE_ZERO,
        } and not all(
            (
                self.authority,
                self.record_id,
                self.version,
                self.effective_at,
                self.evidence_digest,
            )
        ):
            raise ValueError("available Payroll evidence requires complete provenance")


@dataclass(frozen=True, slots=True)
class EmployeePayrollEvidence:
    employee_id: str
    company_id: str
    branch_id: str | None
    active: bool
    compensation_basis: str | None
    fields: tuple[PayrollEvidenceField, ...]


@dataclass(frozen=True, slots=True)
class EmployeePayrollReadiness:
    employee_id: str
    company_id: str
    branch_id: str | None
    status: EmployeePayrollStatus
    calculation_readiness: tuple[CalculationReadiness, ...]
    exact_blockers: tuple[str, ...]
    owner_input_request: tuple[str, ...]
    evidence_digest: str


@dataclass(frozen=True, slots=True)
class PayrollReadinessPacket:
    contract_version: str
    governing_eco_contract_version: str
    source_population_state: SourcePopulationState
    population_blocker: str | None
    total_active_employees_evaluated: int | None
    payroll_ready_count: int | None
    blocked_for_payroll_count: int | None
    employees: tuple[EmployeePayrollReadiness, ...]
    tax_table_readiness: str
    deduction_readiness: str
    ytd_readiness: str
    timecard_readiness: str
    independently_accepted_reference_reconciled: bool
    checklist_6_calculation_ready: bool
    limitations: tuple[str, ...]
    packet_digest: str


_GROUPS: Final = {
    CalculationReadiness.COMPENSATION_NOT_READY: (
        "compensation_basis",
        "compensation_rate",
        "compensation_effective_date",
        "compensation_revision_state",
    ),
    CalculationReadiness.TIME_NOT_READY: (
        "accepted_paid_time",
        "accepted_job_specific_time",
        "timecard_status",
        "time_correction_revision",
        "overtime_applicability",
        "payroll_period_assignment",
    ),
    CalculationReadiness.WITHHOLDING_NOT_READY: (
        "w4_filing_status",
        "w4_step_2",
        "w4_step_3",
        "w4_step_4a",
        "w4_step_4b",
        "w4_step_4c",
    ),
    CalculationReadiness.JURISDICTION_NOT_READY: (
        "work_jurisdiction",
        "residence_jurisdiction",
        "state_local_withholding_configuration",
        "unemployment_workforce_jurisdiction",
    ),
    CalculationReadiness.DEDUCTION_NOT_READY: (
        "deduction_configuration",
        "deduction_tax_treatment",
        "deduction_effective_date",
        "deduction_limits",
    ),
    CalculationReadiness.YTD_NOT_READY: (
        "social_security_applicability",
        "medicare_applicability",
        "social_security_wages_ytd",
        "social_security_tax_ytd",
        "medicare_wages_ytd",
        "medicare_tax_ytd",
        "additional_medicare_prerequisites",
        "federal_withholding_ytd",
        "prior_payroll_coverage",
    ),
    CalculationReadiness.TAX_TABLE_NOT_READY: (
        "federal_tax_table",
        "state_local_tax_table",
        "tax_table_source_version",
        "tax_table_effective_date",
    ),
}

_NOT_APPLICABLE_ALLOWED: Final = {
    "accepted_job_specific_time",
    "state_local_withholding_configuration",
    "deduction_configuration",
    "deduction_tax_treatment",
    "deduction_effective_date",
    "deduction_limits",
    "additional_medicare_prerequisites",
    "state_local_tax_table",
}


def build_payroll_readiness_packet(
    *,
    employees: tuple[EmployeePayrollEvidence, ...],
    source_population_state: SourcePopulationState,
    independently_accepted_reference_reconciled: bool,
) -> PayrollReadinessPacket:
    if len(employees) > MAX_EMPLOYEES:
        raise ValueError("Payroll readiness population exceeds bounded size")
    active = tuple(
        sorted((item for item in employees if item.active), key=lambda x: x.employee_id)
    )
    if len({item.employee_id for item in active}) != len(active):
        raise ValueError("duplicate active Employee identity")
    if len({item.company_id for item in active}) > 1:
        raise ValueError("cross-Company Payroll readiness population")
    population_missing = source_population_state is SourcePopulationState.SOURCE_MISSING
    if population_missing and employees:
        raise ValueError("missing source population cannot contain Employee evidence")
    evaluated = tuple(_evaluate_employee(item) for item in active)
    ready = sum(
        item.status is EmployeePayrollStatus.PAYROLL_READY for item in evaluated
    )
    complete = bool(evaluated) and ready == len(evaluated)
    packet_body = {
        "contract_version": CONTRACT_VERSION,
        "governing_eco_contract_version": ECO_LAUNCH_CONTRACT_VERSION,
        "source_population_state": source_population_state,
        "employees": [asdict(item) for item in evaluated],
        "reference_reconciled": independently_accepted_reference_reconciled,
    }
    digest = hashlib.sha256(
        json.dumps(
            packet_body, sort_keys=True, separators=(",", ":"), default=str
        ).encode()
    ).hexdigest()
    return PayrollReadinessPacket(
        CONTRACT_VERSION,
        ECO_LAUNCH_CONTRACT_VERSION,
        source_population_state,
        "authorized_real_active_employee_population_unavailable"
        if population_missing
        else None,
        None if population_missing else len(evaluated),
        None if population_missing else ready,
        None if population_missing else len(evaluated) - ready,
        evaluated,
        _summary(evaluated, CalculationReadiness.TAX_TABLE_NOT_READY),
        _summary(evaluated, CalculationReadiness.DEDUCTION_NOT_READY),
        _summary(evaluated, CalculationReadiness.YTD_NOT_READY),
        _summary(evaluated, CalculationReadiness.TIME_NOT_READY),
        independently_accepted_reference_reconciled,
        not population_missing
        and complete
        and independently_accepted_reference_reconciled,
        (
            "Readiness does not execute or finalize Payroll.",
            "Scheduled hours and unaccepted Timecards are not payable time.",
            "Protected values are not projected into this packet.",
            "Checklist #6 remains false until an independent Payroll reference is reconciled.",
            "Unavailable Employee population produces unknown counts, never zero.",
        ),
        digest,
    )


def _evaluate_employee(item: EmployeePayrollEvidence) -> EmployeePayrollReadiness:
    values = {field.key: field for field in item.fields}
    if len(values) != len(item.fields):
        raise ValueError("duplicate Employee Payroll evidence field")
    readiness: list[CalculationReadiness] = []
    blockers: list[str] = []
    conflicts = sorted(
        key
        for key, value in values.items()
        if value.state is EvidenceValueState.CONFLICTING
    )
    if conflicts:
        readiness.append(CalculationReadiness.CONFLICTING)
        blockers.extend(f"conflicting {key}" for key in conflicts)
    for state, keys in _GROUPS.items():
        missing = tuple(
            key
            for key in keys
            if key not in values or not _field_satisfies(key, values[key])
        )
        if missing:
            readiness.append(state)
            blockers.extend(f"missing {key}" for key in missing if key not in conflicts)
    if not item.branch_id:
        readiness.append(CalculationReadiness.JURISDICTION_NOT_READY)
        blockers.append("missing authoritative home Branch")
    if item.compensation_basis not in {"hourly", "salaried"}:
        if CalculationReadiness.COMPENSATION_NOT_READY not in readiness:
            readiness.append(CalculationReadiness.COMPENSATION_NOT_READY)
        blockers.append("missing compensation basis")
    ordered_readiness = tuple(dict.fromkeys(readiness)) or (
        CalculationReadiness.INPUT_READY,
    )
    exact = tuple(sorted(set(blockers)))
    status = (
        EmployeePayrollStatus.PAYROLL_READY
        if ordered_readiness == (CalculationReadiness.INPUT_READY,)
        else EmployeePayrollStatus.BLOCKED_FOR_PAYROLL
    )
    body = {
        "employee_id": item.employee_id,
        "company_id": item.company_id,
        "branch_id": item.branch_id,
        "status": status,
        "readiness": ordered_readiness,
        "blockers": exact,
        "field_evidence": [
            asdict(field) for field in sorted(item.fields, key=lambda x: x.key)
        ],
    }
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    return EmployeePayrollReadiness(
        item.employee_id,
        item.company_id,
        item.branch_id,
        status,
        ordered_readiness,
        exact,
        exact,
        digest,
    )


def _summary(
    employees: tuple[EmployeePayrollReadiness, ...], state: CalculationReadiness
) -> str:
    return (
        "READY"
        if employees
        and all(state not in item.calculation_readiness for item in employees)
        else "NOT_READY"
    )


def _field_satisfies(key: str, field: PayrollEvidenceField) -> bool:
    if field.state in {
        EvidenceValueState.AVAILABLE,
        EvidenceValueState.AUTHORITATIVE_ZERO,
    }:
        return True
    return (
        field.state is EvidenceValueState.NOT_APPLICABLE
        and key in _NOT_APPLICABLE_ALLOWED
    )
