from __future__ import annotations

from datetime import date
from pathlib import Path

from app.qbo_source.audit_log_analysis import analyze_registered_audit_log
from app.qbo_source.control_report_registration import (
    RegisterControlReport,
    register_control_report,
)
from app.qbo_source.evidence import ControlReportKind, ProtectedFilesystemEvidenceStore


def test_audit_log_proves_current_environment_boundary(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    source = tmp_path / "audit.csv"
    source.write_text(
        "Date Changed,User,Event\n"
        '"Feb 19, 2024, 5:08 pm Eastern Standard Time",Import Administration,Imported QuickBooks desktop edition company\n'
        '"Feb 19, 2024, 5:02 pm Eastern Standard Time",Import Administration,Purge data\n'
        '"Feb 19, 2024, 5:02 pm Eastern Standard Time",Import Administration,Added account Opening Balance Equity\n'
        '"Feb 19, 2024, 5:02 pm Eastern Standard Time",Import Administration,Edited account Opening Balance Equity\n'
    )
    source.chmod(0o600)
    root = tmp_path / "protected"
    registration = register_control_report(
        command=RegisterControlReport(
            source_file=source,
            control_id="qbo-current-environment-audit-log-v1",
            kind=ControlReportKind.AUDIT_LOG,
            basis="operational",
            start_date=date(2024, 2, 19),
            end_date=date(2024, 2, 19),
        ),
        evidence_root=root,
        repository_root=repository,
    )
    result = analyze_registered_audit_log(
        store=ProtectedFilesystemEvidenceStore(root=root, repository_root=repository),
        control_id="qbo-current-environment-audit-log-v1",
        expected_raw_sha256=str(registration["raw_sha256"]),
    )
    assert result["state"] == "CURRENT_QBO_ENVIRONMENT_BOUNDARY_PROVED"
    assert result["purge_event"] == 1
