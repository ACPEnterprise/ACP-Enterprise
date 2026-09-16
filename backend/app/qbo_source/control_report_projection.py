"""Read-only projections over sealed QBO control reports.

These projections expose source evidence only.  They never create ACP ledger rows or
promote a QBO report to native Accounting truth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from .evidence import EvidenceStoreError
from .ledger_opening_analysis import _date, _shared_strings, _sheet_rows


def discover_registered_control_reports(
    *, evidence_root: Path
) -> list[dict[str, object]]:
    """Return digest-verified registrations without opening a provider connection."""
    controls = evidence_root.expanduser().resolve() / "controls"
    reports: list[dict[str, object]] = []
    for registration_path in sorted(controls.glob("*.json")):
        registration = _read_json(registration_path)
        if registration.get("schema_version") != "qbo-control-registration/v1":
            continue
        raw_sha256 = str(registration.get("raw_sha256", ""))
        suffix = ".csv" if registration.get("kind") == "audit_log" else ".xlsx"
        raw_path = controls / "raw" / f"{raw_sha256}{suffix}"
        _verify_raw(raw_path, raw_sha256, registration.get("byte_size"))
        reports.append(
            {
                "control_id": registration.get("control_id"),
                "kind": registration.get("kind"),
                "accounting_basis": registration.get("accounting_basis"),
                "safe_report_parameters": registration.get("safe_report_parameters"),
                "raw_sha256": raw_sha256,
                "registration_sha256": hashlib.sha256(
                    registration_path.read_bytes()
                ).hexdigest(),
                "authority": "qbo_source_reported",
                "accepted_as_acp_accounting": False,
            }
        )
    return reports


def project_registered_general_ledger_period(
    *, evidence_root: Path, start_date: date, end_date: date, basis: str = "accrual"
) -> dict[str, object]:
    """Summarize an exact date range from a sealed registered General Ledger."""
    if start_date > end_date:
        raise ValueError("start_date must not follow end_date")
    reports = discover_registered_control_reports(evidence_root=evidence_root)
    candidates = [
        report
        for report in reports
        if report["kind"] == "general_ledger"
        and str(report["accounting_basis"]).lower() == basis.lower()
        and _covers(report.get("safe_report_parameters"), start_date, end_date)
    ]
    if not candidates:
        raise EvidenceStoreError("registered_general_ledger_period_unavailable")
    selected = max(candidates, key=lambda item: str(item["control_id"]))
    raw_sha256 = str(selected["raw_sha256"])
    workbook_path = (
        evidence_root.expanduser().resolve()
        / "controls"
        / "raw"
        / f"{raw_sha256}.xlsx"
    )
    metrics = _period_metrics(workbook_path, start_date=start_date, end_date=end_date)
    return {
        "contract_version": "qbo-source-backed-ledger-period/v1",
        "source": "quickbooks_online",
        "authority": "qbo_source_reported",
        "accepted_as_acp_accounting": False,
        "mutation_authority": "none",
        "control_id": selected["control_id"],
        "registration_sha256": selected["registration_sha256"],
        "raw_sha256": raw_sha256,
        "accounting_basis": basis.lower(),
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "limitations": [
            "source_report_not_posted_acp_ledger",
            "ledger_rows_are_not_a_profit_and_loss_report",
            "payment_rows_do_not_duplicate_revenue",
        ],
        **metrics,
    }


def _period_metrics(path: Path, *, start_date: date, end_date: date) -> dict[str, object]:
    try:
        with ZipFile(path) as workbook:
            rows = _sheet_rows(workbook, _shared_strings(workbook))
    except (BadZipFile, KeyError, ElementTree.ParseError) as error:
        raise EvidenceStoreError("ledger_workbook_invalid") from error
    header = next((row for row in rows if "Transaction date" in row.values()), None)
    if header is None:
        raise EvidenceStoreError("ledger_header_missing")
    columns = {value: column for column, value in header.items()}
    required = ("Distribution account", "Transaction date", "Transaction type", "Amount")
    if any(name not in columns for name in required):
        raise EvidenceStoreError("ledger_header_missing")
    types: Counter[str] = Counter()
    accounts: set[str] = set()
    names: set[str] = set()
    numbers: set[str] = set()
    total = Decimal(0)
    count = 0
    for row in rows:
        transaction_date = _date(row.get(columns["Transaction date"], ""))
        account = row.get(columns["Distribution account"], "")
        if (
            transaction_date is None
            or not account
            or not start_date <= transaction_date <= end_date
        ):
            continue
        try:
            amount = Decimal(row.get(columns["Amount"], "") or "0")
        except InvalidOperation as error:
            raise EvidenceStoreError("ledger_amount_invalid") from error
        count += 1
        total += amount
        accounts.add(account)
        types[row.get(columns["Transaction type"], "") or "UNSPECIFIED"] += 1
        if "Name" in columns and row.get(columns["Name"], ""):
            names.add(row[columns["Name"]])
        if "Num" in columns and row.get(columns["Num"], ""):
            numbers.add(row[columns["Num"]])
    return {
        "ledger_row_count": count,
        "distribution_account_count": len(accounts),
        "named_counterparty_count": len(names),
        "transaction_number_count": len(numbers),
        "transaction_type_counts": dict(sorted(types.items())),
        "source_reported_row_amount_sum": str(total),
    }


def _covers(parameters: object, start_date: date, end_date: date) -> bool:
    if not isinstance(parameters, dict):
        return False
    try:
        registered_start = date.fromisoformat(str(parameters["start_date"]))
        registered_end = date.fromisoformat(str(parameters["end_date"]))
        return registered_start <= start_date and registered_end >= end_date
    except (KeyError, ValueError):
        return False


def _verify_raw(path: Path, expected_sha256: str, expected_size: object) -> None:
    if not path.is_file() or path.stat().st_size != expected_size:
        raise EvidenceStoreError("control_report_raw_missing_or_size_mismatch")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise EvidenceStoreError("control_report_raw_digest_mismatch")


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise EvidenceStoreError("stored_document_invalid")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Project a sealed QBO General Ledger period as source evidence"
    )
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--start-date", required=True, type=date.fromisoformat)
    parser.add_argument("--end-date", required=True, type=date.fromisoformat)
    parser.add_argument("--basis", choices=("cash", "accrual"), default="accrual")
    arguments = parser.parse_args()
    result = project_registered_general_ledger_period(
        evidence_root=arguments.evidence_root,
        start_date=arguments.start_date,
        end_date=arguments.end_date,
        basis=arguments.basis,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
