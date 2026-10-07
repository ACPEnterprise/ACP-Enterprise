"""Value-free capability and evidence plan for historical QBO Payroll cutover.

The QBO Accounting API does not expose authoritative paycheck detail.  This
module describes what a sealed Accounting snapshot can prove and what must be
provided as a separately sealed Payroll export or physical source document.
It never calculates Payroll or treats catalog presence as a Payroll value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from .contracts import canonical_digest


class PayrollSourceCapability(StrEnum):
    API_AVAILABLE = "API_AVAILABLE"
    EXISTING_SEALED_EVIDENCE = "EXISTING_SEALED_EVIDENCE"
    EXTERNAL_EXPORT_REQUIRED = "EXTERNAL_EXPORT_REQUIRED"
    MANUAL_EVIDENCE_REQUIRED = "MANUAL_EVIDENCE_REQUIRED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class PayrollFamilyCapability:
    family: str
    classification: PayrollSourceCapability
    accounting_api_support: tuple[str, ...]
    required_exports: tuple[str, ...]
    limitation: str


PAYROLL_EXPORT_REPORTS: Final = (
    "Payroll Details",
    "Payroll Summary by Employee",
    "Paycheck List",
    "Payroll Deductions/Contributions",
    "Payroll Tax and Wage Summary",
    "Payroll Tax Liability",
    "Payroll Tax Payments",
    "Employee Details",
)

_DETAIL_EXPORTS: Final = ("Payroll Details", "Paycheck List")
_YTD_EXPORTS: Final = (
    "Payroll Summary by Employee",
    "Payroll Tax and Wage Summary",
    "Payroll Deductions/Contributions",
)
_LIABILITY_EXPORTS: Final = ("Payroll Tax Liability", "Payroll Tax Payments")


def classify_payroll_history(
    *, entity_counts: dict[str, int], sealed_manifest_available: bool
) -> tuple[PayrollFamilyCapability, ...]:
    """Classify source capability without inspecting or emitting protected values."""

    api_entities = {
        key
        for key in (
            "employee",
            "time_activity",
            "journal_entry",
            "tax_payment",
            "account",
        )
        if entity_counts.get(key, 0) > 0
    }
    accounting_state = (
        PayrollSourceCapability.EXISTING_SEALED_EVIDENCE
        if sealed_manifest_available and api_entities
        else PayrollSourceCapability.API_AVAILABLE
    )
    rows = (
        (
            "employee_identity",
            accounting_state,
            ("employee",),
            ("Employee Details",),
            "Accounting Employee identity is candidate evidence only; an approved provider-ID crosswalk is required.",
        ),
        (
            "payroll_runs_periods_pay_dates",
            PayrollSourceCapability.EXTERNAL_EXPORT_REQUIRED,
            (),
            _DETAIL_EXPORTS,
            "The Accounting API has no authoritative Payroll run/pay-period entity.",
        ),
        (
            "paychecks_payment_identity_check_numbers",
            PayrollSourceCapability.EXTERNAL_EXPORT_REQUIRED,
            (),
            _DETAIL_EXPORTS,
            "Booked accounting transactions do not establish Employee paycheck detail or payment method.",
        ),
        (
            "earnings_hours_gross_net",
            PayrollSourceCapability.EXTERNAL_EXPORT_REQUIRED,
            ("time_activity",),
            ("Payroll Details", "Payroll Summary by Employee"),
            "TimeActivity is not accepted Payroll time and does not establish wages, gross, or net pay.",
        ),
        (
            "employee_employer_taxes",
            PayrollSourceCapability.EXTERNAL_EXPORT_REQUIRED,
            ("journal_entry", "tax_payment"),
            ("Payroll Details", "Payroll Tax and Wage Summary"),
            "Accounting postings may support totals but not Employee-level Payroll tax authority.",
        ),
        (
            "deductions_contributions_reimbursements",
            PayrollSourceCapability.EXTERNAL_EXPORT_REQUIRED,
            ("journal_entry",),
            ("Payroll Details", "Payroll Deductions/Contributions"),
            "Aggregate postings cannot establish Employee elections or paycheck components.",
        ),
        (
            "liabilities_remittances_settlements",
            PayrollSourceCapability.EXTERNAL_EXPORT_REQUIRED,
            ("account", "journal_entry", "tax_payment"),
            _LIABILITY_EXPORTS,
            "Accounting evidence supports reconciliation only; Payroll reports and settlement evidence are required.",
        ),
        (
            "employee_ytd",
            PayrollSourceCapability.EXTERNAL_EXPORT_REQUIRED,
            (),
            _YTD_EXPORTS,
            "Employee-level YTD wages, taxes, deductions, and contributions are outside the Accounting API contract.",
        ),
        (
            "voids_reversals_off_cycle",
            PayrollSourceCapability.EXTERNAL_EXPORT_REQUIRED,
            ("journal_entry",),
            ("Payroll Details", "Paycheck List"),
            "Accounting versions may reveal booked effects but do not prove complete Payroll lifecycle history.",
        ),
        (
            "post_qbo_bridge_and_future_final_checks",
            PayrollSourceCapability.MANUAL_EVIDENCE_REQUIRED,
            (),
            (),
            "These events occurred or will occur outside authoritative QBO Payroll and require physical evidence.",
        ),
    )
    return tuple(
        PayrollFamilyCapability(
            family,
            classification,
            tuple(item for item in api_support if item in api_entities),
            exports,
            limitation,
        )
        for family, classification, api_support, exports, limitation in rows
    )


def acquisition_plan(
    *,
    entity_counts: dict[str, int],
    source_manifest_sha256: str | None,
    acquisition_state: str,
) -> dict[str, object]:
    """Return a deterministic, value-free acquisition and operator packet."""

    rows = classify_payroll_history(
        entity_counts=entity_counts,
        sealed_manifest_available=source_manifest_sha256 is not None,
    )
    body: dict[str, object] = {
        "contract_version": "payroll.qbo-history-acquisition.v1",
        "acquisition_state": acquisition_state,
        "source_manifest_sha256": source_manifest_sha256,
        "families": [
            {
                "family": row.family,
                "classification": row.classification.value,
                "accounting_api_support": row.accounting_api_support,
                "required_exports": row.required_exports,
                "limitation": row.limitation,
            }
            for row in rows
        ],
        "required_exports": PAYROLL_EXPORT_REPORTS,
        "last_qbo_payroll_cutoff": "UNAVAILABLE_UNTIL_PAYROLL_DETAILS_AND_PAYCHECK_LIST_ARE_SEALED",
        "bridge_periods": "UNAVAILABLE_UNTIL_LAST_QBO_PAYROLL_CUTOFF_IS_PROVEN",
        "missing_values_are_zero": False,
        "payroll_executed": False,
        "qbo_write_occurred": False,
        "accounting_posting_occurred": False,
        "money_moved": False,
    }
    body["packet_digest"] = canonical_digest(body)
    return body
