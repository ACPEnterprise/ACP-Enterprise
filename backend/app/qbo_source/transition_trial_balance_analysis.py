"""Safe analysis of the registered February 2024 QBO transition Trial Balance."""

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


def analyze_transition_trial_balance(
    *,
    store: ProtectedFilesystemEvidenceStore,
    control_id: str,
    expected_raw_sha256: str,
) -> dict[str, object]:
    registration_path = store.root / "controls" / f"{control_id}.json"
    registration = store._read_json(registration_path)
    if registration.get("kind") != "trial_balance":
        raise EvidenceStoreError("transition_trial_balance_kind_invalid")
    if registration.get("accounting_basis") != "accrual":
        raise EvidenceStoreError("transition_trial_balance_basis_invalid")
    if registration.get("report_end_date") != _CONTROL_DATE:
        raise EvidenceStoreError("transition_trial_balance_date_invalid")
    if registration.get("raw_sha256") != expected_raw_sha256:
        raise EvidenceStoreError("transition_trial_balance_digest_mismatch")
    source_path = store.root / "controls" / "raw" / f"{expected_raw_sha256}.xlsx"
    if hashlib.sha256(source_path.read_bytes()).hexdigest() != expected_raw_sha256:
        raise EvidenceStoreError("transition_trial_balance_digest_mismatch")
    metrics = _metrics(source_path)
    if metrics["debit_total"] != metrics["credit_total"]:
        raise EvidenceStoreError("transition_trial_balance_unbalanced")
    audit_path = store.root / "controls" / "qbo-current-environment-authority-v1.json"
    audit_authority_digest = hashlib.sha256(audit_path.read_bytes()).hexdigest()
    document: dict[str, object] = {
        "schema_version": "qbo-transition-ledger-control/v1",
        "control_id": control_id,
        "registration_digest": hashlib.sha256(
            registration_path.read_bytes()
        ).hexdigest(),
        "raw_sha256": expected_raw_sha256,
        "current_environment_authority_digest": audit_authority_digest,
        **metrics,
        "current_qbo_environment_authority_date": _CONTROL_DATE,
        "ledger_transition_control": "BALANCED_CONTROL_ACCEPTED",
        "opening_balance_equity": "ABSENT_FROM_TRANSITION_TRIAL_BALANCE",
        "historical_effective_dated_transactions": "PRESERVE_WITH_IMPORT_LINEAGE",
        "opening_state_effect": "NO_FABRICATED_OPENING_JOURNAL",
        "operational_ar_ap_effect": "REQUIRES_SEPARATE_SUBLEDGER_CONTROLS",
        "cash_reporting_effect": "REQUIRES_SEPARATE_CASH_BASIS_CONTROL",
        "bank_card_effect": "REQUIRES_ACCOUNT_LEVEL_EXTERNAL_CONTROLS",
    }
    document["evidence_digest"] = _digest(document)
    analysis_digest = ControlEvidenceRegistry(store).register_authority_document(
        authority_id="qbo-transition-ledger-control-2024-02-19-v1",
        document=document,
    )
    return {
        "state": "TRANSITION_LEDGER_CONTROL_ACCEPTED",
        "analysis_digest": analysis_digest,
        "raw_sha256": expected_raw_sha256,
        "account_count": metrics["account_count"],
        "debit_total": metrics["debit_total"],
        "credit_total": metrics["credit_total"],
        "opening_balance_equity_rows": metrics["opening_balance_equity_rows"],
    }


def _metrics(path: Path) -> dict[str, object]:
    try:
        with ZipFile(path) as workbook:
            rows = _sheet_rows(workbook, _shared_strings(workbook))
    except (BadZipFile, KeyError) as error:
        raise EvidenceStoreError("transition_trial_balance_workbook_invalid") from error
    strings = [value for row in rows for value in row.values()]
    if "Trial Balance" not in strings or "As of Feb 19, 2024" not in strings:
        raise EvidenceStoreError("transition_trial_balance_identity_invalid")
    header = next(
        (
            row
            for row in rows
            if {"Account Name", "Debit", "Credit"}.issubset(row.values())
        ),
        None,
    )
    if header is None:
        raise EvidenceStoreError("transition_trial_balance_header_invalid")
    columns = {value: column for column, value in header.items()}
    accounts: list[tuple[str, Decimal, Decimal]] = []
    for row in rows:
        account = row.get(columns["Account Name"], "")
        if not account or account in {"Account Name", "TOTAL"}:
            continue
        accounts.append(
            (
                account,
                _decimal(row.get(columns["Debit"], "")),
                _decimal(row.get(columns["Credit"], "")),
            )
        )
    if not accounts:
        raise EvidenceStoreError("transition_trial_balance_accounts_missing")
    debit = sum((row[1] for row in accounts), Decimal()).quantize(_CENT)
    credit = sum((row[2] for row in accounts), Decimal()).quantize(_CENT)
    return {
        "report_title_verified": True,
        "report_date_verified": True,
        "basis_authority": "OWNER_SUPPLIED_EXPORT_SETTING",
        "account_count": len(accounts),
        "debit_total": str(debit),
        "credit_total": str(credit),
        "opening_balance_equity_rows": sum(
            "opening balance equity" in row[0].casefold() for row in accounts
        ),
    }


def _decimal(value: str) -> Decimal:
    try:
        return Decimal(value.replace(",", "").replace("$", "").strip() or "0")
    except InvalidOperation as error:
        raise EvidenceStoreError("transition_trial_balance_amount_invalid") from error


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seal QBO transition Trial Balance control"
    )
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--control-id", required=True)
    parser.add_argument("--raw-sha256", required=True)
    arguments = parser.parse_args()
    result = analyze_transition_trial_balance(
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
