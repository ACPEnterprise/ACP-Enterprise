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


def _evidence_root(tmp_path: Path) -> Path:
    root = tmp_path / "protected"
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
                "accounting_date_cutoff": "2026-09-10",
            },
            "entities": entities,
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
    return root


def test_projection_matches_om2b_contract_without_promoting_accounting_truth(
    tmp_path: Path,
) -> None:
    result = project_latest_qbo_workspace(
        evidence_root=_evidence_root(tmp_path), basis="cash"
    )
    assert result["source"] == "quickbooks_online"
    assert result["source_company_label"] == "All County Example"
    assert result["source_company_id_masked"] == "…3456"
    assert result["refresh_state"] == "available"
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
    root = _evidence_root(tmp_path)
    path = root / "runs" / "run-1" / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["snapshot"]["environment"] = "sandbox"
    _write_json(path, manifest)
    with pytest.raises(QboEvidenceProjectionError, match="non_production"):
        project_latest_qbo_workspace(evidence_root=root, basis="cash")


def test_absent_evidence_is_unknown_not_zero_or_live(tmp_path: Path) -> None:
    result = project_latest_qbo_workspace(
        evidence_root=tmp_path / "absent", basis="accrual"
    )
    assert result == unavailable_qbo_workspace(
        basis="accrual", limitation="production_qbo_evidence_unavailable"
    )
    assert result["ar"]["total_open"]["amount"] is None
    assert result["is_live"] is False
