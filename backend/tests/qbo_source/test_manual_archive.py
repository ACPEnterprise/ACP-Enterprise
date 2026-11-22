from pathlib import Path

import pytest
from app.qbo_source.accounting_evidence_projection import project_latest_qbo_workspace
from app.qbo_source.errors import QboEvidenceProjectionError
from app.qbo_source.manual_archive import project_manual_archive

ARCHIVE = Path(
    "/Users/michaelfouse/ReleaseEvidence/qbo-accounting-acquisition-20261119"
)


@pytest.mark.skipif(
    not ARCHIVE.is_dir(), reason="sealed laptop custody package unavailable"
)
def test_manual_archive_projects_verified_source_counts_without_native_posting() -> (
    None
):
    result = project_manual_archive(root=ARCHIVE, basis="accrual")

    assert len(result["accounts"]) == 131
    assert len(result["invoices"]) == 1341
    assert len(result["vendors"]) == 868
    assert result["entity_counts"]["purchase"] == 12414
    assert result["ar"]["total_open"]["amount"] == "500584.34"
    assert result["mutation_authority"] == "none"
    assert "source_reported_not_posted_acp_ledger" in result["limitations"]


@pytest.mark.skipif(
    not ARCHIVE.is_dir(), reason="sealed laptop custody package unavailable"
)
def test_manual_archive_is_used_only_when_bounded_evidence_is_absent() -> None:
    result = project_latest_qbo_workspace(
        evidence_root=ARCHIVE / "missing-bounded-root",
        basis="accrual",
        manual_archive_root=ARCHIVE,
    )

    assert result["evidence_mode"] == "sealed_manual_archive"
    assert result["mode"] == "historical"


def test_manual_archive_rejects_invalid_custody_contract(tmp_path: Path) -> None:
    (tmp_path / "custody-manifest.json").write_text('{"contract":"wrong"}')
    with pytest.raises(
        QboEvidenceProjectionError, match="manual_archive_contract_invalid"
    ):
        project_manual_archive(root=tmp_path, basis="accrual")
