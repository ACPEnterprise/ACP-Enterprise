import pytest
from app.source_history.hcp_packet_recovery import (
    REQUIRED_HCP_CSV_SHA256,
    HcpJobDetail,
    HcpPhotograph,
    recover_hcp_packet,
)


def test_recovers_job_detail_and_photograph_relationships_deterministically() -> None:
    job = HcpJobDetail(
        "job-1", "customer-1", "location-1", "Leak", "Detail", None, "a" * 64
    )
    photo = HcpPhotograph("photo-1", "job-1", "b" * 64, None, "Before repair")
    first = recover_hcp_packet(
        source_csv_sha256=REQUIRED_HCP_CSV_SHA256, jobs=(job,), photographs=(photo,)
    )
    second = recover_hcp_packet(
        source_csv_sha256=REQUIRED_HCP_CSV_SHA256, jobs=(job,), photographs=(photo,)
    )
    assert first == second
    assert first.admissible is True
    assert first.photographs[0].source_job_id == "job-1"
    assert first.read_only is True


def test_missing_photo_parent_is_held_without_fabrication() -> None:
    photo = HcpPhotograph("photo-1", "job-missing", "b" * 64, None, None)
    result = recover_hcp_packet(
        source_csv_sha256=REQUIRED_HCP_CSV_SHA256, jobs=(), photographs=(photo,)
    )
    assert result.admissible is False
    assert result.held_exceptions == ("photo:photo-1:missing_job:job-missing",)


def test_unapproved_source_digest_fails_closed() -> None:
    with pytest.raises(ValueError, match="approved custody"):
        recover_hcp_packet(source_csv_sha256="c" * 64, jobs=(), photographs=())
