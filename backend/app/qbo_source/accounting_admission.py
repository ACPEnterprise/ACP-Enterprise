"""Safe owner-decision and Accounting-admission packets for real QBO evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from .evidence import ControlEvidenceRegistry, ProtectedFilesystemEvidenceStore

DECISION_VERSION = "migration-owner-history-decision/v1"
ADMISSION_VERSION = "qbo-accounting-admission-readiness/v1"
ACCOUNTING_BASIS_AUTHORITY_VERSION = "migration-accounting-basis-authority/v1"

FAMILY_WINDOWS = {
    "invoice": ("2021-07-07", "2026-08-31"),
    "deposit": ("2022-01-03", "2026-08-31"),
    "purchase": ("2022-01-03", "2026-08-05"),
    "journal_entry": ("2022-12-31", "2026-08-17"),
    "payment": ("2024-12-03", "2026-08-31"),
    "refund_receipt": ("2025-02-06", "2026-08-14"),
    "transfer": ("2022-01-01", "2023-12-31"),
}


@dataclass(frozen=True)
class HistoryDecisionAuthority:
    owner_authority_id: str
    decided_at: datetime
    bounded_snapshot_digest: str
    hcp_master_id: str
    hcp_completion_digest: str
    cutoff: str


def seal_full_history_decision(
    registry: ControlEvidenceRegistry, authority: HistoryDecisionAuthority
) -> str:
    document: dict[str, object] = {
        "schema_version": DECISION_VERSION,
        "decision": "FULL_AVAILABLE_HISTORY",
        "owner_authority_id": authority.owner_authority_id,
        "decided_at": authority.decided_at.isoformat(),
        "qbo_run_id": "real-qbo-2026-08-31-g5",
        "qbo_bounded_snapshot_digest": authority.bounded_snapshot_digest,
        "hcp_master_id": authority.hcp_master_id,
        "hcp_completion_digest": authority.hcp_completion_digest,
        "accounting_date_cutoff": authority.cutoff,
        "family_coverage": FAMILY_WINDOWS,
        "temporal_limitation": "FAMILY_SPECIFIC_AVAILABLE_COVERAGE",
        "opening_control_policy": (
            "REQUIRED_WHERE_COVERAGE_DOES_NOT_PROVE_CUTOFF_BALANCE"
        ),
    }
    document["evidence_digest"] = _digest(document)
    return registry.register_authority_document(
        authority_id="full-available-history-g5-v1", document=document
    )


def build_coa_mapping_packet(
    accounts: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    rows = []
    for account in accounts:
        account_type = str(account.get("AccountType", ""))
        subtype = str(account.get("AccountSubType", ""))
        active = bool(account.get("Active", True))
        classification, category = _account_disposition(account_type, subtype, active)
        native_id = str(account.get("Id", ""))
        rows.append(
            {
                "source_identity_digest": hashlib.sha256(
                    f"account:{native_id}".encode()
                ).hexdigest(),
                "account_type": account_type,
                "account_subtype": subtype,
                "active": active,
                "currency": _reference_value(account.get("CurrencyRef")),
                "parent_identity_digest": _parent_digest(account.get("ParentRef")),
                "current_balance": _safe_decimal(account.get("CurrentBalance")),
                "classification": classification,
                "proposed_acp_category": category,
                "rationale": (
                    "provider classification mapped to ACP category; exact ledger "
                    "account requires Finance authority"
                ),
            }
        )
    rows.sort(key=lambda row: str(row["source_identity_digest"]))
    return {
        "schema_version": ADMISSION_VERSION,
        "account_count": len(rows),
        "classification_counts": dict(
            sorted(Counter(str(row["classification"]) for row in rows).items())
        ),
        "accounts": rows,
    }


def accounting_control_matrix(cutoff: str) -> tuple[dict[str, object], ...]:
    return (
        _control(
            "AR", "CONTROL_REPORT_REQUIRED",
            "A/R Aging Detail; Open Invoices; Trial Balance", cutoff,
            "prove cutoff open items and control-account tie-out",
        ),
        _control(
            "opening_balance_sheet",
            "CONTROL_REPORT_REQUIRED",
            "Balance Sheet; Trial Balance",
            "2021-07-06",
            "prove balance-sheet opening authority immediately before the earliest "
            "reliable transaction family",
        ),
        _control(
            "AP", "CONTROL_REPORT_REQUIRED",
            "A/P Aging Detail; Unpaid Bills; Trial Balance", cutoff,
            "prove zero or open AP independently of empty API families",
        ),
        _control(
            "cash_bank", "CONTROL_REPORT_REQUIRED",
            "Balance Sheet; Trial Balance; Account QuickReport", cutoff,
            "prove each bank/cash ledger balance; deposits and payments are not cash",
        ),
        _control(
            "credit_card", "CONTROL_REPORT_REQUIRED",
            "Balance Sheet; Trial Balance; Account QuickReport", cutoff,
            "prove card liabilities and mapping",
        ),
        _control(
            "liabilities", "CONTROL_REPORT_REQUIRED",
            "Balance Sheet; Trial Balance; General Ledger", cutoff,
            "prove liability balances and classifications",
        ),
        _control(
            "equity", "CONTROL_REPORT_REQUIRED",
            "Balance Sheet; Trial Balance; General Ledger", cutoff,
            "prove retained/opening equity without fabrication",
        ),
        _control(
            "inventory", "CONTROL_REPORT_REQUIRED",
            "Balance Sheet; Inventory Valuation Summary", cutoff,
            "prove financial inventory control where used",
        ),
        _control(
            "payroll_liabilities", "OWNER_FINANCE_DECISION",
            "Balance Sheet; Trial Balance; General Ledger", cutoff,
            "identify authoritative payroll liability accounts and supporting "
            "subledger",
        ),
        _control(
            "tax_liabilities", "OWNER_FINANCE_DECISION",
            "Balance Sheet; Trial Balance; General Ledger", cutoff,
            "identify authoritative tax liability accounts and supporting detail",
        ),
    )


def cash_basis_control_matrix(cutoff: str) -> tuple[dict[str, object], ...]:
    """Purpose-specific controls; basis never changes operational obligations."""
    return (
        _basis_control(
            "historical_cash_results", "Profit & Loss", "cash",
            "2021-07-07/2026-08-31",
            "preserve historical cash-basis income and expense continuity",
        ),
        _basis_control(
            "historical_cash_position", "Balance Sheet; Trial Balance", "cash",
            cutoff,
            "control the Company's historical cash-basis reported position",
        ),
        _basis_control(
            "open_customer_obligations",
            "A/R Aging Detail; Open Invoices; Customer Balance Detail",
            "operational", cutoff,
            "preserve invoices, due dates, credits, applications, and open balances",
        ),
        _basis_control(
            "open_vendor_obligations",
            "A/P Aging Detail; Unpaid Bills; Vendor Balance Detail",
            "operational", cutoff,
            "preserve bills, due dates, credits, payments, and open obligations",
        ),
        _basis_control(
            "complete_ledger_and_opening", "General Ledger; Trial Balance",
            "accrual", "2021-07-07/2026-08-31",
            "locate first ledger activity and retain transactions omitted by cash "
            "reports",
        ),
        _basis_control(
            "bank_cash", "Account QuickReport; bank reconciliation/statement",
            "operational", cutoff,
            "prove each bank/cash book balance and reconciling items",
        ),
        _basis_control(
            "credit_cards", "Account QuickReport; card statement",
            "operational", cutoff,
            "prove each card liability independently from bank settlement",
        ),
        _basis_control(
            "undeposited_funds", "Undeposited Funds QuickReport",
            "operational", cutoff,
            "prove clearing items without treating deposits as revenue",
        ),
    )


def seal_cash_basis_authority(
    registry: ControlEvidenceRegistry, authority: HistoryDecisionAuthority
) -> str:
    document: dict[str, object] = {
        "schema_version": ACCOUNTING_BASIS_AUTHORITY_VERSION,
        "decision": "HISTORICAL_REPORTING_BASIS_CASH",
        "owner_authority_id": authority.owner_authority_id,
        "decided_at": authority.decided_at.isoformat(),
        "supersedes_control_assumption": "qbo-g5-accounting-controls-v2",
        "does_not_supersede": (
            "qbo_g1_g5_source_evidence",
            "full_available_history_g5_v1",
            "qbo_g5_coa_mapping_v1",
            "hcp_master_and_dispositions",
        ),
        "qbo_bounded_snapshot_digest": authority.bounded_snapshot_digest,
        "hcp_master_id": authority.hcp_master_id,
        "hcp_completion_digest": authority.hcp_completion_digest,
        "cutoff": authority.cutoff,
        "truth_boundaries": {
            "operational": "invoice_bill_terms_application_and_open_obligation",
            "cash": "received_paid_bank_and_card_settlement",
            "economic": "accepted_earned_work_and_attributable_cost_evidence",
        },
        "control_matrix": cash_basis_control_matrix(authority.cutoff),
    }
    document["evidence_digest"] = _digest(document)
    return registry.register_authority_document(
        authority_id="historical-cash-basis-g5-v1", document=document
    )


def provision_admission_packet(
    *,
    registry: ControlEvidenceRegistry,
    run_id: str,
    authority: HistoryDecisionAuthority,
) -> dict[str, object]:
    run_root = registry.store.root / "runs" / run_id
    bounded = registry.store._read_json(run_root / "bounded-manifest.json")
    if bounded.get("state") != "BOUNDED_COMPLETE":
        raise ValueError("bounded QBO authority is required")
    bounded_digest = hashlib.sha256(
        (run_root / "bounded-manifest.json").read_bytes()
    ).hexdigest()
    if bounded_digest != authority.bounded_snapshot_digest:
        raise ValueError("bounded snapshot authority mismatch")
    accounts: list[Mapping[str, object]] = []
    included_entities = bounded.get("included_entities")
    if not isinstance(included_entities, list):
        raise TypeError("bounded QBO entity evidence is required")
    for row in included_entities:
        if not isinstance(row, Mapping) or row.get("entity_kind") != "account":
            continue
        digest = row.get("raw_sha256")
        if not isinstance(digest, str):
            raise ValueError("account evidence digest missing")
        payload = registry.store._read_json(
            registry.store.root / "blobs" / digest[:2] / digest
        )
        accounts.append(payload)
    coa = build_coa_mapping_packet(accounts)
    controls = {
        "schema_version": ADMISSION_VERSION,
        "cutoff": authority.cutoff,
        "basis": "Accrual",
        "full_history_start": "2021-07-07",
        "opening_control_as_of": "2021-07-06",
        "matrix": accounting_control_matrix(authority.cutoff),
        "observations_not_admitted": {
            "invoice_gross": "1736216.15",
            "observed_open_balance": "574451.39",
            "post_cutoff_modified_invoice_balance": "1250.00",
            "empty_bill_families_do_not_prove_ap_zero": True,
            "deposits_and_payments_do_not_prove_cash": True,
        },
    }
    decision_digest = seal_full_history_decision(registry, authority)
    coa_digest = registry.register_authority_document(
        authority_id="qbo-g5-coa-mapping-v1", document=coa
    )
    control_digest = registry.register_authority_document(
        authority_id="qbo-g5-accounting-controls-v2", document=controls
    )
    return {
        "state": "ACCOUNTING_ADMISSION_CONTROL_PACKET_READY",
        "history_decision_digest": decision_digest,
        "coa_packet_digest": coa_digest,
        "control_packet_digest": control_digest,
        "account_count": coa["account_count"],
        "classification_counts": coa["classification_counts"],
    }


def provision_cash_basis_successor_packet(
    *, registry: ControlEvidenceRegistry, authority: HistoryDecisionAuthority
) -> dict[str, object]:
    authority_digest = seal_cash_basis_authority(registry, authority)
    controls = {
        "schema_version": "qbo-accounting-control-packet/v3",
        "historical_reporting_basis": "cash",
        "cutoff": authority.cutoff,
        "full_history_decision": "FULL_AVAILABLE_HISTORY",
        "matrix": cash_basis_control_matrix(authority.cutoff),
        "opening_boundary": {
            "known_empty_as_of": "2021-07-06",
            "known_populated_as_of": ("2022-12-31", "2023-07-31"),
            "next_control": {
                "report": "General Ledger",
                "basis": "accrual",
                "period": "2021-07-07/2022-12-31",
                "purpose": "identify first ledger posting and opening-balance event",
            },
        },
        "admission_rules": {
            "unpaid_invoice_survives_cash_basis": True,
            "unpaid_bill_survives_cash_basis": True,
            "payment_is_not_revenue": True,
            "deposit_is_not_revenue": True,
            "purchase_is_not_bank_cash_outflow": True,
            "credit_card_purchase_and_settlement_are_distinct": True,
            "economics_is_not_reporting_basis": True,
        },
    }
    control_digest = registry.register_authority_document(
        authority_id="qbo-g5-accounting-controls-v3-cash", document=controls
    )
    return {
        "state": "CASH_BASIS_SUCCESSOR_CONTROL_PACKET_READY",
        "accounting_basis_authority_digest": authority_digest,
        "control_packet_digest": control_digest,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seal QBO Accounting admission control packets"
    )
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--owner-authority-id", required=True)
    parser.add_argument("--decided-at", required=True, type=datetime.fromisoformat)
    parser.add_argument("--bounded-snapshot-digest", required=True)
    parser.add_argument("--hcp-master-id", required=True)
    parser.add_argument("--hcp-completion-digest", required=True)
    parser.add_argument(
        "--mode",
        choices=("full-history", "cash-basis-successor"),
        default="full-history",
    )
    args = parser.parse_args()
    store = ProtectedFilesystemEvidenceStore(
        root=Path(args.evidence_root),
        repository_root=Path(args.repository_root),
        bounded_snapshot=True,
    )
    authority = HistoryDecisionAuthority(
        args.owner_authority_id,
        args.decided_at,
        args.bounded_snapshot_digest,
        args.hcp_master_id,
        args.hcp_completion_digest,
        "2026-08-31",
    )
    registry = ControlEvidenceRegistry(store)
    result = (
        provision_cash_basis_successor_packet(
            registry=registry, authority=authority
        )
        if args.mode == "cash-basis-successor"
        else provision_admission_packet(
            registry=registry,
            run_id="real-qbo-2026-08-31-g5",
            authority=authority,
        )
    )
    print(json.dumps(result, sort_keys=True))


def _control(
    area: str, state: str, reports: str, cutoff: str, purpose: str
) -> dict[str, object]:
    return {
        "area": area,
        "state": state,
        "reports": reports,
        "as_of": cutoff,
        "basis": "Accrual",
        "purpose": purpose,
    }


def _basis_control(
    authority: str, report: str, basis: str, period: str, purpose: str
) -> dict[str, object]:
    return {
        "authority": authority,
        "report": report,
        "basis": basis,
        "date_or_period": period,
        "purpose": purpose,
    }


def _account_disposition(
    account_type: str, subtype: str, active: bool
) -> tuple[str, str | None]:
    if not active:
        return "INACTIVE", None
    direct = {"Accounts Receivable": "AR_CONTROL", "Accounts Payable": "AP_CONTROL"}
    recommended = {
        "Bank": "CASH_BANK",
        "Credit Card": "CREDIT_CARD_LIABILITY",
        "Income": "REVENUE",
        "Cost of Goods Sold": "COGS",
    }
    if account_type in direct:
        return "DIRECT_SAFE_MAPPING", direct[account_type]
    if account_type in recommended:
        return "MAPPING_RECOMMENDED", recommended[account_type]
    if account_type in {
        "Expense", "Other Expense", "Other Current Asset", "Fixed Asset",
        "Other Current Liability", "Long Term Liability", "Equity", "Other Income",
    }:
        return "OWNER_FINANCE_DECISION", account_type.upper().replace(" ", "_")
    if not account_type:
        return "CONFLICTING", None
    return "UNSUPPORTED", None


def _reference_value(value: object) -> str | None:
    if isinstance(value, Mapping) and value.get("value"):
        return str(value.get("value"))
    return None


def _parent_digest(value: object) -> str | None:
    parent = _reference_value(value)
    return hashlib.sha256(f"account:{parent}".encode()).hexdigest() if parent else None


def _safe_decimal(value: object) -> str | None:
    try:
        return format(Decimal(str(value)), "f") if value is not None else None
    except Exception:
        return None


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


if __name__ == "__main__":
    main()
