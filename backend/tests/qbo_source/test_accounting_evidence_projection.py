from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.qbo_source.accounting_evidence_projection import (
    QboEvidenceProjectionError,
    project_latest_qbo_workspace,
    unavailable_qbo_workspace,
)


def _write_json(path: Path, value: object) -> bytes:
    content = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return content


def _source(root: Path, kind: str, row: dict[str, object]) -> dict[str, str]:
    content = json.dumps(row, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(content).hexdigest()
    path = root / "blobs" / digest[:2] / digest
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {"entity_kind": kind, "native_id": str(row["Id"]), "raw_sha256": digest}


def _evidence_root(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "protected"
    runtime = tmp_path / "runtime"
    entities = [
        _source(
            root,
            "company_info",
            {"Id": "company-123456", "CompanyName": "All County Example"},
        ),
        _source(
            root,
            "account",
            {
                "Id": "a-1",
                "Name": "Checking",
                "AccountType": "Bank",
                "CurrentBalance": "10.00",
                "CurrencyRef": {"value": "USD"},
            },
        ),
        _source(
            root,
            "invoice",
            {
                "Id": "i-1",
                "DocNumber": "1001",
                "TxnDate": "2026-09-01",
                "TotalAmt": "12.00",
                "Balance": "2.00",
                "CustomerRef": {"value": "c-1", "name": "Customer label"},
                "CurrencyRef": {"value": "USD"},
            },
        ),
        _source(
            root,
            "payment",
            {
                "Id": "p-1",
                "TxnDate": "2026-09-02",
                "TotalAmt": "10.00",
                "CurrencyRef": {"value": "USD"},
                "Line": [{"LinkedTxn": [{"TxnId": "i-1"}]}],
            },
        ),
        _source(
            root, "vendor", {"Id": "v-1", "DisplayName": "Vendor label", "Active": True}
        ),
        _source(
            root,
            "bill",
            {
                "Id": "b-1",
                "DocNumber": "B-1",
                "TxnDate": "2026-09-03",
                "DueDate": "2026-10-03",
                "TotalAmt": "5.00",
                "Balance": "5.00",
                "VendorRef": {"value": "v-1", "name": "Vendor label"},
                "CurrencyRef": {"value": "USD"},
            },
        ),
    ]
    _write_json(
        root / "runs" / "run-1" / "manifest.json",
        {
            "state": "complete",
            "ended_at": "2026-09-10T20:00:00+00:00",
            "snapshot": {
                "environment": "production",
                "snapshot_id": "run-1",
                "realm_id": "realm-1",
                "api_minor_version": 75,
                "accounting_date_cutoff": "2026-09-10",
            },
            "company_name": "All County Example",
            "entities": entities,
            "entity_counts": {
                "account": 1,
                "bill": 1,
                "company_info": 1,
                "invoice": 1,
                "payment": 1,
                "vendor": 1,
            },
            "pages": [
                {"entity_kind": "account", "page": 1},
                {"entity_kind": "invoice", "page": 1},
                {"entity_kind": "payment", "page": 1},
            ],
            "catalog_dispositions": [
                {
                    "entity_kind": "time_activity",
                    "requirement": "OPTIONAL_PROVIDER_DEPENDENT",
                    "disposition": "PROVIDER_FAMILY_UNAVAILABLE",
                }
            ],
        },
    )
    _write_json(
        root / "controls" / "p-and-l.json",
        {
            "schema_version": "qbo-control-registration/v1",
            "control_id": "p-and-l",
            "kind": "profit_and_loss",
            "accounting_basis": "cash",
            "report_end_date": "2026-09-10",
        },
    )
    _write_json(
        runtime / "connections" / "verified.json",
        {
            "environment": "production",
            "acquisition_eligible": True,
            "realm_id": "realm-1",
            "company_name": "All County Example",
            "company_info_id": "company-123456",
            "api_minor_version": 75,
            "company_info_verified_at": "2026-09-10T19:59:00+00:00",
        },
    )
    return root, runtime


def test_projection_matches_om2b_contract_without_promoting_accounting_truth(
    tmp_path: Path,
) -> None:
    root, runtime = _evidence_root(tmp_path)
    result = project_latest_qbo_workspace(
        evidence_root=root, runtime_root=runtime, basis="cash"
    )
    assert result["source"] == "quickbooks_online"
    assert result["contract_version"] == "qbo-accounting-evidence/v1"
    assert result["mode"] == "live"
    assert result["provider_environment"] == "production"
    assert len(result["company_identity_sha256"]) == 64
    assert result["company_info_verified_at"] == "2026-09-10T19:59:00+00:00"
    assert result["source_manifest_sha256"] == result["snapshot_digest"]
    assert result["source_company_label"] == "All County Example"
    assert result["source_company_id_masked"] == "…3456"
    assert result["refresh_state"] == "available"
    assert result["provider_authorization"] == "verified_current"
    assert result["evidence_mode"] == "current_authorized_snapshot"
    assert result["completeness"] == "complete"
    assert result["entity_counts"]["invoice"] == 1
    assert result["page_counts"]["invoice"] == 1
    assert result["catalog_dispositions"][0]["entity_kind"] == "time_activity"
    assert result["is_live"] is False
    assert result["mutation_authority"] == "none"
    assert result["accounts"][0]["balance"]["amount"] == "10.00"
    assert result["invoices"][0]["open_balance"]["amount"] == "2.00"
    assert result["ar"]["total_open"]["amount"] == "2.00"
    assert result["ar"]["overdue"]["amount"] is None
    assert result["payments"][0]["applied_document_ids"] == ["i-1"]
    assert result["vendors"][0]["source_evidence_only"] is True
    assert result["bills"][0]["open_balance"]["amount"] == "5.00"
    assert result["reports"][0]["basis"] == "cash"
    assert "qbo_source_reported_not_posted_acp_ledger" in result["limitations"]


def test_nonproduction_snapshot_is_rejected(tmp_path: Path) -> None:
    root, runtime = _evidence_root(tmp_path)
    path = root / "runs" / "run-1" / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["snapshot"]["environment"] = "sandbox"
    _write_json(path, manifest)
    with pytest.raises(QboEvidenceProjectionError, match="non_production"):
        project_latest_qbo_workspace(
            evidence_root=root, runtime_root=runtime, basis="cash"
        )


def test_absent_evidence_is_unknown_not_zero_or_live(tmp_path: Path) -> None:
    result = project_latest_qbo_workspace(
        evidence_root=tmp_path / "absent", basis="accrual"
    )
    assert result == unavailable_qbo_workspace(
        basis="accrual", limitation="production_qbo_evidence_unavailable"
    )
    assert result["ar"]["total_open"]["amount"] is None
    assert result["is_live"] is False
    assert result["mode"] == "blocked"


def test_preserved_snapshot_is_stale_not_live_when_current_oauth_is_absent(
    tmp_path: Path,
) -> None:
    root, _ = _evidence_root(tmp_path)
    result = project_latest_qbo_workspace(evidence_root=root, basis="cash")
    assert result["refresh_state"] == "stale"
    assert result["mode"] == "historical"
    assert result["company_info_verified_at"] is None
    assert result["provider_authorization"] == "unverified"
    assert result["evidence_mode"] == "historical_snapshot"
    assert (
        "current_provider_authorization_unverified_historical_snapshot"
        in result["limitations"]
    )


def test_verified_realm_conflict_fails_closed(tmp_path: Path) -> None:
    root, runtime = _evidence_root(tmp_path)
    marker_path = runtime / "connections" / "verified.json"
    marker = json.loads(marker_path.read_text())
    marker["realm_id"] = "other-realm"
    _write_json(marker_path, marker)
    with pytest.raises(QboEvidenceProjectionError, match="authorization_conflict"):
        project_latest_qbo_workspace(
            evidence_root=root, runtime_root=runtime, basis="cash"
        )
