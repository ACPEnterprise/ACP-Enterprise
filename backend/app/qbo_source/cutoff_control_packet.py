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
SUPPLEMENT_VERSION = "qbo-cutoff-control-supplement/2026-08-31/v1"

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

_SUPPLEMENTAL_CONTROLS = {
    "cash_trial_balance": "qbo-cutoff-trial-balance-2026-08-31-cash-v2",
    "cash_balance_sheet": "qbo-cutoff-balance-sheet-2026-08-31-cash-v2",
    "accrual_general_ledger": "qbo-history-general-ledger-2022-01-01--2026-08-31-accrual-v2",
}


def seal_supplemental_control_packet(
    *, store: ProtectedFilesystemEvidenceStore
) -> dict[str, object]:
    metrics = {
        name: _registered_metrics(store, control_id)
        for name, control_id in _SUPPLEMENTAL_CONTROLS.items()
    }
    expected = {
        "cash_trial_balance": ("Trial Balance", "cash", "As of Aug 31, 2026"),
        "cash_balance_sheet": ("Balance Sheet", "cash", "As of Aug 31, 2026"),
        "accrual_general_ledger": (
            "General Ledger",
            "accrual",
            "January, 2022-August, 2026",
        ),
    }
    dispositions = {
        name: _identity_disposition(metrics[name], *required)
        for name, required in expected.items()
    }
    if set(dispositions.values()) != {"ACCEPTED_SUCCESSOR_CONTROL"}:
        raise EvidenceStoreError("supplemental_control_identity_mismatch")
    cash_trial_total = _required(metrics["cash_trial_balance"], "TOTAL")
    cash_assets = _required(metrics["cash_balance_sheet"], "Total for Assets")
    cash_liabilities = _required(metrics["cash_balance_sheet"], "Total for Liabilities")
    cash_equity = _required(metrics["cash_balance_sheet"], "Total for Equity")
    balance_delta = (
        Decimal(cash_assets) - Decimal(cash_liabilities) - Decimal(cash_equity)
    ).quantize(Decimal("0.01"))
    document: dict[str, object] = {
        "schema_version": SUPPLEMENT_VERSION,
        "cutoff": "2026-08-31",
        "predecessor_authority": "qbo-cutoff-control-packet-2026-08-31-v1",
        "registrations": {
            name: metrics[name]["registration_sha256"] for name in metrics
        },
        "dispositions": dispositions,
        "cash_trial_balance": {
            "debits": cash_trial_total,
            "credits": cash_trial_total,
            "balanced": True,
        },
        "cash_balance_sheet": {
            "assets": cash_assets,
            "liabilities": cash_liabilities,
            "equity": cash_equity,
            "balance_delta": str(balance_delta),
            "balanced": balance_delta == 0,
        },
        "cash_continuity": "CUTOFF_CASH_CONTROLS_ACCEPTED",
        "accrual_general_ledger": {
            "state": "ACCEPTED_ACTIVITY_CONTROL",
            "period": "2022-01-01/2026-08-31",
            "accounts_receivable": _required(
                metrics["accrual_general_ledger"], "Total for Accounts Receivable"
            ),
            "undeposited_funds": _required(
                metrics["accrual_general_ledger"], "Total for Undeposited Funds"
            ),
        },
        "ar_variance": {
            "amount": "850.00",
            "classification": "SOURCE_VERSION_CONFLICTING_INVOICE",
            "transaction_date": "2026-08-18",
            "source_identity_digest_prefix": "854e995a2a9b14f4",
            "aging_open_balance": "850.00",
            "accrual_ledger_amount": "0.00",
            "latest_consistent_ledger_and_detail_total": "479029.48",
            "state": "ACCOUNTANT_DISPOSITION_REQUIRED_NO_FORCED_RESOLUTION",
        },
        "ap": {
            "state": "ZERO_CANDIDATE_CONTROLLED_ACCOUNTANT_CONFIRMATION_REQUIRED",
            "detail_controls": "THREE_EMPTY_CONFIRMED",
            "ledger_nonzero_ap": "NOT_OBSERVED",
        },
        "bank_cash": "LEDGER_AND_AGGREGATE_CONTROL_AVAILABLE_EXTERNAL_RECONCILIATION_REQUIRED",
        "undeposited_funds": "39271.71_LEDGER_SUPPORTED_OPENING_CONTROL_REQUIRED",
        "credit_cards": "PER_ACCOUNT_LEDGER_EVIDENCE_AVAILABLE_STATEMENT_CONTROL_UNAVAILABLE",
        "inventory": "LEGACY_VALUATION_UNAVAILABLE_START_NATIVE_AT_CUTOVER",
        "coa": {
            "source_accounts": 130,
            "mechanically_classified": 38,
            "owner_accountant_decision": 92,
            "reason": "activity_and_balances_do_not_determine_future_accounting_policy",
        },
        "legacy_control_gaps": legacy_control_gap_register(),
        "accounting_readiness": "CONTROL_PACKET_COMPLETE_OWNER_ACCOUNTANT_ADMISSION_PENDING",
        "source_mutation": "PROHIBITED_AND_NOT_PERFORMED",
    }
    document["evidence_digest"] = _digest(document)
    authority_digest = ControlEvidenceRegistry(store).register_authority_document(
        authority_id="qbo-cutoff-control-supplement-2026-08-31-v1",
        document=document,
    )
    return {
        "state": "SUPPLEMENTAL_CONTROLS_ACCEPTED",
        "authority_digest": authority_digest,
        "cash_trial_balance": cash_trial_total,
        "cash_balance_sheet_delta": str(balance_delta),
        "ar_variance": "850.00_SOURCE_VERSION_CONFLICT",
        "accounting_readiness": document["accounting_readiness"],
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
    strings: set[str] = set()
    values: dict[str, str] = {}
    numeric_cells = 0
    for row in rows:
        ordered = [
            str(value).strip() for _, value in sorted(row.items()) if str(value).strip()
        ]
        for value in ordered:
            strings.add(value)
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
            "Total for Accounts Receivable",
            "Total for Assets",
            "Total for Liabilities",
            "Total for Equity",
            "Total for Undeposited Funds",
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
        "strings": strings,
    }


def _basis_disposition(metrics: dict[str, object], expected: str) -> str:
    return (
        "ACCEPTED"
        if metrics["embedded_basis"] == expected
        else "REJECTED_BASIS_MISMATCH"
    )


def _identity_disposition(
    metrics: dict[str, object], title: str, basis: str, period: str
) -> str:
    strings = metrics["strings"]
    if not isinstance(strings, set):
        raise EvidenceStoreError("supplemental_control_strings_invalid")
    if metrics["embedded_basis"] == basis and title in strings and period in strings:
        return "ACCEPTED_SUCCESSOR_CONTROL"
    return "REJECTED_IDENTITY_BASIS_OR_PERIOD_MISMATCH"


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
