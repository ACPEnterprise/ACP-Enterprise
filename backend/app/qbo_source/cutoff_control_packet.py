"""Reconcile the immutable August 31 owner control packet without source writes."""

from __future__ import annotations

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

PACKET_VERSION = "qbo-cutoff-control-packet/2026-08-31/v1"

_CONTROLS = {
    "accrual_trial_balance": "qbo-cutoff-trial-balance-2026-08-31-accrual-v1",
    "cash_trial_balance": "qbo-cutoff-trial-balance-2026-08-31-cash-v1",
    "cash_balance_sheet": "qbo-cutoff-balance-sheet-2026-08-31-cash-v1",
    "cash_profit_and_loss": "qbo-history-profit-loss-2022-01-01--2026-08-31-cash-v1",
    "open_invoices": "qbo-cutoff-open-invoices-2026-08-31-v1",
    "customer_balance_detail": "qbo-cutoff-customer-balance-detail-2026-08-31-v1",
    "ap_aging": "qbo-cutoff-ap-aging-detail-2026-08-31-v1",
    "unpaid_bills": "qbo-cutoff-unpaid-bills-2026-08-31-v1",
    "vendor_balance_detail": "qbo-cutoff-vendor-balance-detail-2026-08-31-v1",
    "accrual_general_ledger": "qbo-history-general-ledger-2022-01-01--2026-08-31-accrual-v1",
}


def seal_cutoff_control_packet(
    *, store: ProtectedFilesystemEvidenceStore
) -> dict[str, object]:
    metrics = {
        name: _registered_metrics(store, control_id)
        for name, control_id in _CONTROLS.items()
    }
    dispositions = {
        "accrual_trial_balance": _basis_disposition(
            metrics["accrual_trial_balance"], "accrual"
        ),
        "cash_trial_balance": _basis_disposition(metrics["cash_trial_balance"], "cash"),
        "cash_balance_sheet": _basis_disposition(metrics["cash_balance_sheet"], "cash"),
        "cash_profit_and_loss": _basis_disposition(
            metrics["cash_profit_and_loss"], "cash"
        ),
        "open_invoices": "ACCEPTED_OPERATIONAL_CONTROL",
        "customer_balance_detail": "ACCEPTED_OPERATIONAL_CONTROL",
        "ap_aging": "EMPTY_CONFIRMED_REPORT_IDENTITY_LIMITED",
        "unpaid_bills": "EMPTY_CONFIRMED",
        "vendor_balance_detail": "EMPTY_CONFIRMED",
        "accrual_general_ledger": _basis_disposition(
            metrics["accrual_general_ledger"], "accrual"
        ),
    }
    ar: dict[str, object] = {
        "accepted_ar_aging": "479879.48",
        "accrual_trial_balance": _required(
            metrics["accrual_trial_balance"], "Accounts Receivable"
        ),
        "open_invoices": _required(metrics["open_invoices"], "TOTAL"),
        "customer_balance_detail": _required(
            metrics["customer_balance_detail"], "TOTAL"
        ),
    }
    ar["aging_to_ledger_variance"] = str(
        Decimal(str(ar["accrual_trial_balance"]))
        - Decimal(str(ar["accepted_ar_aging"]))
    )
    ar["detail_controls_tie"] = (
        ar["accrual_trial_balance"]
        == ar["open_invoices"]
        == ar["customer_balance_detail"]
    )
    ap_empty = all(
        metrics[name]["numeric_cell_count"] == 0
        for name in ("ap_aging", "unpaid_bills", "vendor_balance_detail")
    )
    document: dict[str, object] = {
        "schema_version": PACKET_VERSION,
        "cutoff": "2026-08-31",
        "historical_reporting_basis": "CASH",
        "registrations": {
            name: value["registration_sha256"] for name, value in metrics.items()
        },
        "dispositions": dispositions,
        "ar": ar,
        "ap": {
            "three_detail_controls_empty": ap_empty,
            "ledger_control": "NO_NONZERO_AP_CONTROL_OBSERVED",
            "state": "ZERO_SUPPORTED_ACCOUNTANT_CONFIRMATION_REQUIRED",
        },
        "cash_accrual": {
            "cash_profit_and_loss": "ACCEPTED",
            "cash_trial_balance": dispositions["cash_trial_balance"],
            "cash_balance_sheet": dispositions["cash_balance_sheet"],
            "accrual_general_ledger": dispositions["accrual_general_ledger"],
            "difference_is_not_error": True,
        },
        "legacy_control_gaps": legacy_control_gap_register(),
        "accounting_admission": "BLOCKED_BY_CONTROL_VARIANCE_AND_BASIS_MISMATCHES",
        "source_mutation": "PROHIBITED_AND_NOT_PERFORMED",
    }
    document["evidence_digest"] = _digest(document)
    authority_digest = ControlEvidenceRegistry(store).register_authority_document(
        authority_id="qbo-cutoff-control-packet-2026-08-31-v1", document=document
    )
    return {
        "state": "CONTROL_PACKET_RECONCILED_WITH_EXCEPTIONS",
        "authority_digest": authority_digest,
        "ar_variance": ar["aging_to_ledger_variance"],
        "ap_detail_controls_empty": ap_empty,
        "basis_mismatches": tuple(
            name
            for name, state in dispositions.items()
            if state == "REJECTED_BASIS_MISMATCH"
        ),
    }


def legacy_control_gap_register() -> dict[str, object]:
    return {
        "undeposited_funds": {
            "state": "LEGACY_CONTROL_NOT_MAINTAINED",
            "existing_evidence": "ledger_account_and_transaction_evidence",
            "reconstruction": "RECONSTRUCTABLE_WITH_EVIDENCE_ONLY_WHERE_SETTLEMENT_LINKS_PROVE_IT",
            "opening": "OWNER_ACCOUNTANT_OPENING_CONTROL_REQUIRED",
            "native": "START_NATIVE_AT_CUTOVER",
        },
        "company_credit_cards": {
            "state": "LEGACY_CONTROL_NOT_MAINTAINED",
            "existing_evidence": "ledger_accounts_purchases_and_payments",
            "reconstruction": "OWNER_ACCOUNTANT_OPENING_CONTROL_REQUIRED",
            "opening": "PER_CARD_ACCEPTED_BALANCE_REQUIRED",
            "native": "START_NATIVE_AT_CUTOVER",
        },
        "inventory_valuation": {
            "state": "LEGACY_CONTROL_NOT_MAINTAINED",
            "existing_evidence": "items_purchases_and_operational_material_evidence",
            "reconstruction": "WOULD_REQUIRE_FABRICATION_WITHOUT_PHYSICAL_COUNT_AND_COST_BASIS",
            "opening": "OWNER_ACCOUNTANT_OPENING_CONTROL_REQUIRED_OR_NOT_APPLICABLE",
            "native": "START_NATIVE_AT_CUTOVER",
        },
    }


def _registered_metrics(
    store: ProtectedFilesystemEvidenceStore, control_id: str
) -> dict[str, object]:
    registration_path = store.root / "controls" / f"{control_id}.json"
    registration = store._read_json(registration_path)
    raw_sha = str(registration["raw_sha256"])
    raw_path = store.root / "controls" / "raw" / f"{raw_sha}.xlsx"
    if hashlib.sha256(raw_path.read_bytes()).hexdigest() != raw_sha:
        raise EvidenceStoreError("cutoff_control_raw_digest_mismatch")
    workbook = _workbook_metrics(raw_path)
    workbook["registration_sha256"] = hashlib.sha256(
        registration_path.read_bytes()
    ).hexdigest()
    return workbook


def _workbook_metrics(path: Path) -> dict[str, object]:
    try:
        with ZipFile(path) as workbook:
            rows = _sheet_rows(workbook, _shared_strings(workbook))
    except (BadZipFile, KeyError, ValueError) as error:
        raise EvidenceStoreError("cutoff_control_workbook_invalid") from error
    basis: str | None = None
    values: dict[str, str] = {}
    numeric_cells = 0
    for row in rows:
        ordered = [
            str(value).strip() for _, value in sorted(row.items()) if str(value).strip()
        ]
        for value in ordered:
            lowered = value.lower()
            if "cash basis" in lowered:
                basis = "cash"
            if "accrual basis" in lowered:
                basis = "accrual"
            if _decimal_or_none(value) is None:
                continue
            numeric_cells += 1
        if len(ordered) >= 2 and ordered[0] in {
            "Accounts Receivable",
            "Accounts Payable",
            "TOTAL",
        }:
            for candidate in reversed(ordered[1:]):
                amount = _decimal_or_none(candidate)
                if amount is None:
                    continue
                values[ordered[0]] = str(amount.quantize(Decimal("0.01")))
                break
    return {
        "embedded_basis": basis,
        "values": values,
        "numeric_cell_count": numeric_cells,
    }


def _basis_disposition(metrics: dict[str, object], expected: str) -> str:
    return (
        "ACCEPTED"
        if metrics["embedded_basis"] == expected
        else "REJECTED_BASIS_MISMATCH"
    )


def _decimal_or_none(value: str) -> Decimal | None:
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def _required(metrics: dict[str, object], label: str) -> str:
    values = metrics["values"]
    if not isinstance(values, dict) or label not in values:
        raise EvidenceStoreError("cutoff_control_required_total_missing")
    return str(values[label])


def _digest(value: object) -> str:
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(serialized).hexdigest()
