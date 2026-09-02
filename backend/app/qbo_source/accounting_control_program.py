"""Successor Accounting-control readiness over registered real-QBO controls."""

from __future__ import annotations

import hashlib
import json

from .evidence import (
    ControlEvidenceRegistry,
    EvidenceStoreError,
    ProtectedFilesystemEvidenceStore,
)

_AUTHORITIES = (
    "qbo-current-environment-authority-v1",
    "qbo-transition-ledger-control-2024-02-19-v1",
    "qbo-transition-cash-balance-control-2024-02-19-v1",
)


def seal_accounting_control_program(
    *, store: ProtectedFilesystemEvidenceStore
) -> dict[str, object]:
    controls: dict[str, str] = {}
    for authority_id in _AUTHORITIES:
        path = store.root / "controls" / f"{authority_id}.json"
        authority_document = store._read_json(path)
        if authority_document.get("evidence_digest") != _digest_without_evidence(
            authority_document
        ):
            raise EvidenceStoreError("accounting_control_authority_digest_invalid")
        controls[authority_id] = hashlib.sha256(path.read_bytes()).hexdigest()
    document: dict[str, object] = {
        "schema_version": "migration-accounting-control-admission-program/v2",
        "historical_reporting_basis": "CASH",
        "full_available_history": "PRESERVED",
        "current_qbo_environment_authority_date": "2024-02-19",
        "registered_authorities": controls,
        "opening_state": {
            "ledger": "TRANSITION_CONTROL_ACCEPTED",
            "cash_reporting": "TRANSITION_CONTROL_ACCEPTED",
            "operational_ar": "CONTROL_REPORT_REQUIRED",
            "operational_ap": "CONTROL_REPORT_REQUIRED",
            "bank_cash": "ACCOUNT_LEVEL_EXTERNAL_CONTROL_REQUIRED",
            "credit_cards": "ACCOUNT_LEVEL_EXTERNAL_CONTROL_REQUIRED",
            "undeposited_funds": "ACCOUNT_QUICKREPORT_REQUIRED",
            "other_liabilities": "OWNER_ACCOUNTANT_CLASSIFICATION_REQUIRED",
            "equity": "OWNER_ACCOUNTANT_CLASSIFICATION_REQUIRED",
            "fabricated_opening_journal": "PROHIBITED",
        },
        "coa": {
            "source_accounts": 130,
            "mechanically_classified": 38,
            "owner_accountant_decision": 92,
            "decision_reduction": "NO_ADDITIONAL_SAFE_REDUCTION_FROM_AGGREGATE_REPORTS",
        },
        "controls": {
            "cash_continuity": "TRANSITION_ACCEPTED_CUTOFF_CONTINUITY_PENDING",
            "ar": "AR_AGING_DETAIL_REQUIRED",
            "ap": "AP_AGING_DETAIL_REQUIRED",
            "bank_cash": "PER_ACCOUNT_QUICKREPORT_AND_EXTERNAL_RECONCILIATION_REQUIRED",
            "credit_cards": "PER_ACCOUNT_QUICKREPORT_AND_STATEMENT_REQUIRED",
            "liability_equity": "AGGREGATE_CONTROL_ACCEPTED_CLASSIFICATION_PENDING",
        },
        "source_authority": {
            "operational_job_estimate": "HCP",
            "accounting_ledger_and_settlement": "QBO_CONTROLLED_PENDING_ADMISSION",
            "native_admitted_truth": "ACP_NATIVE",
            "economics": "SEPARATE_ACCEPTED_ECONOMIC_EVIDENCE",
        },
        "preserved_dispositions": {
            "canceled_job_balance_holds": 296,
            "unlinked_estimate_evidence_only": 24,
            "employee_candidates": 6,
            "employee_exclusion": 1,
            "branch_candidate": 1,
        },
        "combined_rehearsal": {
            "state": "DEPENDENCY_SAFE_PREPARATION_COMPLETE",
            "accounting_admission": "BLOCKED_BY_CUTOFF_SUBLEDGER_CONTROLS",
            "population_invariants": "UNCHANGED",
            "source_freeze": "NOT_AUTHORIZED",
            "production_activation": "NOT_AUTHORIZED",
        },
        "next_owner_evidence": {
            "report": "Accounts Receivable Aging Detail",
            "basis": "accrual_operational",
            "as_of": "2026-08-31",
            "purpose": "cutoff open-invoice and AR-control reconciliation",
        },
    }
    document["evidence_digest"] = _digest(document)
    authority_digest = ControlEvidenceRegistry(store).register_authority_document(
        authority_id="migration-accounting-control-admission-program-v2",
        document=document,
    )
    return {
        "state": "ACCOUNTING_CONTROL_PROGRAM_READY_AT_AR_EVIDENCE_GATE",
        "authority_digest": authority_digest,
        "opening_ledger": "ACCEPTED",
        "opening_cash_reporting": "ACCEPTED",
        "coa_source_accounts": 130,
        "coa_owner_accountant_decisions": 92,
        "canceled_job_holds": 296,
        "unlinked_estimates": 24,
        "next_report": "AR_AGING_DETAIL_2026-08-31",
    }


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _digest_without_evidence(document: dict[str, object]) -> str:
    return _digest(
        {key: value for key, value in document.items() if key != "evidence_digest"}
    )
