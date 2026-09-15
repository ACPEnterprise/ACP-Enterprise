"""Read-only May 2026 reporting projection from registered QBO controls."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from .evidence import EvidenceStoreError
from .ledger_opening_analysis import _shared_strings, _sheet_rows

CONTRACT = "qbo-source-backed-may-report/v1"
START = date(2026, 5, 1)
END = date(2026, 5, 31)

_INCOME = {
    "Discounts given",
    "Returns & Allowances",
    "Sales",
    "Sales of Product Income",
    "Services",
    "Unapplied Cash Payment Income",
}
_COGS = {
    "Building permits",
    "Disposal Fees",
    "Equipment Lease",
    "Housecall Pro Payment Processing Fee",
    "Subcontractors Expense",
    "Supplies & Material - COGS",
}
_EXPENSE = {
    "Advertising and Promotion",
    "Answering Service",
    "Bank Service Charges",
    "Consulting",
    "Continuing Education",
    "Depreciation Expense",
    "Dues & Subscriptions",
    "Insurance Expense",
    "Interest Expense",
    "Loan Fees",
    "Meals and Entertainment",
    "Merchant Fees",
    "Office Supplies",
    "Parking & Tolls",
    "Payroll Expenses",
    "Officer Compensation",
    "Salaries and wages",
    "Taxes",
    "Wages",
    "Pipe Capital (via Housecall Pro) - Fees",
    "Postage & Delivery",
    "Professional Fees",
    "Reimbursements",
    "Rent Expense",
    "Repairs and Maintenance",
    "Security expense",
    "Small business Loan Repayment",
    "Small Tools & Equipment",
    "Software",
    "Storage",
    "Supplies",
    "Taxes & Licenses",
    "Payroll Taxes",
    "Telephone Expense",
    "Travel Expense",
    "Uniforms",
    "Utilities",
    "Vehicle Expense",
}
_OTHER_INCOME = {"Other Income", "Rewards Income"}
_OTHER_EXPENSE = {"Ask My Accountant"}


def project_may_2026_source_report(root: Path) -> dict[str, object] | None:
    """Project May without creating Accounting truth or composing HCP amounts."""
    controls = root / "controls"
    ledger = _latest_control(controls, kind="general_ledger", basis="accrual")
    profit_loss = _latest_control(controls, kind="profit_and_loss", basis="cash")
    if ledger is None:
        return None
    ledger_path, ledger_registration = ledger
    raw_path = _raw_path(root, ledger_registration)
    if profit_loss is not None:
        _raw_path(root, profit_loss[1])
    rows, strings = _rows(raw_path)
    if "All County Plumbing and Leak" not in strings or "General Ledger" not in strings:
        raise EvidenceStoreError("may_ledger_report_identity_invalid")
    header = next((row for row in rows if "Transaction date" in row.values()), None)
    if header is None:
        raise EvidenceStoreError("may_ledger_header_missing")
    columns = {value: column for column, value in header.items()}
    required = {
        "account": "Distribution account",
        "date": "Transaction date",
        "type": "Transaction type",
        "number": "Num",
        "name": "Name",
        "amount": "Amount",
    }
    if any(label not in columns for label in required.values()):
        raise EvidenceStoreError("may_ledger_header_missing")
    may_rows: list[dict[int, str]] = []
    for row in rows:
        observed = _date(row.get(columns[required["date"]], ""))
        if observed is not None and START <= observed <= END:
            may_rows.append(row)
    if not may_rows:
        raise EvidenceStoreError("may_ledger_rows_missing")
    amounts: dict[str, Decimal] = {
        "income": Decimal(0),
        "cost_of_goods_sold": Decimal(0),
        "operating_expense": Decimal(0),
        "other_income": Decimal(0),
        "other_expense": Decimal(0),
        "excluded_non_profit_loss": Decimal(0),
    }
    counts: Counter[str] = Counter()
    transaction_types: Counter[str] = Counter()
    named_postings: Counter[str] = Counter()
    numbered_postings: Counter[str] = Counter()
    for row in may_rows:
        account = row.get(columns[required["account"]], "")
        family = _family(account)
        amount = _amount(row.get(columns[required["amount"]], ""))
        amounts[family] += amount
        counts[family] += 1
        transaction_type = row.get(columns[required["type"]], "") or "UNSPECIFIED"
        transaction_types[transaction_type] += 1
        if row.get(columns[required["name"]], ""):
            named_postings[transaction_type] += 1
        if row.get(columns[required["number"]], ""):
            numbered_postings[transaction_type] += 1
    revenue = amounts["income"]
    cogs = amounts["cost_of_goods_sold"]
    operating_expense = amounts["operating_expense"]
    other_income = amounts["other_income"]
    other_expense = amounts["other_expense"]
    values = {
        "revenue": _money(revenue),
        "cost_of_goods_sold": _money(cogs),
        "gross_profit": _money(revenue - cogs),
        "operating_expense": _money(operating_expense),
        "net_operating_income": _money(revenue - cogs - operating_expense),
        "other_income": _money(other_income),
        "other_expense": _money(other_expense),
        "net_income": _money(
            revenue - cogs - operating_expense + other_income - other_expense
        ),
    }
    result: dict[str, object] = {
        "contract": CONTRACT,
        "authority": "QBO_SOURCE_BACKED",
        "accepted_as_acp_accounting": False,
        "basis": "accrual",
        "period": {"start": START.isoformat(), "end": END.isoformat()},
        "currency": "USD",
        "source_as_of": ledger_registration["report_end_date"],
        "acquired_at": ledger_registration.get("generated_at"),
        "source_control": _control_evidence(ledger_path, ledger_registration),
        "supporting_cash_profit_loss_control": (
            _control_evidence(*profit_loss) if profit_loss is not None else None
        ),
        "values": values,
        "coverage": {
            "may_ledger_postings": len(may_rows),
            "classified_profit_loss_postings": sum(
                counts[key]
                for key in (
                    "income",
                    "cost_of_goods_sold",
                    "operating_expense",
                    "other_income",
                    "other_expense",
                )
            ),
            "excluded_non_profit_loss_postings": counts["excluded_non_profit_loss"],
            "postings_by_profit_loss_family": {
                key: counts[key]
                for key in (
                    "income",
                    "cost_of_goods_sold",
                    "operating_expense",
                    "other_income",
                    "other_expense",
                )
            },
            "transaction_types": dict(sorted(transaction_types.items())),
            "named_postings_by_type": dict(sorted(named_postings.items())),
            "numbered_postings_by_type": dict(sorted(numbered_postings.items())),
            "invoice_ledger_postings": transaction_types["Invoice"],
            "payment_ledger_postings": transaction_types["Payment"],
            "provider_transaction_ids": "unavailable_in_registered_gl_export",
            "job_provider_ids": "unavailable_in_registered_gl_export",
        },
        "duplicate_boundary": {
            "financial_amount_authority": "QBO_ONLY",
            "hcp_amounts_composed": False,
            "payments_counted_as_revenue": False,
            "rule": "QBO report account postings only; HCP is linkage context only",
        },
        "limitations": [
            "derived_from_registered_qbo_accrual_general_ledger",
            "not_a_native_qbo_may_profit_and_loss_export",
            "registered_cash_profit_and_loss_is_aggregate_2022_through_2026_not_may",
            "customer_names_are_labels_not_acp_customer_identity",
            "job_provider_identity_unavailable",
            "invoice_and_payment_counts_are_ledger_postings_not_unique_entities",
            "qbo_source_reported_not_posted_acp_ledger",
            "missing_values_are_not_zero",
        ],
        "mutation_authority": "none",
    }
    result["evidence_digest"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return result


def _latest_control(
    controls: Path, *, kind: str, basis: str
) -> tuple[Path, dict[str, Any]] | None:
    candidates = []
    for path in controls.glob("*.json"):
        try:
            value = json.loads(path.read_bytes())
        except (OSError, json.JSONDecodeError) as error:
            raise EvidenceStoreError("may_control_registration_invalid") from error
        if not isinstance(value, dict):
            continue
        parameters = value.get("safe_report_parameters")
        start = parameters.get("start_date") if isinstance(parameters, dict) else None
        end = parameters.get("end_date") if isinstance(parameters, dict) else None
        if (
            value.get("schema_version") == "qbo-control-registration/v1"
            and value.get("kind") == kind
            and str(value.get("accounting_basis", "")).lower() == basis
            and isinstance(start, str)
            and isinstance(end, str)
            and start <= START.isoformat()
            and end >= END.isoformat()
        ):
            candidates.append((str(value["control_id"]), path, value))
    if not candidates:
        return None
    _, path, value = max(candidates, key=lambda item: item[0])
    return path, value


def _raw_path(root: Path, registration: dict[str, Any]) -> Path:
    digest = registration.get("raw_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise EvidenceStoreError("may_control_digest_invalid")
    path = root / "controls" / "raw" / f"{digest}.xlsx"
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise EvidenceStoreError("may_control_digest_mismatch")
    return path


def _rows(path: Path) -> tuple[list[dict[int, str]], list[str]]:
    try:
        with ZipFile(path) as workbook:
            shared = _shared_strings(workbook)
            rows = _sheet_rows(workbook, shared)
    except (BadZipFile, KeyError, ElementTree.ParseError) as error:
        raise EvidenceStoreError("may_control_workbook_invalid") from error
    return rows, [value for row in rows for value in row.values()]


def _control_evidence(path: Path, value: dict[str, Any]) -> dict[str, object]:
    return {
        "control_id": value["control_id"],
        "kind": value["kind"],
        "basis": value["accounting_basis"],
        "period": value["safe_report_parameters"],
        "registration_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "raw_sha256": value["raw_sha256"],
    }


def _family(account: str) -> str:
    if account in _INCOME:
        return "income"
    if account in _COGS:
        return "cost_of_goods_sold"
    if account in _EXPENSE:
        return "operating_expense"
    if account in _OTHER_INCOME:
        return "other_income"
    if account in _OTHER_EXPENSE:
        return "other_expense"
    return "excluded_non_profit_loss"


def _date(value: str) -> date | None:
    try:
        month, day, year = (int(part) for part in value.split("/"))
        return date(year, month, day)
    except (TypeError, ValueError):
        return None


def _amount(value: str) -> Decimal:
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise EvidenceStoreError("may_ledger_amount_invalid") from error


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")
