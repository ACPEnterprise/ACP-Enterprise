"""Safe mechanical analysis of a registered QuickBooks General Ledger XLSX."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from .evidence import ControlEvidenceRegistry, EvidenceStoreError
from .evidence import ProtectedFilesystemEvidenceStore

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_OPENING = re.compile(
    r"\b(opening balance|beginning balance|balance forward|opening entry)\b",
    re.IGNORECASE,
)


def analyze_registered_general_ledger(
    *,
    store: ProtectedFilesystemEvidenceStore,
    control_id: str,
    expected_raw_sha256: str,
) -> dict[str, object]:
    registration_path = store.root / "controls" / f"{control_id}.json"
    registration = store._read_json(registration_path)
    if registration.get("kind") != "general_ledger":
        raise EvidenceStoreError("ledger_control_kind_invalid")
    if str(registration.get("accounting_basis", "")).lower() != "accrual":
        raise EvidenceStoreError("ledger_control_basis_invalid")
    if registration.get("raw_sha256") != expected_raw_sha256:
        raise EvidenceStoreError("ledger_control_digest_mismatch")
    parameters = registration.get("safe_report_parameters")
    if not isinstance(parameters, dict) or parameters != {
        "start_date": "2021-07-07",
        "end_date": "2022-12-31",
    }:
        raise EvidenceStoreError("ledger_control_period_invalid")
    workbook_path = store.root / "controls" / "raw" / f"{expected_raw_sha256}.xlsx"
    if hashlib.sha256(workbook_path.read_bytes()).hexdigest() != expected_raw_sha256:
        raise EvidenceStoreError("ledger_control_digest_mismatch")
    metrics = _workbook_metrics(workbook_path)
    if not metrics["report_title_verified"] or not metrics["period_verified"]:
        raise EvidenceStoreError("ledger_report_identity_invalid")
    document: dict[str, object] = {
        "schema_version": "qbo-ledger-opening-analysis/v1",
        "control_id": control_id,
        "registration_digest": hashlib.sha256(
            registration_path.read_bytes()
        ).hexdigest(),
        "raw_sha256": expected_raw_sha256,
        **metrics,
        "ledger_activity_boundary": "2022-01-01",
        "ledger_opening_authority": "INSUFFICIENT_OPENING_AUTHORITY",
        "first_activity_classification": "TRANSFER_ONLY_EVIDENCE",
        "july_2021_accounting_opening_boundary": "REJECTED_BY_LEDGER_EVIDENCE",
        "isolated_2021_invoice": (
            "SOURCE_COMMERCIAL_EVIDENCE_NOT_CORROBORATED_BY_2021_GL_ACTIVITY"
        ),
        "full_available_history_effect": "UNCHANGED_FAMILY_SPECIFIC_COVERAGE",
        "opening_state_effect": (
            "DO_NOT_FABRICATE_OPENING_BALANCE; FIRST_ACTIVITY_REQUIRES_AUDIT_LINEAGE"
        ),
        "additional_control_required": {
            "report": "QuickBooks Audit Log",
            "period": "2021-07-07/2022-01-03",
            "filters": "all_users_all_events",
            "purpose": (
                "classify the first Transfer, account/file creation, imports, "
                "opening-balance events, and the isolated 2021 Invoice"
            ),
        },
    }
    document["evidence_digest"] = _digest(document)
    analysis_digest = ControlEvidenceRegistry(store).register_authority_document(
        authority_id="qbo-g5-ledger-opening-analysis-v1", document=document
    )
    return {
        "state": "LEDGER_ACTIVITY_BOUNDARY_PROVED_OPENING_AUTHORITY_INSUFFICIENT",
        "analysis_digest": analysis_digest,
        "raw_sha256": expected_raw_sha256,
        "earliest_ledger_date": metrics["earliest_ledger_date"],
        "ledger_rows_2021": metrics["ledger_rows_2021"],
        "first_activity_classification": "TRANSFER_ONLY_EVIDENCE",
        "explicit_opening_keyword_matches": metrics[
            "explicit_opening_keyword_matches"
        ],
        "next_report": "QBO_AUDIT_LOG_2021-07-07_2022-01-03",
    }


def _workbook_metrics(path: Path) -> dict[str, object]:
    try:
        with ZipFile(path) as workbook:
            names = workbook.namelist()
            shared = _shared_strings(workbook)
            basis_embedded = any(
                b"accrual" in workbook.read(name).lower() for name in names
            )
            rows = _sheet_rows(workbook, shared)
    except (BadZipFile, KeyError, ElementTree.ParseError) as error:
        raise EvidenceStoreError("ledger_workbook_invalid") from error
    strings = [value for row in rows for value in row.values()]
    header = next((row for row in rows if "Transaction date" in row.values()), None)
    if header is None:
        raise EvidenceStoreError("ledger_header_missing")
    columns = {value: column for column, value in header.items()}
    date_column = columns.get("Transaction date")
    type_column = columns.get("Transaction type")
    if date_column is None or type_column is None:
        raise EvidenceStoreError("ledger_header_missing")
    transactions: list[tuple[date, str]] = []
    for row in rows:
        transaction_date = _date(row.get(date_column, ""))
        if transaction_date is not None:
            transactions.append((transaction_date, row.get(type_column, "")))
    if not transactions:
        raise EvidenceStoreError("ledger_transactions_missing")
    earliest = min(item[0] for item in transactions)
    latest = max(item[0] for item in transactions)
    earliest_types = Counter(
        item_type or "UNSPECIFIED"
        for transaction_date, item_type in transactions
        if transaction_date == earliest
    )
    title_verified = any(value == "General Ledger" for value in strings)
    period_verified = any(
        value == "July 7, 2021-December 31, 2022" for value in strings
    )
    return {
        "report_title_verified": title_verified,
        "period_verified": period_verified,
        "registered_basis": "accrual",
        "basis_label_embedded": basis_embedded,
        "basis_authority": (
            "WORKBOOK_EMBEDDED" if basis_embedded else "OWNER_SUPPLIED_EXPORT_SETTING"
        ),
        "dated_ledger_rows": len(transactions),
        "earliest_ledger_date": earliest.isoformat(),
        "latest_ledger_date": latest.isoformat(),
        "ledger_rows_2021": sum(item[0].year == 2021 for item in transactions),
        "earliest_date_row_count": sum(
            item[0] == earliest for item in transactions
        ),
        "earliest_date_transaction_types": dict(sorted(earliest_types.items())),
        "earliest_date_transfer_only": set(earliest_types) == {"Transfer"},
        "first_non_transfer_date": min(
            item[0] for item in transactions if item[1] != "Transfer"
        ).isoformat(),
        "explicit_opening_keyword_matches": sum(
            bool(_OPENING.search(value)) for value in strings
        ),
    }


def _shared_strings(workbook: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []
    root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
    return [
        "".join(node.text or "" for node in item.iter(_NS + "t"))
        for item in root.findall(_NS + "si")
    ]


def _sheet_rows(workbook: ZipFile, shared: list[str]) -> list[dict[int, str]]:
    root = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
    rows: list[dict[int, str]] = []
    for source_row in root.iter(_NS + "row"):
        row: dict[int, str] = {}
        for cell in source_row.findall(_NS + "c"):
            reference = cell.attrib["r"]
            column = _column(reference)
            value_node = cell.find(_NS + "v")
            if cell.attrib.get("t") == "inlineStr":
                value = "".join(node.text or "" for node in cell.iter(_NS + "t"))
            elif value_node is None:
                value = ""
            elif cell.attrib.get("t") == "s":
                value = shared[int(value_node.text or "0")]
            else:
                value = value_node.text or ""
            row[column] = value.strip()
        rows.append(row)
    return rows


def _column(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference)
    if letters is None:
        raise EvidenceStoreError("ledger_cell_reference_invalid")
    result = 0
    for character in letters.group():
        result = result * 26 + ord(character) - 64
    return result


def _date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        return None


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seal safe ledger-opening analysis")
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--control-id", required=True)
    parser.add_argument("--raw-sha256", required=True)
    arguments = parser.parse_args()
    result = analyze_registered_general_ledger(
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
