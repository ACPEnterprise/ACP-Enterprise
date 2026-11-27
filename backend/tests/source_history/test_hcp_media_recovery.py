from app.source_history.hcp_media_recovery import (
    AttachmentReference,
    RecoveredMedia,
    artifact_name,
    reconcile_media,
)

URL = "https://housecall-web-request-attachments-production-us-west-2.s3-accelerate.amazonaws.com/attachments/photo.jpg?signature=secret"


def reference(identifier: str, url: str | None = URL) -> AttachmentReference:
    return AttachmentReference(
        identifier,
        "job-1",
        "customer-1",
        "2026-01-01T00:00:00Z",
        "photo.jpg",
        "image/jpeg",
        url,
    )


def test_reconciles_recovered_retrievable_and_missing_bodies() -> None:
    recovered = RecoveredMedia("a-1", "a" * 64, 42, artifact_name("a-1"))
    plan = reconcile_media(
        (reference("a-1"), reference("a-2"), reference("a-3", None)), (recovered,)
    )

    assert [row.disposition for row in plan.items] == [
        "RECOVERED",
        "RETRIEVE",
        "MISSING_BODY",
    ]
    assert plan.counts == {
        "references": 3,
        "recovered": 1,
        "retrieve": 1,
        "missing_body": 1,
        "orphaned_media": 0,
    }
    assert plan.items[1].reference.source_job_id == "job-1"
    assert plan.items[1].signed_get_url_sha256 is not None
    assert "secret" not in plan.plan_digest
    assert plan.http_method_allowlist == ("GET",)
    assert plan.provider_writes_allowed is False


def test_reports_orphaned_media_without_inventing_relationship() -> None:
    orphan = RecoveredMedia("orphan", "b" * 64, 1, artifact_name("orphan"))
    plan = reconcile_media((reference("a-1", None),), (orphan,))
    assert plan.orphaned_media == (orphan,)
    assert plan.counts["orphaned_media"] == 1


def test_rejects_unapproved_url_and_duplicate_identity() -> None:
    try:
        reconcile_media((reference("a-1", "https://example.com/attachment"),), ())
    except ValueError as error:
        assert "approved GET scope" in str(error)
    else:
        raise AssertionError("unapproved URL was accepted")

    try:
        reconcile_media((reference("a-1"), reference("a-1")), ())
    except ValueError as error:
        assert "duplicate" in str(error)
    else:
        raise AssertionError("duplicate identity was accepted")
