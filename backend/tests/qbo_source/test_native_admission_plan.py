from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.qbo_source.native_admission_plan import (
    EXPECTED_CONFLICT_IDS,
    NativeAdmissionPlanError,
    build_native_admission_plan,
    verify_native_admission_plan,
)
from scripts.qualify_qbo_native_admission import write_private_output


def _archive(tmp_path: Path) -> Path:
    root = tmp_path / "archive"
    raw = root / "raw"
    raw.mkdir(parents=True)
    account = raw / "All County Plumbing and Leak_Account List.xlsx"
    account.write_bytes(b"sealed-account-report")
    import hashlib

    file_digest = hashlib.sha256(account.read_bytes()).hexdigest()
    custody = {
        "contract": "qbo-manual-archive-custody/v1",
        "sealed_at": "2026-11-20T00:00:00+00:00",
        "custody_set_sha256": "c" * 64,
        "files": [
            {
                "name": "All County Plumbing and Leak_Account List.xlsx",
                "bytes": account.stat().st_size,
                "sha256": file_digest,
            }
        ],
    }
    counts = {
        "account": 2,
        "company_info": 1,
        "customer": 3,
        "deposit": 4,
        "employee": 1,
        "invoice": 5,
        "item": 1,
        "journal_entry": 1,
        "payment": 3,
        "payment_method": 1,
        "purchase": 6,
        "refund_receipt": 1,
        "term": 1,
        "transfer": 1,
        "vendor": 2,
    }
    manifest_digest = "a" * 64
    bounded_digest = "b" * 64
    acquisition = {
        "run_id": "sealed-test-run",
        "cutoff": "2026-11-19",
        "record_count": sum(counts.values()),
        "manifest_sha256": manifest_digest,
        "bounded_snapshot_sha256": bounded_digest,
        "counts": counts,
        "zero_count_families": ["bill"],
        "relationship_ids_preserved": 10,
        "invoice": {"open_balance": "500584.34"},
        "payment": {
            "invoice_links": 2,
            "missing_linked_invoice_ids": 0,
            "without_links": 1,
            "without_links_total": "12.00",
            "unapplied_amount": "14.00",
        },
        "journal": {"posting_lines": 2},
    }
    inventory = {
        key: 0
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
    }
    inventory.update(
        {"native_invoices": 2, "native_invoice_lines": 3, "native_payments": 1}
    )
    zero = "0.00"
    controls = {
        "trial_balance": {"difference": zero},
        "balance_sheet": {"equation_difference": zero, "provider_difference": zero},
        "profit_and_loss": {
            "provider_difference": zero,
            "balance_sheet_net_income_difference": zero,
        },
        "general_ledger": {"amount_difference": zero},
        "journal_export": {"difference": zero},
    }
    conflicts = [
        {"id": conflict_id, "classification": "PRESERVED", "next_action": "review"}
        for conflict_id in EXPECTED_CONFLICT_IDS
    ]
    register = {
        "current_acquisition": acquisition,
        "twelvehats_existing_inventory": inventory,
        "report_reconciliation": controls,
        "bank_feed_evidence": {
            "authoritative_pending_rows": 102,
            "exact_duplicate_rows": 4,
        },
        "payroll_reconstruction": {"employee_records": 30},
        "discrepancies": conflicts,
    }
    rehearsal = {
        "state": "REHEARSAL_COMPLETE_NO_WRITES",
        "source_record_count": sum(counts.values()),
        "source_family_counts": counts,
        "source_manifest_sha256": manifest_digest,
        "bounded_snapshot_sha256": bounded_digest,
        "write_assertions": {
            "database_transaction": "READ_ONLY",
            "application_records_created": 0,
            "accounting_facts_created": 0,
            "qbo_operations": 0,
        },
    }
    (root / "custody-manifest.json").write_text(json.dumps(custody))
    (root / "reconciliation-register.json").write_text(json.dumps(register))
    (root / "native-admission-rehearsal.v1.json").write_text(json.dumps(rehearsal))
    return root


def test_plan_preserves_all_conflicts_and_authorizes_no_native_writes(
    tmp_path: Path,
) -> None:
    plan = verify_native_admission_plan(archive_root=_archive(tmp_path))
    assert plan["state"] == "PREPARED_BLOCKED_BEFORE_NATIVE_WRITES"
    assert [item["id"] for item in plan["conflicts"]] == list(EXPECTED_CONFLICT_IDS)
    assert plan["safe_now"]["native_posting_authority"] == "NONE"
    assert plan["write_assertions"] == {
        "qbo_operations": 0,
        "native_rows_created_by_plan": 0,
        "bank_feed_postings": 0,
        "payroll_actions": 0,
        "actual_transactions_posted": 0,
    }
    assert len(plan["plan_sha256"]) == 64


def test_plan_rejects_missing_disclosed_conflict(tmp_path: Path) -> None:
    root = _archive(tmp_path)
    path = root / "reconciliation-register.json"
    register = json.loads(path.read_text())
    register["discrepancies"].pop()
    path.write_text(json.dumps(register))
    with pytest.raises(
        NativeAdmissionPlanError, match="seven_disclosed_conflicts_not_preserved"
    ):
        build_native_admission_plan(archive_root=root)


def test_plan_rejects_source_family_count_drift(tmp_path: Path) -> None:
    root = _archive(tmp_path)
    path = root / "reconciliation-register.json"
    register = json.loads(path.read_text())
    register["current_acquisition"]["counts"]["invoice"] += 1
    path.write_text(json.dumps(register))
    with pytest.raises(NativeAdmissionPlanError, match="source_family_count_mismatch"):
        build_native_admission_plan(archive_root=root)


def test_plan_rejects_rehearsal_that_wrote_rows(tmp_path: Path) -> None:
    root = _archive(tmp_path)
    path = root / "native-admission-rehearsal.v1.json"
    rehearsal = json.loads(path.read_text())
    rehearsal["write_assertions"]["accounting_facts_created"] = 1
    path.write_text(json.dumps(rehearsal))
    with pytest.raises(NativeAdmissionPlanError, match="rehearsal_write_boundary"):
        build_native_admission_plan(archive_root=root)


def test_private_output_is_exclusive_and_mode_0600(tmp_path: Path) -> None:
    plan = verify_native_admission_plan(archive_root=_archive(tmp_path))
    output = tmp_path / "evidence" / "plan.json"
    assert write_private_output(path=output, plan=plan) == plan["plan_sha256"]
    assert output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        write_private_output(path=output, plan=plan)
