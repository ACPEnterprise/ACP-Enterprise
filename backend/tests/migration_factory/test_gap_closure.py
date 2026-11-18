import json
from pathlib import Path

from app.migration_factory.certification import (
    CertificationStatus,
    CommercialSupportLabel,
    commercial_support_label,
)
from app.migration_factory.gap_closure import (
    audit_hcp_retained_evidence,
    protected_runtime_availability,
)


def write_page(root: Path, family: str, records: list[dict[str, object]]) -> None:
    target = root / "raw" / family
    target.mkdir(parents=True, exist_ok=True)
    (target / "page-0001.json").write_text(json.dumps({family: records}))


def retained_source(root: Path) -> Path:
    (root / "acquisition-package-manifest.json").write_text(
        json.dumps(
            {
                "contract": "hcp-source-4-acquisition-package/v1",
                "request_methods": ["GET"],
            }
        )
    )
    write_page(root, "customers", [{"id": "c1", "addresses": [{"id": "l1"}]}])
    write_page(
        root,
        "jobs",
        [{"id": "j1", "customer": {"id": "c1"}, "address": {"id": "l1"}}],
    )
    write_page(
        root,
        "invoices",
        [
            {
                "id": "i1",
                "job_id": "j1",
                "payments": [{"id": "p1"}],
                "refunds": [
                    {"id": "r1", "payment_id": "p1"},
                    {"id": None},
                ],
            }
        ],
    )
    (root / "relationship-appointments-manifest.json").write_text(
        json.dumps(
            {
                "artifacts": [
                    {"http_status": 200},
                    {"http_status": 400, "parent_state": "deleted"},
                    {"http_status": 503, "retryable": True},
                ]
            }
        )
    )
    return root


def test_gap_audit_is_conservative_and_complete(tmp_path: Path) -> None:
    result = audit_hcp_retained_evidence(retained_source(tmp_path))
    result.verify()
    assert result.payments["status"] == CertificationStatus.QUALIFIED_LIVE
    assert result.payments["duplicate_count"] == 0
    assert result.refunds["status"] == CertificationStatus.PARTIAL
    assert result.refunds["unidentified_count"] == 1
    assert result.appointments["original_failure_count"] == 2
    assert result.appointments["true_unrecoverable_count"] == 2
    assert result.appointments["failure_reasons"] == {
        "DELETED_HISTORICAL_PARENT": 1,
        "RETRYABLE": 1,
    }
    assert result.locations["status"] == CertificationStatus.QUALIFIED_LIVE
    assert result.attachments["status"] == CertificationStatus.BLOCKED_PROVIDER


def test_runtime_check_never_reads_secret_files(tmp_path: Path) -> None:
    result = protected_runtime_availability(
        hcp_root=str(tmp_path), qbo_runtime_root=None, qbo_evidence_root="/missing"
    )
    assert result == {
        "hcp_evidence": True,
        "qbo_runtime": False,
        "qbo_evidence": False,
    }


def test_commercial_labels_never_promote_connection_state() -> None:
    assert (
        commercial_support_label(
            (CertificationStatus.QUALIFIED_LIVE, CertificationStatus.PARTIAL)
        )
        is CommercialSupportLabel.PARTIALLY_CERTIFIED
    )
    assert (
        commercial_support_label((CertificationStatus.IMPLEMENTED_UNQUALIFIED,))
        is CommercialSupportLabel.AWAITING_PROVIDER_ACCESS
    )
