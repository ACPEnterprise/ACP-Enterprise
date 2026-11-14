from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.accounting.cutover_evidence import capture_source_baseline, seal_cutover_package


def _workbook() -> dict:
    return {
        "issues": [
            {
                "issue_id": "AR-850",
                "category": "AR",
                "description": "Two source versions disagree on one invoice balance.",
                "affected_accounts_or_entities": ["Accounts Receivable"],
                "dollar_value": "850.00",
                "value_status": "OBSERVED",
                "materiality": "REVIEW_REQUIRED",
                "business_impact": "AR authority is unresolved.",
                "accounting_impact": "AR and P&L acceptance requires a decision.",
                "source_provenance": ["qbo-aging", "qbo-ledger"],
            }
        ],
        "provenance": [
            {
                "provenance_id": "PROV-AR-850",
                "conclusion_id": "AR-850",
                "source_evidence": ["qbo-aging"],
                "conflicting_evidence": ["qbo-ledger"],
                "source_dates": ["2026-08-31"],
                "source_system_authority": "QBO_SOURCE_REPORTED",
                "confidence": "HIGH_CONFLICT_EXPLICIT",
                "unresolved_contradictions": ["source-version conflict"],
                "decision_authority": "ACCOUNTANT",
                "accepted_evidence": [],
                "value_class": "OBSERVED VALUE",
            }
        ],
        "reconciliations": [{"finding_id": "REC-AR-850", "workstream": "AR", "issue_ids": ["AR-850"], "analysis": "No forced resolution.", "source_evidence": ["qbo-aging", "qbo-ledger"], "result": "decision required", "status": "OPEN"}],
        "decisions": [{"decision_id": "DEC-AR-850", "issue_id": "AR-850", "request": "Select accepted source version.", "evidence_for": ["qbo-aging"], "evidence_against": ["qbo-ledger"], "dollar_impact": "850.00", "pnl_effect": "unknown", "balance_sheet_effect": "AR", "tax_payroll_effect": "unknown", "recommendation": "accountant review", "approver_role": "ACCOUNTANT", "status": "OPEN"}],
        "corrections": [],
        "scorecard": {"before": {"ar_difference": "850.00", "unexplained_variance": "850.00"}, "after": {"ar_difference": "UNKNOWN", "unexplained_variance": "UNKNOWN"}},
        "unresolved_external_evidence": ["latest complete All County QBO evidence mount", "accountant decision on AR-850"],
        "milestones": {"SOURCE_BASELINE": {"status": "CAPTURED"}, "DISCOVERY": {"status": "IN_PROGRESS"}},
    }


def test_baseline_is_digest_sealed_and_copies_nonsecret_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "report.xlsx").write_bytes(b"source")
    (source / "credentials.env").write_text("secret")
    result = capture_source_baseline(source_root=source, output_root=tmp_path / "baseline", authority_id="qbo-before", cutoff="2026-08-31")
    assert result["baseline_digest"]
    assert (tmp_path / "baseline/source/report.xlsx").exists()
    assert not (tmp_path / "baseline/source/credentials.env").exists()
    assert (tmp_path / "baseline/source-baseline.json").stat().st_mode & 0o777 == 0o600


def test_seal_package_validates_provenance_and_emits_private_and_sanitized_outputs(tmp_path: Path) -> None:
    result = seal_cutover_package(workbook=_workbook(), output_root=tmp_path / "private", sanitized_root=tmp_path / "sanitized")
    assert result["package_digest"]
    private = json.loads((tmp_path / "private/issue-register.json").read_text())
    sanitized = json.loads((tmp_path / "sanitized/lia-decision-packet-history.json").read_text())
    assert private["issues"][0]["dollar_value"] == "850.00"
    assert sanitized["decisions"][0]["approver_role"] == "ACCOUNTANT"


def test_seal_rejects_issue_without_provenance(tmp_path: Path) -> None:
    workbook = _workbook()
    workbook["provenance"] = []
    with pytest.raises(ValueError, match="lacks provenance"):
        seal_cutover_package(workbook=workbook, output_root=tmp_path / "private", sanitized_root=tmp_path / "sanitized")
