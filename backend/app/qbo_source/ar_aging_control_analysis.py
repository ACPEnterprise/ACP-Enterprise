"""Safe cutoff analysis of a registered QBO A/R Aging Detail report."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from .evidence import (
    ControlEvidenceRegistry,
    EvidenceStoreError,
    ProtectedFilesystemEvidenceStore,
)
from .ledger_opening_analysis import _shared_strings, _sheet_rows

_CUTOFF = date(2026, 8, 31)
_OBSERVED_CURRENT_BALANCE = Decimal("574451.39")
_CENT = Decimal("0.01")


def analyze_ar_aging_control(
    *,
    store: ProtectedFilesystemEvidenceStore,
    control_id: str,
    expected_raw_sha256: str,
) -> dict[str, object]:
    registration_path = store.root / "controls" / f"{control_id}.json"
    registration = store._read_json(registration_path)
    if registration.get("kind") != "ar_aging_detail":
        raise EvidenceStoreError("ar_aging_control_kind_invalid")
    if registration.get("accounting_basis") != "operational":
        raise EvidenceStoreError("ar_aging_control_basis_invalid")
    if registration.get("report_end_date") != _CUTOFF.isoformat():
        raise EvidenceStoreError("ar_aging_control_cutoff_invalid")
    if registration.get("raw_sha256") != expected_raw_sha256:
        raise EvidenceStoreError("ar_aging_control_digest_mismatch")
    source_path = store.root / "controls" / "raw" / f"{expected_raw_sha256}.xlsx"
    if hashlib.sha256(source_path.read_bytes()).hexdigest() != expected_raw_sha256:
        raise EvidenceStoreError("ar_aging_control_digest_mismatch")
    metrics = _metrics(source_path)
    if metrics["post_cutoff_rows"] != 0:
        raise EvidenceStoreError("ar_aging_control_contains_post_cutoff_rows")
    document: dict[str, object] = {
        "schema_version": "qbo-ar-aging-control-analysis/v1",
        "control_id": control_id,
        "registration_digest": hashlib.sha256(
            registration_path.read_bytes()
        ).hexdigest(),
        "raw_sha256": expected_raw_sha256,
        **metrics,
        "cutoff": _CUTOFF.isoformat(),
        "historical_reporting_basis": "CASH",
        "operational_ar_authority": "AGING_DETAIL_ACCEPTED_LEDGER_TIE_REQUIRED",
        "observed_current_balance": str(_OBSERVED_CURRENT_BALANCE),
        "cutoff_to_current_variance": str(
            (
                Decimal(str(metrics["open_balance"])) - _OBSERVED_CURRENT_BALANCE
            ).quantize(_CENT)
        ),
        "post_cutoff_modified_invoice": (
            "ONE_1250_CUTOFF_ITEM_PRESENT_IDENTITY_CROSSWALK_REQUIRED"
        ),
        "cash_reporting_effect": "NO_CHANGE",
        "next_control": "ACCRUAL_TRIAL_BALANCE_2026-08-31",
    }
    document["evidence_digest"] = _digest(document)
    analysis_digest = ControlEvidenceRegistry(store).register_authority_document(
        authority_id="qbo-cutoff-ar-aging-control-2026-08-31-v1",
        document=document,
    )
    return {
        "state": "AR_AGING_CONTROL_ACCEPTED_LEDGER_TIE_REQUIRED",
        "analysis_digest": analysis_digest,
        "raw_sha256": expected_raw_sha256,
        "customer_count": metrics["customer_count"],
        "item_count": metrics["item_count"],
        "invoice_count": metrics["invoice_count"],
        "payment_count": metrics["payment_count"],
        "deposit_count": metrics["deposit_count"],
        "open_balance": metrics["open_balance"],
        "next_report": "ACCRUAL_TRIAL_BALANCE_2026-08-31",
    }


def _metrics(path: Path) -> dict[str, object]:
    try:
        with ZipFile(path) as workbook:
            rows = _sheet_rows(workbook, _shared_strings(workbook))
    except (BadZipFile, KeyError) as error:
        raise EvidenceStoreError("ar_aging_workbook_invalid") from error
    strings = [value for row in rows for value in row.values()]
    if "A/R Aging Detail Report" not in strings or "As of Aug 31, 2026" not in strings:
        raise EvidenceStoreError("ar_aging_report_identity_invalid")
    header = next(
        (
            row
            for row in rows
            if {
                "Date",
                "Transaction type",
                "Customer full name",
                "Open balance",
            }.issubset(row.values())
        ),
        None,
    )
    if header is None:
        raise EvidenceStoreError("ar_aging_header_invalid")
    columns = {value: column for column, value in header.items()}
    bucket = "UNCLASSIFIED"
    bucket_counts: Counter[str] = Counter()
    bucket_balances: defaultdict[str, Decimal] = defaultdict(Decimal)
    type_counts: Counter[str] = Counter()
    type_amounts: defaultdict[str, Decimal] = defaultdict(Decimal)
    type_balances: defaultdict[str, Decimal] = defaultdict(Decimal)
    customers: set[str] = set()
    dates: list[date] = []
    item_count = negative_count = open_1250_count = 0
    for row in rows:
        if len(row) == 1 and 1 in row and row[1] != "TOTAL":
            bucket = row[1]
            continue
        try:
            transaction_date = _date(row.get(columns["Date"], ""))
        except ValueError:
            continue
        transaction_type = row.get(columns["Transaction type"], "")
        amount = _decimal(row.get(columns["Amount"], ""))
        open_balance = _decimal(row.get(columns["Open balance"], ""))
        customer = row.get(columns["Customer full name"], "")
        dates.append(transaction_date)
        customers.add(customer)
        item_count += 1
        negative_count += open_balance < 0
        open_1250_count += open_balance == Decimal(1250)
        bucket_counts[bucket] += 1
        bucket_balances[bucket] += open_balance
        type_counts[transaction_type] += 1
        type_amounts[transaction_type] += amount
        type_balances[transaction_type] += open_balance
    if not dates or not customers:
        raise EvidenceStoreError("ar_aging_items_missing")
    open_balance = sum(type_balances.values(), Decimal()).quantize(_CENT)
    report_total = next(
        (
            _decimal(row.get(columns["Open balance"], "")).quantize(_CENT)
            for row in rows
            if row.get(1) == "TOTAL"
        ),
        None,
    )
    if report_total is None or report_total != open_balance:
        raise EvidenceStoreError("ar_aging_total_mismatch")
    return {
        "report_title_verified": True,
        "report_cutoff_verified": True,
        "basis_authority": "OPERATIONAL_OPEN_BALANCE_VIEW",
        "customer_count": len(customers),
        "item_count": item_count,
        "earliest_transaction_date": min(dates).isoformat(),
        "latest_transaction_date": max(dates).isoformat(),
        "post_cutoff_rows": sum(item > _CUTOFF for item in dates),
        "negative_open_item_count": negative_count,
        "type_counts": dict(sorted(type_counts.items())),
        "invoice_count": type_counts["Invoice"],
        "payment_count": type_counts["Payment"],
        "deposit_count": type_counts["Deposit"],
        "type_amounts": {
            key: str(value.quantize(_CENT))
            for key, value in sorted(type_amounts.items())
        },
        "type_open_balances": {
            key: str(value.quantize(_CENT))
            for key, value in sorted(type_balances.items())
        },
        "aging_bucket_counts": dict(bucket_counts),
        "aging_bucket_balances": {
            key: str(value.quantize(_CENT)) for key, value in bucket_balances.items()
        },
        "open_balance": str(open_balance),
        "open_1250_item_count": open_1250_count,
    }


def _decimal(value: str) -> Decimal:
    try:
        return Decimal(value.replace(",", "").replace("$", "").strip() or "0")
    except InvalidOperation as error:
        raise EvidenceStoreError("ar_aging_amount_invalid") from error


def _date(value: str) -> date:
    month, day, year = (int(item) for item in value.split("/"))
    return date(year, month, day)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seal QBO cutoff A/R Aging control")
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--control-id", required=True)
    parser.add_argument("--raw-sha256", required=True)
    arguments = parser.parse_args()
    result = analyze_ar_aging_control(
        store=ProtectedFilesystemEvidenceStore(
            root=arguments.evidence_root,
            repository_root=arguments.repository_root,
        ),
        control_id=arguments.control_id,
        expected_raw_sha256=arguments.raw_sha256,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
