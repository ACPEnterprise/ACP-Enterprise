"""Fail-closed native Accounting admission plan for sealed QBO evidence.

This module deliberately does not load provider records or create Accounting rows.
It binds the manual custody archive to the separately produced bounded-envelope
rehearsal and describes the controls that must be satisfied before each native
admission phase can execute.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from .manual_archive import manual_archive_readiness

PLAN_SCHEMA = "qbo-native-accounting-admission-plan/v1"
EXPECTED_CONFLICT_IDS = tuple(f"D-{index:03d}" for index in range(1, 8))


class NativeAdmissionPlanError(ValueError):
    """The sealed inputs cannot support a deterministic admission plan."""


def build_native_admission_plan(*, archive_root: Path) -> dict[str, object]:
    """Validate sealed inputs and return a non-posting admission plan."""

    root = archive_root.expanduser().resolve()
    readiness = manual_archive_readiness(root=root)
    register = _read_mapping(root / "reconciliation-register.json")
    rehearsal = _read_mapping(root / "native-admission-rehearsal.v1.json")
    acquisition = _mapping(register, "current_acquisition")
    inventory = _mapping(register, "twelvehats_existing_inventory")
    report_reconciliation = _mapping(register, "report_reconciliation")
    bank_feed = _mapping(register, "bank_feed_evidence")
    payroll = _mapping(register, "payroll_reconstruction")

    conflicts = _conflicts(register.get("discrepancies"))
    conflict_ids = tuple(item["id"] for item in conflicts)
    if conflict_ids != EXPECTED_CONFLICT_IDS:
        raise NativeAdmissionPlanError("seven_disclosed_conflicts_not_preserved")

    source_count = _integer(acquisition, "record_count")
    source_counts = _integer_mapping(acquisition, "counts")
    if sum(source_counts.values()) != source_count:
        raise NativeAdmissionPlanError("source_family_count_mismatch")
    if source_count != _integer(rehearsal, "source_record_count"):
        raise NativeAdmissionPlanError("rehearsal_source_count_mismatch")
    if source_counts != _integer_mapping(rehearsal, "source_family_counts"):
        raise NativeAdmissionPlanError("rehearsal_family_count_mismatch")
    if acquisition.get("manifest_sha256") != rehearsal.get("source_manifest_sha256"):
        raise NativeAdmissionPlanError("source_manifest_binding_mismatch")
    if acquisition.get("bounded_snapshot_sha256") != rehearsal.get(
        "bounded_snapshot_sha256"
    ):
        raise NativeAdmissionPlanError("bounded_snapshot_binding_mismatch")
    if rehearsal.get("state") != "REHEARSAL_COMPLETE_NO_WRITES":
        raise NativeAdmissionPlanError("bounded_rehearsal_not_complete")
    _require_no_writes(rehearsal)
    _validate_controls(report_reconciliation)

    invoice = _mapping(acquisition, "invoice")
    payment = _mapping(acquisition, "payment")
    journal = _mapping(acquisition, "journal")
    native_financial_rows = sum(
        _integer(inventory, key)
        for key in (
            "accounting_accounts",
            "account_source_identities",
            "bank_accounts",
            "bank_transactions",
            "journals",
            "posting_sources",
            "qbo_application_records",
            "qbo_review_items",
            "qbo_decisions",
            "ap_vendors",
            "ap_vendor_mappings",
        )
    )

    safe_source_dispositions = {
        "sealed_source_records": source_count,
        "relationship_identities": _integer(acquisition, "relationship_ids_preserved"),
        "payment_invoice_links": _integer(payment, "invoice_links"),
        "missing_linked_invoice_ids": _integer(payment, "missing_linked_invoice_ids"),
        "balanced_source_journal_entries": source_counts["journal_entry"],
        "balanced_source_journal_posting_lines": _integer(journal, "posting_lines"),
        "bounded_zero_count_families": len(
            cast(Sequence[object], acquisition.get("zero_count_families", ()))
        ),
        "disposition": "REGISTER_AS_SOURCE_EVIDENCE_OR_EXPLICIT_HOLD_ONLY",
        "native_posting_authority": "NONE",
    }

    held_native_records = {
        "chart_of_accounts": {
            "count": source_counts["account"],
            "reason": "exact_native_account_mapping_and_finance_classification_required",
        },
        "customer_receivable_invoices": {
            "count": source_counts["invoice"],
            "source_open_balance": str(invoice.get("open_balance")),
            "reason": "customer_mapping_overlap_control_and_ar_bridge_required",
        },
        "payments": {
            "count": source_counts["payment"],
            "unlinked_count": _integer(payment, "without_links"),
            "unlinked_total": str(payment.get("without_links_total")),
            "provider_unapplied_total": str(payment.get("unapplied_amount")),
            "reason": "historical_payment_contract_and_unapplied_cash_disposition_required",
        },
        "general_ledger_and_opening_state": {
            "journal_entries": source_counts["journal_entry"],
            "reason": "per_account_mapping_complete_control_ties_and_finance_approval_required",
        },
        "purchases_deposits_transfers": {
            "count": (
                source_counts["purchase"]
                + source_counts["deposit"]
                + source_counts["transfer"]
            ),
            "reason": "historical_double_entry_contract_and_duplicate_prevention_required",
        },
        "american_express_bank_feed": {
            "count": _integer(bank_feed, "authoritative_pending_rows"),
            "exact_repeated_rows": _integer(bank_feed, "exact_duplicate_rows"),
            "reason": "unposted_evidence_without_stable_source_ids",
        },
        "payroll": {
            "employee_records": _integer(payroll, "employee_records"),
            "reason": "separate_payroll_authority_and_coverage_reconciliation_required",
        },
    }

    plan: dict[str, object] = {
        "schema_version": PLAN_SCHEMA,
        "state": "PREPARED_BLOCKED_BEFORE_NATIVE_WRITES",
        "source_binding": {
            "source_run_id": acquisition.get("run_id"),
            "source_manifest_sha256": acquisition.get("manifest_sha256"),
            "bounded_snapshot_sha256": acquisition.get("bounded_snapshot_sha256"),
            "manual_custody_manifest_sha256": readiness["source_manifest_sha256"],
            "manual_custody_set_sha256": _read_mapping(
                root / "custody-manifest.json"
            ).get("custody_set_sha256"),
            "record_count": source_count,
            "cutoff": acquisition.get("cutoff"),
        },
        "current_native_inventory": {
            "financial_control_rows": native_financial_rows,
            "native_invoices": _integer(inventory, "native_invoices"),
            "native_invoice_lines": _integer(inventory, "native_invoice_lines"),
            "native_payments": _integer(inventory, "native_payments"),
            "overlap_policy": "EXACT_SOURCE_ID_OR_EXPLICIT_APPROVAL_NEVER_NAME_MATCH",
        },
        "safe_now": safe_source_dispositions,
        "held_from_native_admission": held_native_records,
        "conflicts": conflicts,
        "phases": _phases(source_count),
        "acceptance_controls": _acceptance_controls(),
        "backup_and_rollback": _backup_and_rollback(),
        "write_assertions": {
            "qbo_operations": 0,
            "native_rows_created_by_plan": 0,
            "bank_feed_postings": 0,
            "payroll_actions": 0,
            "actual_transactions_posted": 0,
        },
        "next_executable_action": (
            "retrieve_and_custody_verify_the_original_bounded_envelope_store_then_"
            "run_disposition_only_application_in_a_disposable_database"
        ),
    }
    plan["plan_sha256"] = _digest(plan)
    return plan


def verify_native_admission_plan(*, archive_root: Path) -> dict[str, object]:
    first = build_native_admission_plan(archive_root=archive_root)
    second = build_native_admission_plan(archive_root=archive_root)
    if first != second:
        raise NativeAdmissionPlanError("admission_plan_not_deterministic")
    return first


def _phases(source_count: int) -> list[dict[str, object]]:
    return [
        {
            "order": 0,
            "name": "immutable_evidence_and_disposition_ledger",
            "state": "BLOCKED_BOUNDED_ENVELOPES_NOT_IN_MANUAL_ARCHIVE",
            "records": source_count,
            "writes": "source_dispositions_only_no_accounting_facts",
            "gate": "exact_bounded_envelope_store_and_digest_available_read_only",
        },
        {
            "order": 1,
            "name": "chart_of_accounts",
            "state": "BLOCKED_MAPPING_APPROVAL",
            "writes": "versioned_chart_and_exact_source_identities",
            "gate": "all_131_accounts_mapped_classified_and_overlap_checked",
        },
        {
            "order": 2,
            "name": "historical_subledgers",
            "state": "BLOCKED_CONTRACT_AND_AR_RECONCILIATION",
            "writes": "customers_invoices_payments_and_explicit_applications",
            "gate": "native_contracts_customer_bindings_and_100801_91_ar_bridge_accepted",
        },
        {
            "order": 3,
            "name": "opening_state_and_general_ledger",
            "state": "BLOCKED_FINANCE_APPROVAL",
            "writes": "balanced_idempotent_opening_and_historical_journals",
            "gate": "all_control_accounts_tie_no_plug_and_three_distinct_native_actors",
        },
        {
            "order": 4,
            "name": "native_reporting_and_reconciliation",
            "state": "BLOCKED_UPSTREAM_PHASES",
            "writes": "none",
            "gate": "trial_balance_balance_sheet_pnl_gl_ar_and_source_parity_all_tie",
        },
    ]


def _acceptance_controls() -> list[dict[str, str]]:
    return [
        {
            "area": "chart_of_accounts",
            "requirement": "131 exact source identities; classifications, parents, currency, active state, and control-account uniqueness approved",
        },
        {
            "area": "opening_balances",
            "requirement": "per-account debit/credit control; balanced; no fabricated plug; AR/AP/cash/card/payroll holds remain excluded until accepted",
        },
        {
            "area": "general_ledger",
            "requirement": "source transaction identity and line provenance; 46,405 versus 46,410 presentation-row difference explained with zero amount variance",
        },
        {
            "area": "trial_balance",
            "requirement": "debits and credits both 2,021,520.50 and native report checksum stable",
        },
        {
            "area": "receivables",
            "requirement": "invoice open 500,584.34 bridged to Balance Sheet A/R 399,782.43 without fabricated links or balances",
        },
        {
            "area": "invoices_and_payments",
            "requirement": "source-ID idempotency, 1,171 exact invoice links, zero missing linked invoices, and 73 unlinked payments held",
        },
        {
            "area": "financial_reporting",
            "requirement": "native GL, Trial Balance, Balance Sheet and P&L reproduce accepted controls at the same cutoff and basis",
        },
        {
            "area": "reconciliation",
            "requirement": "all seven conflicts retained as open or explicitly accountant-resolved; no automatic resolution",
        },
    ]


def _backup_and_rollback() -> dict[str, object]:
    return {
        "before_any_write": [
            "candidate_bound_database_backup",
            "sha256_receipt",
            "isolated_restore_and_schema_verification",
            "native_inventory_and_source_parity_snapshot",
        ],
        "rehearsal": "single_disposable_database_transaction_rollback_with_zero_committed_rows",
        "execution": "phase_boundaries_with_idempotency_and_receipts",
        "rollback": (
            "restore_verified_pre_admission_backup; never delete posted journals or "
            "rewrite source evidence in place"
        ),
        "post_restore_verification": [
            "schema_head",
            "inventory_digest",
            "tenant_isolation",
            "native_report_checksums",
        ],
    }


def _validate_controls(controls: Mapping[str, Any]) -> None:
    trial = _mapping(controls, "trial_balance")
    balance = _mapping(controls, "balance_sheet")
    profit = _mapping(controls, "profit_and_loss")
    ledger = _mapping(controls, "general_ledger")
    journal = _mapping(controls, "journal_export")
    required_zeroes = (
        trial.get("difference"),
        balance.get("equation_difference"),
        balance.get("provider_difference"),
        profit.get("provider_difference"),
        profit.get("balance_sheet_net_income_difference"),
        ledger.get("amount_difference"),
        journal.get("difference"),
    )
    if any(str(value) != "0.00" for value in required_zeroes):
        raise NativeAdmissionPlanError("financial_control_variance_present")


def _require_no_writes(rehearsal: Mapping[str, Any]) -> None:
    assertions = _mapping(rehearsal, "write_assertions")
    if assertions.get("database_transaction") != "READ_ONLY" or any(
        _integer(assertions, key) != 0
        for key in (
            "application_records_created",
            "accounting_facts_created",
            "qbo_operations",
        )
    ):
        raise NativeAdmissionPlanError("rehearsal_write_boundary_invalid")


def _conflicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise NativeAdmissionPlanError("conflict_register_invalid")
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for value_row in value:
        if not isinstance(value_row, Mapping):
            raise NativeAdmissionPlanError("conflict_register_invalid")
        row = {str(key): item for key, item in value_row.items()}
        conflict_id = row.get("id")
        if not isinstance(conflict_id, str) or conflict_id in seen:
            raise NativeAdmissionPlanError("conflict_register_invalid")
        seen.add(conflict_id)
        rows.append(row)
    return rows


def _read_mapping(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise NativeAdmissionPlanError(f"sealed_json_unreadable:{path.name}") from error
    if not isinstance(value, dict):
        raise NativeAdmissionPlanError(f"sealed_json_invalid:{path.name}")
    return cast(dict[str, Any], value)


def _mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    child = value.get(key)
    if not isinstance(child, Mapping):
        raise NativeAdmissionPlanError(f"required_mapping_missing:{key}")
    return cast(Mapping[str, Any], child)


def _integer(value: Mapping[str, Any], key: str) -> int:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, int):
        raise NativeAdmissionPlanError(f"required_integer_missing:{key}")
    return item


def _integer_mapping(value: Mapping[str, Any], key: str) -> dict[str, int]:
    child = _mapping(value, key)
    result: dict[str, int] = {}
    for child_key, child_value in child.items():
        if isinstance(child_value, bool) or not isinstance(child_value, int):
            raise NativeAdmissionPlanError(f"invalid_integer_mapping:{key}")
        result[str(child_key)] = child_value
    return result


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
