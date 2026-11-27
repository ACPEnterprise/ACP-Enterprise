"""Read-only projection of the sealed QuickBooks manual archive.

The November 19 archive is an evidence package of exported reports, not the
bounded API-envelope package used by native QBO admission.  This module keeps
that distinction explicit: it validates custody, projects source-backed
history for owner review, and never creates ACP ledger truth or calls QBO.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast
from xml.etree import ElementTree
from zipfile import ZipFile

from .errors import QboEvidenceProjectionError

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def manual_archive_available(root: Path) -> bool:
    return (root / "custody-manifest.json").is_file() and (
        root / "raw" / "All County Plumbing and Leak_Account List.xlsx"
    ).is_file()


def manual_archive_readiness(*, root: Path) -> dict[str, object]:
    """Return custody-backed source counts without parsing or admitting records."""
    root = root.expanduser().resolve()
    manifest = _read_json(root / "custody-manifest.json")
    if manifest.get("contract") != "qbo-manual-archive-custody/v1":
        raise QboEvidenceProjectionError("manual_archive_contract_invalid")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise QboEvidenceProjectionError("manual_archive_file_inventory_invalid")
    _verify_inventory(root, files)
    register = _read_json(root / "reconciliation-register.json")
    acquisition = _mapping(register.get("current_acquisition"))
    counts = acquisition.get("counts")
    if not isinstance(counts, Mapping):
        raise QboEvidenceProjectionError("manual_archive_acquisition_counts_invalid")
    counts = cast(Mapping[str, Any], counts)
    families = [
        {"source_family": str(family), "total_source": int(total)}
        for family, total in sorted(counts.items())
    ]
    return {
        "available": True,
        "reason": "Verified sealed manual QuickBooks archive; native bounded-envelope admission remains separate.",
        "source_run_id": str(acquisition.get("run_id") or "qbo-manual-20261119"),
        "source_manifest_sha256": _sha256(root / "custody-manifest.json"),
        "acquired_at": str(manifest.get("sealed_at") or ""),
        "total_source_records": int(
            cast(Any, acquisition.get("record_count"))
            or sum(int(cast(Any, v)) for v in counts.values())
        ),
        "source_families": families,
        "evidence_mode": "sealed_manual_archive",
        "native_admission_ready": False,
    }


def project_manual_archive(*, root: Path, basis: str) -> dict[str, object]:
    root = root.expanduser().resolve()
    manifest = _read_json(root / "custody-manifest.json")
    if manifest.get("contract") != "qbo-manual-archive-custody/v1":
        raise QboEvidenceProjectionError("manual_archive_contract_invalid")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise QboEvidenceProjectionError("manual_archive_file_inventory_invalid")
    _verify_inventory(root, files)

    register = _read_json(root / "reconciliation-register.json")
    connection = _mapping(register.get("connection"))
    acquisition = _mapping(register.get("current_acquisition"))
    reconciliation = _mapping(register.get("report_reconciliation"))
    manifest_digest = _sha256(root / "custody-manifest.json")
    custody_digest = _required_text(manifest, "custody_set_sha256")
    company_name = _required_text(connection, "company_name")
    realm_id = _required_text(connection, "realm_id")
    company_identity = hashlib.sha256(
        f"historical:{realm_id}:{company_name}".encode()
    ).hexdigest()
    as_of = str(acquisition.get("cutoff") or "2026-11-19")
    acquired_at = str(
        manifest.get("sealed_at") or datetime.now(timezone.utc).isoformat()
    )

    account_rows = [
        row
        for row in _data_rows(
            root / "raw" / "All County Plumbing and Leak_Account List.xlsx",
            header_contains="Account Name",
        )
        if row.get("Account Name") and row.get("Type")
    ]
    invoice_rows = [
        row
        for row in _data_rows(
            root / "raw" / "All County Plumbing and Leak_Invoice List by Date.xlsx",
            header_contains="Transaction type",
        )
        if row.get("Transaction type") == "Invoice"
    ]
    vendor_rows = [
        row
        for row in _data_rows(
            root / "raw" / "All County Plumbing and Leak_Vendor Contact List.xlsx",
            header_contains="Vendor",
        )
        if row.get("Vendor") and row.get("Track 1099") is not None
    ]
    accounts = [_account(row, index) for index, row in enumerate(account_rows)]
    invoices: list[dict[str, Any]] = [
        _invoice(row, index) for index, row in enumerate(invoice_rows)
    ]
    vendors = [_vendor(row, index) for index, row in enumerate(vendor_rows)]
    report_controls = _report_controls(root, as_of, basis)
    discrepancies = register.get("discrepancies")
    conflicts = _conflicts(discrepancies)
    counts = acquisition.get("counts")
    entity_counts = dict(counts) if isinstance(counts, Mapping) else {}
    open_total = sum(
        (
            Decimal(str(item["open_balance"]["amount"]))
            for item in invoices
            if item["open_balance"]["amount"] is not None
        ),
        Decimal(0),
    )
    return {
        "contract_version": "qbo-accounting-evidence/v1",
        "source": "quickbooks_online",
        "mode": "historical",
        "provider_environment": "production",
        "company_identity_sha256": company_identity,
        "realm_company_identity": company_identity,
        "company_info_verified_at": connection.get("verified_at"),
        "source_manifest_sha256": manifest_digest,
        "source_company_label": company_name,
        "source_company_id_masked": _masked(realm_id),
        "accounting_basis": basis,
        "as_of": as_of,
        "acquired_at": acquired_at,
        "refresh_state": "available",
        "provider_authorization": "historical_custody_verified",
        "evidence_mode": "sealed_manual_archive",
        "completeness": "complete",
        "entity_counts": entity_counts,
        "page_counts": {},
        "catalog_dispositions": [],
        "conflicts": conflicts,
        "snapshot_id": str(acquisition.get("run_id") or "qbo-manual-20261119"),
        "snapshot_digest": custody_digest,
        "is_live": False,
        "limitations": [
            "sealed_manual_report_archive",
            "source_reported_not_posted_acp_ledger",
            "native_qbo_record_envelopes_not_available_for_admission",
            "known_reconciliation_exceptions_preserved",
            "missing_values_are_not_zero",
        ],
        "accounts": accounts,
        "invoices": invoices,
        "ar": {
            "total_open": _amount(open_total),
            "invoice_evidence_count": len(invoices),
            "open_invoice_count": sum(
                1
                for item in invoices
                if Decimal(str(item["open_balance"]["amount"] or 0)) > 0
            ),
            "closed_invoice_count": sum(
                1
                for item in invoices
                if Decimal(str(item["open_balance"]["amount"] or 0)) <= 0
            ),
            "current": _amount(None),
            "overdue": _amount(None),
        },
        "payments": [],
        "vendors": vendors,
        "bills": [],
        "reports": report_controls,
        "records": [],
        "mutation_authority": "none",
        "source_reconciliation": reconciliation,
        "historical_reconciliation": _historical_reconciliation(
            acquisition=acquisition,
            report_reconciliation=reconciliation,
            conflicts=conflicts,
        ),
    }


def project_manual_profit_and_loss(
    *, root: Path, start_date: str, end_date: str, basis: str
) -> dict[str, object]:
    """Project the sealed P&L workbook without promoting it to the ACP ledger."""
    root = root.expanduser().resolve()
    manifest = _read_json(root / "custody-manifest.json")
    if manifest.get("contract") != "qbo-manual-archive-custody/v1":
        raise QboEvidenceProjectionError("manual_archive_contract_invalid")
    pnl_files = manifest.get("files", [])
    if not isinstance(pnl_files, list):
        raise QboEvidenceProjectionError("manual_archive_file_inventory_invalid")
    _verify_inventory(root, pnl_files)
    register = _read_json(root / "reconciliation-register.json")
    connection = _mapping(register.get("connection"))
    company_name = _required_text(connection, "company_name")
    realm_id = _required_text(connection, "realm_id")
    raw_rows = _xlsx_rows(
        root / "raw" / "All County Plumbing and Leak_Profit and Loss.xlsx"
    )
    header_index = next(
        (
            index
            for index, row in enumerate(raw_rows)
            if len(row) > 1 and row[1] == "Total"
        ),
        None,
    )
    if header_index is None:
        raise QboEvidenceProjectionError("manual_archive_report_header_missing")
    rows = [
        {"Account": row[0], "Total": row[1] if len(row) > 1 else None}
        for row in raw_rows[header_index + 1 :]
    ]
    projected = [
        {
            "kind": "data",
            "depth": 0,
            "values": [
                str(row.get("Account") or row.get("") or ""),
                str(row.get("Total") or ""),
            ],
        }
        for row in rows
        if any(value not in {None, ""} for value in row.values())
    ]
    raw_digest = _sha256(
        root / "raw" / "All County Plumbing and Leak_Profit and Loss.xlsx"
    )
    return {
        "contract_version": "qbo-source-backed-financial-report/v1",
        "report_type": "profit_and_loss",
        "authority": "QBO_SOURCE_BACKED",
        "provider_environment": "production",
        "source": "QuickBooks Online manual archive",
        "source_company": company_name,
        "realm_id": realm_id,
        "start_date": start_date,
        "end_date": end_date,
        "accounting_basis": basis,
        "currency": "USD",
        "source_as_of": str(
            _mapping(register.get("current_acquisition")).get("cutoff") or end_date
        ),
        "acquired_at": str(
            manifest.get("sealed_at") or datetime.now(timezone.utc).isoformat()
        ),
        "columns": ["Account", "Total"],
        "rows": projected,
        "source_digest": raw_digest,
        "accepted_as_acp_accounting": False,
        "mutation_authority": "none",
        "limitations": [
            "sealed_manual_report_archive",
            "report_basis_is_provider_export_metadata",
        ],
    }


def project_manual_aged_receivables(
    *, root: Path, report_date: str
) -> dict[str, object]:
    """Project read-only A/R aging from the sealed invoice archive.

    The manual archive is source-backed evidence, not ACP ledger truth.  Aging
    is calculated only from invoice open balances and due dates present in the
    verified invoice workbook; payments and credits without an invoice link
    remain disclosed in the archive reconciliation exceptions.
    """
    projected = project_manual_archive(root=root, basis="accrual")
    invoices = projected.get("invoices")
    if not isinstance(invoices, list):
        raise QboEvidenceProjectionError("manual_archive_invoice_projection_invalid")
    ar = projected.get("ar")
    if not isinstance(ar, Mapping):
        raise QboEvidenceProjectionError("manual_archive_ar_projection_invalid")

    try:
        cutoff = datetime.fromisoformat(report_date).date()
    except ValueError as error:
        raise QboEvidenceProjectionError(
            "manual_archive_report_date_invalid"
        ) from error

    current = Decimal(0)
    overdue = Decimal(0)
    for invoice in invoices:
        if not isinstance(invoice, Mapping):
            raise QboEvidenceProjectionError(
                "manual_archive_invoice_projection_invalid"
            )
        balance = invoice.get("open_balance")
        if not isinstance(balance, Mapping):
            continue
        amount = balance.get("amount")
        if amount in {None, ""}:
            continue
        try:
            open_balance = Decimal(str(amount))
        except (InvalidOperation, ValueError) as error:
            raise QboEvidenceProjectionError(
                "manual_archive_invoice_balance_invalid"
            ) from error
        if open_balance <= 0:
            continue
        due_date = invoice.get("due_date")
        if isinstance(due_date, str):
            try:
                due = datetime.fromisoformat(due_date).date()
            except ValueError:
                due = None
        else:
            due = None
        if due is not None and due >= cutoff:
            current += open_balance
        else:
            overdue += open_balance

    register = _read_json(root / "reconciliation-register.json")
    connection = _mapping(register.get("connection"))
    net_open_ar = _mapping(ar["total_open"])
    amount = net_open_ar.get("amount")
    if not isinstance(amount, str):
        raise QboEvidenceProjectionError("manual_archive_ar_total_invalid")
    source_digest = str(projected["source_manifest_sha256"])
    return {
        "contract_version": "qbo-source-backed-ar-summary/v1",
        "authority": "QBO_SOURCE_BACKED",
        "provider_environment": "production",
        "source": "QuickBooks Online manual archive A/R evidence",
        "source_company": _required_text(connection, "company_name"),
        "realm_id": _required_text(connection, "realm_id"),
        "report_date": report_date,
        "currency": "USD",
        "source_as_of": str(
            _mapping(register.get("current_acquisition")).get("cutoff") or report_date
        ),
        "acquired_at": str(
            _read_json(root / "custody-manifest.json").get("sealed_at")
            or datetime.now(timezone.utc).isoformat()
        ),
        # This is the gross invoice Balance total.  It intentionally uses the
        # provider contract's scalar shape while the boolean below prevents a
        # client from representing it as net of credits/unapplied payments.
        "net_open_ar": amount,
        "current": _amount(current),
        "overdue": _amount(overdue),
        "invoice_evidence_count": ar["invoice_evidence_count"],
        "open_invoice_count": ar["open_invoice_count"],
        "includes_customer_credits_and_unapplied_payments": False,
        "source_digest": source_digest,
        "source_manifest_sha256": source_digest,
        "accepted_as_acp_accounting": False,
        "mutation_authority": "none",
        "limitations": [
            "sealed_manual_report_archive",
            "invoice_open_balances_only",
            "unapplied_payments_and_credits_require_account_level_bridge",
            "source_reported_not_posted_acp_ledger",
        ],
    }


def _verify_inventory(root: Path, files: list[object]) -> None:
    for entry in files:
        if not isinstance(entry, Mapping):
            raise QboEvidenceProjectionError("manual_archive_file_inventory_invalid")
        name = entry.get("name")
        expected = entry.get("sha256")
        expected_bytes = entry.get("bytes")
        if (
            not isinstance(name, str)
            or "/" in name
            or not isinstance(expected, str)
            or not isinstance(expected_bytes, (int, str))
        ):
            raise QboEvidenceProjectionError("manual_archive_file_inventory_invalid")
        path = root / (Path("raw") / name if name != "custody-manifest.json" else name)
        if not path.is_file() or path.stat().st_size != int(expected_bytes):
            raise QboEvidenceProjectionError("manual_archive_file_inventory_mismatch")
        if _sha256(path) != expected:
            raise QboEvidenceProjectionError("manual_archive_file_digest_mismatch")


def _data_rows(path: Path, *, header_contains: str) -> list[dict[str, str | None]]:
    rows = _xlsx_rows(path)
    header_index = next(
        (index for index, row in enumerate(rows) if header_contains in row), None
    )
    if header_index is None:
        raise QboEvidenceProjectionError("manual_archive_report_header_missing")
    headers = rows[header_index]
    result = []
    for row in rows[header_index + 1 :]:
        if not any(value not in {None, ""} for value in row):
            continue
        result.append(
            {
                header: row[index] if index < len(row) else None
                for index, header in enumerate(headers)
                if header
            }
        )
    return result


def _xlsx_rows(path: Path) -> list[list[str | None]]:
    try:
        with ZipFile(path) as archive:
            shared: list[str] = []
            try:
                root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
                for item in root.findall(_NS + "si"):
                    shared.append(
                        "".join(text.text or "" for text in item.iter(_NS + "t"))
                    )
            except KeyError:
                pass
            sheet = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    except (OSError, KeyError, ElementTree.ParseError) as error:
        raise QboEvidenceProjectionError("manual_archive_xlsx_unreadable") from error
    rows: list[list[str | None]] = []
    for row in sheet.findall(".//" + _NS + "row"):
        cells: dict[int, str | None] = {}
        max_column = 0
        for cell in row.findall(_NS + "c"):
            reference = str(cell.get("r") or "")
            column = 0
            for character in reference:
                if not character.isalpha():
                    break
                column = column * 26 + ord(character.upper()) - ord("A") + 1
            max_column = max(max_column, column)
            value = cell.find(_NS + "v")
            text = None if value is None else value.text
            if cell.get("t") == "s" and text is not None:
                text = shared[int(text)]
            cells[column] = text
        rows.append([cells.get(index) for index in range(1, max_column + 1)])
    return rows


def _account(row: Mapping[str, str | None], index: int) -> dict[str, object]:
    return {
        "source_id": f"manual-account-{index + 1}",
        "name": row.get("Account Name") or "Unnamed account",
        "account_type": row.get("Type") or "Unavailable",
        "account_subtype": row.get("Detail type"),
        "balance": _amount(row.get("Total balance")),
    }


def _invoice(row: Mapping[str, str | None], index: int) -> dict[str, Any]:
    return {
        "source_id": f"manual-invoice-{index + 1}",
        "document_number": row.get("Num"),
        "customer_label": row.get("Name"),
        "transaction_date": _date(row.get("Date")),
        "due_date": _date(row.get("Due date")),
        "source_status": row.get("Transaction type"),
        "total": _amount(row.get("Amount")),
        "open_balance": _amount(row.get("Open balance")),
    }


def _vendor(row: Mapping[str, str | None], index: int) -> dict[str, object]:
    return {
        "source_id": f"manual-vendor-{index + 1}",
        "name": row.get("Vendor") or row.get("Company") or "Unnamed vendor",
        "company_name": row.get("Company"),
    }


def _report_controls(root: Path, as_of: str, basis: str) -> list[dict[str, object]]:
    labels = (
        ("balance_sheet", "Balance Sheet"),
        ("profit_and_loss", "Profit and Loss"),
        ("trial_balance", "Trial Balance"),
        ("general_ledger", "General Ledger"),
        ("journal", "Journal"),
    )
    return [
        {
            "report_key": key,
            "label": label,
            "basis": basis,
            "as_of": as_of,
            "state": "available",
            "limitation": "Sealed source report; not posted to ACP ledger.",
        }
        for key, label in labels
        if (root / "raw" / f"All County Plumbing and Leak_{label}.xlsx").is_file()
        or key == "journal"
    ]


def _conflicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    conflicts: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        evidence = [
            {"name": str(key), "value": str(item[key])}
            for key in sorted(item)
            if key not in {"id", "classification", "description", "next_action"}
            and item[key] is not None
        ]
        conflicts.append(
            {
                "conflict_id": str(item.get("id") or "unknown"),
                "subject_label": "All County historical accounting",
                "fact_name": str(item.get("classification") or "reconciliation"),
                "state": "unresolved",
                "source_assertions": [],
                "limitation": str(
                    item.get("description") or "Source exception preserved."
                ),
                "next_action": str(
                    item.get("next_action") or "Retain for explicit accounting review."
                ),
                "evidence": evidence,
            }
        )
    return conflicts


def _historical_reconciliation(
    *,
    acquisition: Mapping[str, object],
    report_reconciliation: Mapping[str, object],
    conflicts: list[dict[str, object]],
) -> dict[str, object]:
    """Project non-PII acquisition controls for authenticated operator review."""

    counts = _mapping(acquisition.get("counts"))
    invoice = _mapping(acquisition.get("invoice"))
    payment = _mapping(acquisition.get("payment"))
    return {
        "state": "RECONCILED_WITH_DISCLOSED_EXCEPTIONS",
        "source_record_count": int(cast(Any, acquisition.get("record_count")) or 0),
        "relationship_id_count": int(
            cast(Any, acquisition.get("relationship_ids_preserved")) or 0
        ),
        "conflict_count": len(conflicts),
        "customer_count": int(cast(Any, counts.get("customer")) or 0),
        "invoice_count": int(cast(Any, counts.get("invoice")) or 0),
        "invoice_line_count": int(cast(Any, invoice.get("line_count")) or 0),
        "invoice_open_balance": _amount(invoice.get("open_balance")),
        "payment_count": int(cast(Any, counts.get("payment")) or 0),
        "payment_total": _amount(payment.get("total_amount")),
        "payment_invoice_links": int(cast(Any, payment.get("invoice_links")) or 0),
        "missing_payment_invoice_links": int(
            cast(Any, payment.get("missing_linked_invoice_ids")) or 0
        ),
        "unlinked_payment_count": int(cast(Any, payment.get("without_links")) or 0),
        "unlinked_payment_total": _amount(payment.get("without_links_total")),
        "provider_unapplied_amount": _amount(payment.get("unapplied_amount")),
        "controls": dict(report_reconciliation),
        "mutation_authority": "none",
    }


def _amount(value: object) -> dict[str, object]:
    if value is None or value == "":
        return {"amount": None, "currency": "USD", "state": "unavailable"}
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return {"amount": None, "currency": "USD", "state": "unavailable"}
    return {"amount": format(amount, "f"), "currency": "USD", "state": "available"}


def _date(value: str | None) -> str | None:
    if not value:
        return None
    match = _DATE_RE.fullmatch(value.strip())
    return (
        f"{match.group(3)}-{int(match.group(1)):02d}-{int(match.group(2)):02d}"
        if match
        else value
    )


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise QboEvidenceProjectionError("manual_archive_register_invalid")
    return value


def _read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise QboEvidenceProjectionError("manual_archive_json_unreadable") from error
    if not isinstance(value, dict):
        raise QboEvidenceProjectionError("manual_archive_json_invalid")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_text(value: Mapping[str, object], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise QboEvidenceProjectionError("manual_archive_register_invalid")
    return result


def _masked(value: str) -> str:
    return f"…{value[-4:]}" if len(value) > 4 else value
