from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.operational_migration.hcp_control_closure import (
    BranchMappingCandidate,
    ControlExportType,
    PaymentDateRange,
    ReadinessImpact,
    ReconciliationClassification,
    TechnicianCrosswalkSource,
    financial_conflict,
    intake_csv_control,
    reconcile_native_evidence,
    seal_control_manifest,
    unsupported_relationship,
    validate_payment_ranges,
)
from app.operational_migration.hcp_readonly_extractor import ProtectedEvidenceStore
from app.operational_migration.hcp_source_acquisition import SourceAssertion

SHA = "a" * 64


def entry(tmp_path: Path, kind: ControlExportType, company: str = SHA):
    root = tmp_path / kind.value
    return intake_csv_control(
        store=ProtectedEvidenceStore(root), artifact_name=f"{kind.value}.csv",
        source=b"Native ID,Status\n1,source-value\n", control_type=kind,
        source_report_identity=f"housecall_pro/{kind.value}/v1",
        extraction_timestamp=datetime(2026, 8, 26, 12, tzinfo=ZoneInfo("America/New_York")),
        timezone="America/New_York", filters={"scope": "unfiltered"},
        exporting_admin_evidence_sha256=SHA, company_identity_sha256=company,
    )


def test_intake_and_manifest_are_immutable_and_company_scoped(tmp_path: Path) -> None:
    entries = [entry(tmp_path, kind) for kind in ControlExportType]
    manifest = seal_control_manifest("controls-1", entries)
    assert len(manifest.entries) == 5
    assert len(manifest.manifest_sha256) == 64
    assert all(item.row_count == 1 and item.byte_size > 0 for item in entries)
    assert all((tmp_path / item.control_type.value / item.protected_artifact_name).stat().st_mode & 0o777 == 0o600 for item in entries)
    entries[-1] = entry(tmp_path / "other", ControlExportType.PAYMENT_DETAILS, "b" * 64)
    with pytest.raises(ValueError, match="cross Company"):
        seal_control_manifest("controls-2", entries)


def test_payment_partitions_are_contiguous_without_duplicate_dates() -> None:
    ranges = validate_payment_ranges((PaymentDateRange(date(2026, 2, 1), date(2026, 2, 28)), PaymentDateRange(date(2026, 1, 1), date(2026, 1, 31))))
    assert ranges[0].start == date(2026, 1, 1)
    with pytest.raises(ValueError, match="contiguous"):
        validate_payment_ranges((PaymentDateRange(date(2026, 1, 1), date(2026, 1, 31)), PaymentDateRange(date(2026, 1, 31), date(2026, 2, 28))))


def test_reconciliation_preserves_missing_conflicting_and_unsupported() -> None:
    results = reconcile_native_evidence(entity="job", api={"1": SHA, "2": SHA, "3": SHA}, control={"1": SHA, "2": "b" * 64, "4": SHA})
    assert [item.classification for item in results] == [ReconciliationClassification.MATCHED, ReconciliationClassification.CONFLICTING, ReconciliationClassification.CONTROL_EXPORT_MISSING, ReconciliationClassification.SOURCE_API_MISSING]
    assert unsupported_relationship("payment", "application").classification is ReconciliationClassification.UNSUPPORTED_RELATIONSHIP


def test_financial_conflict_keeps_both_source_assertions() -> None:
    evidence = financial_conflict(SourceAssertion("housecall_pro", "invoice", "h1", "status", "paid", SHA), SourceAssertion("quickbooks_online", "invoice", "q1", "status", "open", "b" * 64))
    assert evidence.classification == "conflict"
    assert {item.original_value for item in evidence.assertions} == {"paid", "open"}


def test_review_packets_do_not_claim_owner_mapping() -> None:
    branch = BranchMappingCandidate(SHA, None, ("b" * 64,), "unresolved")
    tech = TechnicianCrosswalkSource(SHA, "b" * 64, None, (), "c" * 64, ())
    assert branch.candidate_enterprise_branch_id is None
    assert tech.enterprise_employee_id is None
    assert ReadinessImpact.BLOCKS_OPEN_WORK_CUTOVER.value == "blocks_open_work_cutover"
