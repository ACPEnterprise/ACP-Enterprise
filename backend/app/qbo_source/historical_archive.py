"""Searchable, immutable projection of the sealed All County QBO exports.

This module deliberately models historical source evidence, not native ledger
entries.  Every returned record is bound to the custody file digest, source row
number, and normalized row contents.  Nothing here can post, update QuickBooks,
or manufacture a missing relationship.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal, cast

import xlrd  # type: ignore[import-untyped]

from .errors import QboEvidenceProjectionError
from .manual_archive import (
    _data_rows,
    _date,
    _mapping,
    _read_json,
    _required_text,
    _sha256,
    _verify_inventory,
    _xlsx_rows,
)

HistoricalKind = Literal[
    "all",
    "account",
    "customer",
    "vendor",
    "invoice",
    "transaction",
    "bank_activity",
]
HistoricalReport = Literal[
    "profit_and_loss",
    "balance_sheet",
    "trial_balance",
    "general_ledger",
    "cash_activity",
]


@dataclass(frozen=True, slots=True)
class Dataset:
    key: str
    label: str
    filename: str
    category: str
    header: str | None = None
    date_column: str | None = None
    transaction_type_column: str | None = None


_DATASETS = (
    Dataset(
        "accounts",
        "Chart of Accounts",
        "All County Plumbing and Leak_Account List.xlsx",
        "account",
        "Account Name",
    ),
    Dataset(
        "balance_sheet",
        "Balance Sheet",
        "All County Plumbing and Leak_Balance Sheet.xlsx",
        "financial_report",
    ),
    Dataset(
        "customers",
        "Customer directory",
        "All County Plumbing and Leak_Customer Contact List.xlsx",
        "customer",
        "Customer full name",
    ),
    Dataset(
        "general_ledger",
        "General Ledger",
        "All County Plumbing and Leak_General Ledger.xlsx",
        "transaction",
        "Transaction date",
        "Transaction date",
        "Transaction type",
    ),
    Dataset(
        "invoices",
        "Invoice history",
        "All County Plumbing and Leak_Invoice List by Date.xlsx",
        "invoice",
        "Transaction type",
        "Date",
        "Transaction type",
    ),
    Dataset(
        "profit_and_loss",
        "Profit and Loss",
        "All County Plumbing and Leak_Profit and Loss.xlsx",
        "financial_report",
    ),
    Dataset(
        "account_detail",
        "Transaction detail by account",
        "All County Plumbing and Leak_Transaction Detail by Account.xlsx",
        "transaction_control",
        "Transaction date",
        "Transaction date",
        "Transaction type",
    ),
    Dataset(
        "customer_transactions",
        "Transaction list by customer",
        "All County Plumbing and Leak_Transaction List by Customer.xlsx",
        "customer_transaction",
        "Transaction type",
        "Date",
        "Transaction type",
    ),
    Dataset(
        "vendor_transactions",
        "Transaction list by vendor",
        "All County Plumbing and Leak_Transaction List by Vendor.xlsx",
        "vendor_transaction",
        "Transaction type",
        "Date",
        "Transaction type",
    ),
    Dataset(
        "trial_balance",
        "Trial Balance",
        "All County Plumbing and Leak_Trial Balance.xlsx",
        "financial_report",
        "Account Name",
    ),
    Dataset(
        "vendors",
        "Vendor directory",
        "All County Plumbing and Leak_Vendor Contact List.xlsx",
        "vendor",
        "Vendor",
    ),
    Dataset(
        "amex_pending",
        "American Express pending feed",
        "American_Express.csv",
        "unposted_bank_feed",
    ),
    Dataset(
        "amex_pending_repeat",
        "American Express pending feed repeat export",
        "American_Express (1).csv",
        "unposted_bank_feed",
    ),
    Dataset(
        "payroll_deductions",
        "Payroll deductions and contributions",
        "AllCountyPlumbingAndLeak_DeductionsAndContributionsReport_11192026_1824.xls",
        "payroll",
    ),
    Dataset(
        "employees",
        "Employee details",
        "AllCountyPlumbingAndLeak_EmployeeDetails_11192026_1827.xls",
        "payroll",
    ),
    Dataset(
        "paychecks",
        "Paycheck history",
        "AllCountyPlumbingAndLeak_PaycheckHistory_11192026_1816.xls",
        "payroll",
    ),
    Dataset(
        "payroll_summary",
        "Payroll summary by employee",
        "AllCountyPlumbingAndLeak_PayrollSummaryByEmployee_11192026_1828.xls",
        "payroll",
    ),
    Dataset(
        "payroll_summary_duplicate",
        "Payroll summary duplicate export",
        "AllCountyPlumbingAndLeak_PayrollSummaryByEmployee_11192026_1814.xls",
        "payroll_duplicate",
    ),
    Dataset(
        "payroll_tax_liability",
        "Payroll tax liability",
        "AllCountyPlumbingAndLeak_PayrollTaxLiability_11192026_1823.xls",
        "payroll",
    ),
    Dataset(
        "payroll_tax_payments",
        "Payroll tax payments",
        "AllCountyPlumbingAndLeak_PayrollTaxPayments_11192026_1820.xls",
        "payroll",
    ),
    Dataset(
        "source_bundle",
        "Original accounting source archive",
        "All County Plumbing and Leak Nov 19, 2026.zip",
        "custody_bundle",
    ),
)

_SEARCH_DATASETS = {
    "account": "accounts",
    "customer": "customers",
    "vendor": "vendors",
    "invoice": "invoices",
    "transaction": "general_ledger",
    "bank_activity": "general_ledger",
}
_BANK_TRANSACTION_TYPES = frozenset(
    {
        "Check",
        "Credit Card Credit",
        "Credit Card Expense",
        "Credit Card Payment",
        "Deposit",
        "Expense",
        "Refund",
        "Tax Payment",
        "Transfer",
    }
)


def historical_archive_catalog(*, root: Path) -> dict[str, object]:
    root, manifest, register, inventory = _verified(root)
    inventory_by_name = {str(item["name"]): item for item in inventory}
    datasets: list[dict[str, object]] = []
    for dataset in _DATASETS:
        entry = inventory_by_name.get(dataset.filename)
        if entry is None:
            continue
        source = root / "raw" / dataset.filename
        count, start, end = _dataset_metrics(source, dataset)
        datasets.append(
            {
                "key": dataset.key,
                "label": dataset.label,
                "category": dataset.category,
                "source_file": dataset.filename,
                "source_sha256": str(entry["sha256"]),
                "source_bytes": _integer(entry["bytes"]),
                "record_count": count,
                "starts_on": start,
                "ends_on": end,
                "source_identity": "custody-file-sha256-plus-report-row",
            }
        )
    acquisition = _mapping(register.get("current_acquisition"))
    reconciliation = _mapping(register.get("report_reconciliation"))
    discrepancies = register.get("discrepancies")
    conflicts = discrepancies if isinstance(discrepancies, list) else []
    return {
        "contract_version": "qbo-historical-archive-catalog/v1",
        "authority": "QBO_HISTORICAL_SOURCE_EVIDENCE",
        "source_company": _required_text(
            _mapping(register.get("connection")), "company_name"
        ),
        "source_run_id": str(acquisition.get("run_id") or "qbo-manual-20261119"),
        "source_cutoff": str(acquisition.get("cutoff") or "2026-11-19"),
        "source_record_count": _integer(acquisition.get("record_count") or 0),
        "relationship_identity_count": _integer(
            acquisition.get("relationship_ids_preserved") or 0
        ),
        "source_manifest_sha256": str(acquisition.get("manifest_sha256") or ""),
        "bounded_snapshot_sha256": str(
            acquisition.get("bounded_snapshot_sha256") or ""
        ),
        "custody_manifest_sha256": _sha256(root / "custody-manifest.json"),
        "custody_set_sha256": _required_text(manifest, "custody_set_sha256"),
        "historical_basis": "cash",
        "currency": "USD",
        "datasets": datasets,
        "reconciliation_controls": dict(reconciliation),
        "exception_count": len(conflicts),
        "exceptions": conflicts,
        "limitations": [
            "report_row_identities_are_not_provider_record_ids",
            "source_attachments_are_not_present_in_the_preserved_exports",
            "detailed_payroll_api_records_are_not_available_under_accounting_scope",
            "historical_source_evidence_is_not_native_posting_authority",
        ],
        "mutation_authority": "none",
    }


def search_historical_archive(
    *,
    root: Path,
    kind: HistoricalKind,
    query: str | None,
    start_date: date | None,
    end_date: date | None,
    transaction_type: str | None,
    account: str | None,
    offset: int,
    limit: int,
) -> dict[str, object]:
    root, _, _, inventory = _verified(root)
    selected = (
        tuple(_SEARCH_DATASETS.values()) if kind == "all" else (_SEARCH_DATASETS[kind],)
    )
    inventory_by_name = {str(item["name"]): item for item in inventory}
    records: list[dict[str, object]] = []
    for key in selected:
        dataset = next(item for item in _DATASETS if item.key == key)
        entry = inventory_by_name[dataset.filename]
        records.extend(
            _records(
                root / "raw" / dataset.filename,
                dataset,
                source_sha256=str(entry["sha256"]),
            )
        )
    if kind == "bank_activity":
        records = [
            row
            for row in records
            if row.get("transaction_type") in _BANK_TRANSACTION_TYPES
        ]
    normalized_query = (query or "").strip().casefold()
    normalized_account = (account or "").strip().casefold()
    normalized_type = (transaction_type or "").strip().casefold()
    filtered: list[dict[str, object]] = []
    for record in records:
        record_date = _iso_date(record.get("transaction_date"))
        if start_date is not None and (record_date is None or record_date < start_date):
            continue
        if end_date is not None and (record_date is None or record_date > end_date):
            continue
        if (
            normalized_type
            and str(record.get("transaction_type") or "").casefold() != normalized_type
        ):
            continue
        if (
            normalized_account
            and normalized_account not in str(record.get("account") or "").casefold()
        ):
            continue
        if (
            normalized_query
            and normalized_query
            not in " ".join(
                str(value) for value in record.values() if value is not None
            ).casefold()
        ):
            continue
        filtered.append(record)
    filtered.sort(
        key=lambda row: (
            str(row.get("transaction_date") or ""),
            str(row.get("source_identity") or ""),
        ),
        reverse=True,
    )
    return {
        "contract_version": "qbo-historical-search/v1",
        "kind": kind,
        "total": len(filtered),
        "offset": offset,
        "limit": limit,
        "records": filtered[offset : offset + limit],
        "mutation_authority": "none",
    }


def historical_payroll_records(
    *, root: Path, query: str | None, offset: int, limit: int
) -> dict[str, object]:
    root, _, _, inventory = _verified(root)
    dataset = next(item for item in _DATASETS if item.key == "paychecks")
    entry = next(item for item in inventory if item.get("name") == dataset.filename)
    rows = _xls_data_rows(root / "raw" / dataset.filename)
    records = [
        _historical_record(
            dataset=dataset,
            source_sha256=str(entry["sha256"]),
            row_number=row_number,
            values=values,
            record_kind="payroll",
            fields={
                "transaction_date": values.get("Pay date"),
                "name": values.get("Name"),
                "amount": values.get("Total pay"),
                "net_amount": values.get("Net pay"),
                "payment_method": values.get("Pay method"),
                "reference": values.get("Check Number"),
                "status": values.get("Status"),
            },
        )
        for row_number, values in rows
    ]
    normalized = (query or "").strip().casefold()
    if normalized:
        records = [
            record
            for record in records
            if normalized
            in " ".join(
                str(value) for value in record.values() if value is not None
            ).casefold()
        ]
    return {
        "contract_version": "qbo-historical-payroll/v1",
        "total": len(records),
        "offset": offset,
        "limit": limit,
        "records": records[offset : offset + limit],
        "limitations": [
            "historical_source_evidence_only",
            "no_payroll_execution_authority",
            "payroll_summary_and_paycheck_history_coverage_conflict_preserved",
        ],
        "mutation_authority": "none",
    }


def historical_report(
    *,
    root: Path,
    report: HistoricalReport,
    start_date: date | None,
    end_date: date | None,
) -> dict[str, object]:
    root, _, register, inventory = _verified(root)
    inventory_by_name = {str(item["name"]): item for item in inventory}
    dataset_key = {
        "profit_and_loss": "profit_and_loss",
        "balance_sheet": "balance_sheet",
        "trial_balance": "trial_balance",
        "general_ledger": "general_ledger",
        "cash_activity": "general_ledger",
    }[report]
    dataset = next(item for item in _DATASETS if item.key == dataset_key)
    entry = inventory_by_name[dataset.filename]
    if report in {"general_ledger", "cash_activity"}:
        kind: HistoricalKind = (
            "bank_activity" if report == "cash_activity" else "transaction"
        )
        result = search_historical_archive(
            root=root,
            kind=kind,
            query=None,
            start_date=start_date,
            end_date=end_date,
            transaction_type=None,
            account=None,
            offset=0,
            limit=50000,
        )
        records = cast(list[Mapping[str, object]], result["records"])
        amount_total = sum(
            (
                _decimal(item.get("amount"))
                for item in records
                if isinstance(item, Mapping)
            ),
            Decimal(0),
        )
        return {
            "contract_version": "qbo-historical-report/v1",
            "report_type": report,
            "title": dataset.label,
            "basis": "cash",
            "currency": "USD",
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "columns": [
                "Date",
                "Type",
                "Number",
                "Name",
                "Description",
                "Account",
                "Split",
                "Amount",
                "Balance",
            ],
            "rows": records,
            "record_count": result["total"],
            "amount_total": format(amount_total.quantize(Decimal("0.01")), "f"),
            "source_sha256": str(entry["sha256"]),
            "source_mode": "sealed_report_rows",
            "mutation_authority": "none",
        }
    rows = _xlsx_rows(root / "raw" / dataset.filename)
    projected = [
        {"row_number": index, "cells": [value or "" for value in row]}
        for index, row in enumerate(rows, 1)
        if any(value not in {None, ""} for value in row)
    ]
    acquisition = _mapping(register.get("current_acquisition"))
    return {
        "contract_version": "qbo-historical-report/v1",
        "report_type": report,
        "title": dataset.label,
        "basis": "cash",
        "currency": "USD",
        "start_date": "2026-01-01" if report == "profit_and_loss" else None,
        "end_date": str(acquisition.get("cutoff") or "2026-11-19"),
        "columns": [],
        "rows": projected,
        "record_count": len(projected),
        "source_sha256": str(entry["sha256"]),
        "source_mode": "sealed_source_report",
        "requested_period_matches_source": (
            report != "profit_and_loss"
            or (
                start_date in {None, date(2026, 1, 1)}
                and end_date in {None, date(2026, 11, 19)}
            )
        ),
        "mutation_authority": "none",
    }


def _verified(
    root: Path,
) -> tuple[Path, dict[str, object], dict[str, object], list[Mapping[str, object]]]:
    resolved = root.expanduser().resolve()
    manifest = _read_json(resolved / "custody-manifest.json")
    if manifest.get("contract") != "qbo-manual-archive-custody/v1":
        raise QboEvidenceProjectionError("manual_archive_contract_invalid")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise QboEvidenceProjectionError("manual_archive_file_inventory_invalid")
    _verify_inventory(resolved, files)
    inventory = [item for item in files if isinstance(item, Mapping)]
    if len(inventory) != len(files):
        raise QboEvidenceProjectionError("manual_archive_file_inventory_invalid")
    return (
        resolved,
        manifest,
        _read_json(resolved / "reconciliation-register.json"),
        inventory,
    )


def _dataset_metrics(
    path: Path, dataset: Dataset
) -> tuple[int, str | None, str | None]:
    if path.suffix == ".xlsx":
        if dataset.header is None:
            source_rows = [
                row
                for row in _xlsx_rows(path)
                if any(value not in {None, ""} for value in row)
            ]
            return len(source_rows), None, None
        mapped_rows = _valid_rows(
            dataset, _data_rows(path, header_contains=dataset.header)
        )
        dates = [_iso_date(row.get(dataset.date_column or "")) for row in mapped_rows]
        actual_dates = [value for value in dates if value is not None]
        if dataset.date_column:
            mapped_rows = [
                row
                for row in mapped_rows
                if _iso_date(row.get(dataset.date_column)) is not None
            ]
        return (
            len(mapped_rows),
            min(actual_dates).isoformat() if actual_dates else None,
            max(actual_dates).isoformat() if actual_dates else None,
        )
    if path.suffix == ".xls":
        xls_rows = _xls_data_rows(path)
        dates = [
            _iso_date(row.get("Pay date") or row.get("Payment date"))
            for _, row in xls_rows
        ]
        actual_dates = [value for value in dates if value is not None]
        return (
            len(xls_rows),
            min(actual_dates).isoformat() if actual_dates else None,
            max(actual_dates).isoformat() if actual_dates else None,
        )
    if path.suffix == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as stream:
            return sum(1 for _ in csv.DictReader(stream)), None, None
    return 1, None, None


def _records(
    path: Path, dataset: Dataset, *, source_sha256: str
) -> list[dict[str, object]]:
    if dataset.header is None:
        return []
    source_rows = _valid_rows(dataset, _data_rows(path, header_contains=dataset.header))
    records: list[dict[str, object]] = []
    for row_number, values in enumerate(source_rows, 1):
        if dataset.date_column and _iso_date(values.get(dataset.date_column)) is None:
            continue
        if dataset.key == "accounts":
            fields = {
                "name": values.get("Account Name"),
                "account": values.get("Account Name"),
                "account_type": values.get("Type"),
                "account_subtype": values.get("Detail type"),
                "description": values.get("Description"),
                "amount": values.get("Total balance"),
            }
        elif dataset.key == "customers":
            fields = {
                "name": values.get("Customer full name"),
                "phone": values.get("Phone numbers"),
                "email": values.get("Email"),
                "description": values.get("Full name"),
                "address": values.get("Bill address"),
            }
        elif dataset.key == "vendors":
            fields = {
                "name": values.get("Vendor") or values.get("Company"),
                "description": values.get("Company"),
                "phone": values.get("Phone numbers"),
                "email": values.get("Email"),
                "address": values.get("Billing address"),
                "reference": values.get("Account #"),
                "status": values.get("Track 1099"),
            }
        elif dataset.key == "invoices":
            fields = {
                "transaction_date": _source_date(values.get("Date")),
                "transaction_type": values.get("Transaction type"),
                "reference": values.get("Num"),
                "name": values.get("Name"),
                "description": values.get("Memo"),
                "due_date": _source_date(values.get("Due date")),
                "amount": values.get("Amount"),
                "open_balance": values.get("Open balance"),
            }
        else:
            fields = {
                "transaction_date": _source_date(values.get("Transaction date")),
                "transaction_type": values.get("Transaction type"),
                "reference": values.get("Num"),
                "name": values.get("Name"),
                "description": values.get("Description"),
                "account": values.get("Distribution account"),
                "split_account": values.get("Split"),
                "amount": values.get("Amount"),
                "balance": values.get("Balance"),
            }
        records.append(
            _historical_record(
                dataset=dataset,
                source_sha256=source_sha256,
                row_number=row_number,
                values=values,
                record_kind=dataset.category,
                fields=fields,
            )
        )
    return records


def _valid_rows(
    dataset: Dataset, rows: Sequence[Mapping[str, object]]
) -> list[Mapping[str, object]]:
    if dataset.key == "accounts":
        return [row for row in rows if row.get("Account Name") and row.get("Type")]
    if dataset.key == "customers":
        return [
            row
            for row in rows
            if row.get("Customer full name")
            and not str(row.get("Customer full name")).lstrip().startswith("Thursday,")
        ]
    if dataset.key == "vendors":
        return [
            row
            for row in rows
            if row.get("Vendor") and row.get("Track 1099") is not None
        ]
    return list(rows)


def _historical_record(
    *,
    dataset: Dataset,
    source_sha256: str,
    row_number: int,
    values: Mapping[str, object],
    record_kind: str,
    fields: Mapping[str, object],
) -> dict[str, object]:
    encoded = json.dumps(
        values, sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    row_digest = hashlib.sha256(encoded).hexdigest()
    identity = hashlib.sha256(
        f"{source_sha256}:{row_number}:{row_digest}".encode()
    ).hexdigest()
    return {
        "source_identity": identity,
        "identity_kind": "custody-file-sha256-plus-report-row",
        "record_kind": record_kind,
        "dataset": dataset.key,
        "source_row_number": row_number,
        "source_file_sha256": source_sha256,
        "row_sha256": row_digest,
        **{key: value for key, value in fields.items() if value not in {None, ""}},
    }


def _xls_data_rows(path: Path) -> list[tuple[int, dict[str, object]]]:
    try:
        sheet = xlrd.open_workbook(path, on_demand=True).sheet_by_index(0)
    except (OSError, xlrd.XLRDError) as error:
        raise QboEvidenceProjectionError("manual_archive_xls_unreadable") from error
    header_index = next(
        (
            index
            for index in range(min(sheet.nrows, 12))
            if sum(bool(str(value).strip()) for value in sheet.row_values(index)) >= 2
            and any(
                str(value).strip()
                in {
                    "Pay date",
                    "Payment date",
                    "Item",
                    "Personal info",
                    "Description",
                    "Tax types",
                }
                for value in sheet.row_values(index)
            )
        ),
        None,
    )
    if header_index is None:
        raise QboEvidenceProjectionError("manual_archive_report_header_missing")
    headers = [str(value).strip() for value in sheet.row_values(header_index)]
    rows: list[tuple[int, dict[str, object]]] = []
    for index in range(header_index + 1, sheet.nrows):
        values = sheet.row_values(index)
        if not any(str(value).strip() for value in values):
            continue
        rows.append(
            (
                index + 1,
                {
                    header: values[column]
                    for column, header in enumerate(headers)
                    if header and column < len(values)
                },
            )
        )
    return rows


def _iso_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value:
        return None
    normalized = _date(value)
    if normalized is None:
        return None
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        return None


def _source_date(value: object) -> str | None:
    return _date(value if isinstance(value, str) else None)


def _decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value or "0").replace(",", "").replace("$", ""))
    except (InvalidOperation, ValueError):
        return Decimal(0)


def _integer(value: object) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def transaction_type_counts(*, root: Path) -> dict[str, int]:
    """Return the canonical General Ledger transaction-type control."""
    root, _, _, inventory = _verified(root)
    dataset = next(item for item in _DATASETS if item.key == "general_ledger")
    entry = next(item for item in inventory if item.get("name") == dataset.filename)
    return dict(
        sorted(
            Counter(
                str(row.get("transaction_type") or "UNSPECIFIED")
                for row in _records(
                    root / "raw" / dataset.filename,
                    dataset,
                    source_sha256=str(entry["sha256"]),
                )
            ).items()
        )
    )
