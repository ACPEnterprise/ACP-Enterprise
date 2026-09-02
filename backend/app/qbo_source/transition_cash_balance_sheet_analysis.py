"""Safe analysis of the February 2024 QBO Cash-basis Balance Sheet."""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from .evidence import (
    ControlEvidenceRegistry,
    EvidenceStoreError,
    ProtectedFilesystemEvidenceStore,
)
from .ledger_opening_analysis import _shared_strings, _sheet_rows

_CONTROL_DATE = "2024-02-19"
_CENT = Decimal("0.01")


def analyze_transition_cash_balance_sheet(
    *,
    store: ProtectedFilesystemEvidenceStore,
    control_id: str,
    expected_raw_sha256: str,
) -> dict[str, object]:
    registration_path = store.root / "controls" / f"{control_id}.json"
    registration = store._read_json(registration_path)
    if registration.get("kind") != "balance_sheet":
        raise EvidenceStoreError("transition_cash_balance_sheet_kind_invalid")
    if registration.get("accounting_basis") != "cash":
        raise EvidenceStoreError("transition_cash_balance_sheet_basis_invalid")
    if registration.get("report_end_date") != _CONTROL_DATE:
        raise EvidenceStoreError("transition_cash_balance_sheet_date_invalid")
    if registration.get("raw_sha256") != expected_raw_sha256:
        raise EvidenceStoreError("transition_cash_balance_sheet_digest_mismatch")
    source_path = store.root / "controls" / "raw" / f"{expected_raw_sha256}.xlsx"
    if hashlib.sha256(source_path.read_bytes()).hexdigest() != expected_raw_sha256:
        raise EvidenceStoreError("transition_cash_balance_sheet_digest_mismatch")
    metrics = _metrics(source_path)
    if metrics["assets"] != metrics["liabilities_and_equity"]:
        raise EvidenceStoreError("transition_cash_balance_sheet_unbalanced")
    trial_path = (
        store.root / "controls" / "qbo-transition-ledger-control-2024-02-19-v1.json"
    )
    document: dict[str, object] = {
        "schema_version": "qbo-transition-cash-balance-control/v1",
        "control_id": control_id,
        "registration_digest": hashlib.sha256(
            registration_path.read_bytes()
        ).hexdigest(),
        "raw_sha256": expected_raw_sha256,
        "transition_ledger_control_digest": hashlib.sha256(
            trial_path.read_bytes()
        ).hexdigest(),
        **metrics,
        "historical_reporting_basis": "CASH",
        "cash_transition_continuity": "BALANCED_CONTROL_ACCEPTED",
        "operational_ar_authority": "SEPARATE_AR_AGING_CONTROL_REQUIRED",
        "operational_ap_authority": "SEPARATE_AP_AGING_CONTROL_REQUIRED",
        "bank_opening_authority": "ACCOUNT_LEVEL_EXTERNAL_CONTROL_REQUIRED",
        "credit_card_opening_authority": "ACCOUNT_LEVEL_EXTERNAL_CONTROL_REQUIRED",
        "economics_effect": "NO_CHANGE_SEPARATE_ECONOMIC_AUTHORITY",
    }
    document["evidence_digest"] = _digest(document)
    analysis_digest = ControlEvidenceRegistry(store).register_authority_document(
        authority_id="qbo-transition-cash-balance-control-2024-02-19-v1",
        document=document,
    )
    return {
        "state": "TRANSITION_CASH_BALANCE_CONTROL_ACCEPTED",
        "analysis_digest": analysis_digest,
        "raw_sha256": expected_raw_sha256,
        "assets": metrics["assets"],
        "liabilities_and_equity": metrics["liabilities_and_equity"],
        "bank_accounts": metrics["bank_accounts"],
        "credit_cards": metrics["credit_cards"],
    }


def _metrics(path: Path) -> dict[str, object]:
    try:
        with ZipFile(path) as workbook:
            rows = _sheet_rows(workbook, _shared_strings(workbook))
    except (BadZipFile, KeyError) as error:
        raise EvidenceStoreError("transition_cash_balance_workbook_invalid") from error
    strings = [value for row in rows for value in row.values()]
    if "Balance Sheet" not in strings or "As of Feb 19, 2024" not in strings:
        raise EvidenceStoreError("transition_cash_balance_identity_invalid")
    totals: dict[str, Decimal] = {}
    for row in rows:
        label = row.get(1, "")
        if label.startswith("Total for "):
            totals[label.removeprefix("Total for ")] = _decimal(row.get(2, ""))
    required = {
        "Bank Accounts",
        "Assets",
        "Credit Cards",
        "Liabilities",
        "Equity",
        "Liabilities and Equity",
    }
    if not required.issubset(totals):
        raise EvidenceStoreError("transition_cash_balance_totals_missing")
    return {
        "report_title_verified": True,
        "report_date_verified": True,
        "basis_authority": "OWNER_SUPPLIED_EXPORT_SETTING",
        "assets": str(totals["Assets"].quantize(_CENT)),
        "liabilities": str(totals["Liabilities"].quantize(_CENT)),
        "equity": str(totals["Equity"].quantize(_CENT)),
        "liabilities_and_equity": str(totals["Liabilities and Equity"].quantize(_CENT)),
        "bank_accounts": str(totals["Bank Accounts"].quantize(_CENT)),
        "credit_cards": str(totals["Credit Cards"].quantize(_CENT)),
        "opening_balance_equity_rows": sum(
            "opening balance equity" in value.casefold() for value in strings
        ),
    }


def _decimal(value: str) -> Decimal:
    try:
        return Decimal(value.replace(",", "").replace("$", "").strip() or "0")
    except InvalidOperation as error:
        raise EvidenceStoreError("transition_cash_balance_amount_invalid") from error


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seal QBO transition Cash Balance Sheet"
    )
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--control-id", required=True)
    parser.add_argument("--raw-sha256", required=True)
    arguments = parser.parse_args()
    result = analyze_transition_cash_balance_sheet(
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
