from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.qbo_source.accounting_admission import (
    HistoryDecisionAuthority,
    accounting_control_matrix,
    build_coa_mapping_packet,
    cash_basis_control_matrix,
    provision_admission_packet,
    provision_cash_basis_successor_packet,
    seal_full_history_decision,
)
from app.qbo_source.evidence import (
    ControlEvidenceRegistry,
    ProtectedFilesystemEvidenceStore,
)


def test_full_history_decision_is_immutable_and_binds_both_sources(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    store = ProtectedFilesystemEvidenceStore(
        root=tmp_path / "evidence", repository_root=repository
    )
    registry = ControlEvidenceRegistry(store)
    authority = HistoryDecisionAuthority(
        "owner-safe-id",
        datetime(2026, 9, 1, tzinfo=timezone.utc),
        "a" * 64,
        "master-id",
        "b" * 64,
        "2026-08-31",
    )
    first = seal_full_history_decision(registry, authority)
    assert seal_full_history_decision(registry, authority) == first
    document = json.loads(
        (store.root / "controls/full-available-history-g5-v1.json").read_bytes()
    )
    assert document["decision"] == "FULL_AVAILABLE_HISTORY"
    assert document["qbo_bounded_snapshot_digest"] == "a" * 64
    assert document["hcp_master_id"] == "master-id"


def test_admission_rejects_malformed_bounded_entity_collection(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    store = ProtectedFilesystemEvidenceStore(
        root=tmp_path / "evidence", repository_root=repository
    )
    registry = ControlEvidenceRegistry(store)
    run_root = store.root / "runs" / "malformed-run"
    run_root.mkdir(parents=True)
    manifest = run_root / "bounded-manifest.json"
    manifest.write_text(
        json.dumps(
            {"state": "BOUNDED_COMPLETE", "included_entities": {"unsafe": True}}
        ),
        encoding="utf-8",
    )
    authority = HistoryDecisionAuthority(
        "owner-safe-id",
        datetime(2026, 9, 1, tzinfo=timezone.utc),
        hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "master-id",
        "b" * 64,
        "2026-08-31",
    )

    with pytest.raises(TypeError, match="bounded QBO entity evidence is required"):
        provision_admission_packet(
            registry=registry,
            run_id="malformed-run",
            authority=authority,
        )


def test_coa_packet_is_safe_conservative_and_complete() -> None:
    packet = build_coa_mapping_packet((
        {
            "Id": "1", "AccountType": "Accounts Receivable",
            "Active": True, "CurrentBalance": "12.34",
        },
        {
            "Id": "2", "AccountType": "Expense",
            "AccountSubType": "LegalProfessionalFees", "Active": True,
        },
        {"Id": "3", "AccountType": "Income", "Active": False},
    ))
    assert packet["account_count"] == 3
    assert packet["classification_counts"] == {
        "DIRECT_SAFE_MAPPING": 1,
        "INACTIVE": 1,
        "OWNER_FINANCE_DECISION": 1,
    }
    rendered = json.dumps(packet)
    assert '"Id"' not in rendered
    assert "source_identity_digest" in rendered


def test_control_matrix_requires_independent_ar_ap_and_cash_controls() -> None:
    matrix = {row["area"]: row for row in accounting_control_matrix("2026-08-31")}
    assert matrix["AR"]["state"] == "CONTROL_REPORT_REQUIRED"
    assert "A/R Aging Detail" in matrix["AR"]["reports"]
    assert matrix["AP"]["state"] == "CONTROL_REPORT_REQUIRED"
    assert matrix["cash_bank"]["state"] == "CONTROL_REPORT_REQUIRED"
    assert matrix["opening_balance_sheet"]["as_of"] == "2021-07-06"


def test_cash_basis_controls_preserve_operational_ar_ap_and_ledger() -> None:
    matrix = {row["authority"]: row for row in cash_basis_control_matrix("2026-08-31")}
    assert matrix["historical_cash_results"]["basis"] == "cash"
    assert matrix["open_customer_obligations"]["basis"] == "operational"
    assert matrix["open_vendor_obligations"]["basis"] == "operational"
    assert matrix["complete_ledger_and_opening"]["basis"] == "accrual"


def test_cash_basis_successor_preserves_prior_packets(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    store = ProtectedFilesystemEvidenceStore(
        root=tmp_path / "evidence", repository_root=repository
    )
    registry = ControlEvidenceRegistry(store)
    prior = store.root / "controls/prior.json"
    store._store_named_immutable(prior, b"{}")
    result = provision_cash_basis_successor_packet(
        registry=registry,
        authority=HistoryDecisionAuthority(
            "owner-safe-id", datetime(2026, 9, 1, tzinfo=timezone.utc),
            "a" * 64, "master-id", "b" * 64, "2026-08-31",
        ),
    )
    assert result["state"] == "CASH_BASIS_SUCCESSOR_CONTROL_PACKET_READY"
    assert prior.read_bytes() == b"{}"
    successor = json.loads(
        (store.root / "controls/qbo-g5-accounting-controls-v3-cash.json").read_bytes()
    )
    assert successor["historical_reporting_basis"] == "cash"
    assert successor["admission_rules"]["unpaid_invoice_survives_cash_basis"]
