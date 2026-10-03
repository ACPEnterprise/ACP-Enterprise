import hashlib
from pathlib import Path

import pytest

from app.operational_migration.hcp_supplemental_evidence import (
    attachment_retry_queue,
    build_attachment_authority,
    build_membership_authority,
    build_review_authority,
    build_supplemental_delta,
    import_attachment_content,
    import_attachment_manifest,
)

ACQUIRED = "2026-10-03T15:00:00Z"
PROVENANCE = {"source": "hcp_support_export", "version": "export-1"}


def _attachment(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "provider_attachment_id": "att_1",
        "parent_type": "job",
        "parent_source_id": "job_1",
        "filename": "photo.jpg",
        "media_type": "image/jpeg",
        "created_at": ACQUIRED,
        "state": "AVAILABLE",
        "provenance": PROVENANCE,
    }
    result.update(overrides)
    return result


def test_unknown_attachment_inventory_is_not_reported_as_zero() -> None:
    packet = build_attachment_authority(
        company_id="company-1",
        acquired_at=ACQUIRED,
        inventory_complete=False,
        records=[],
        known_parents={},
    )

    assert packet["counts"] == {
        "source": 0,
        "admitted": 0,
        "held": 0,
        "unknown": 1,
        "unexplained": 0,
    }
    assert packet["records"][0]["state"] == "UNKNOWN_PROVIDER_INVENTORY"
    assert packet["guardrails"]["absence_is_zero"] is False


def test_attachment_manifest_covers_parent_types_and_holds_orphans() -> None:
    records = [
        _attachment(
            provider_attachment_id=f"att_{domain}",
            parent_type=domain,
            parent_source_id=f"{domain}_1",
        )
        for domain in ("customer", "job", "estimate", "open_work")
    ]
    packet = build_attachment_authority(
        company_id="company-1",
        acquired_at=ACQUIRED,
        inventory_complete=True,
        records=records,
        known_parents={
            "customer": {"customer_1"},
            "job": {"job_1"},
            "estimate": {"estimate_1"},
        },
    )

    assert packet["counts"]["source"] == 3
    assert packet["counts"]["held"] == 1
    orphan = next(
        row for row in packet["records"] if row["parent_type"] == "open_work"
    )
    assert orphan["parent_known"] is False
    assert orphan["disposition"] == "HELD"


@pytest.mark.parametrize(
    ("state", "reason", "expected"),
    [
        ("FAILED", "provider download failed", "HELD"),
        ("MISSING_SOURCE", None, "HELD"),
        ("RETRY_REQUIRED", "temporary provider error", "HELD"),
        ("OWNER_EXPORT_REQUIRED", None, "HELD"),
    ],
)
def test_attachment_failure_states_are_explicit(
    state: str, reason: str | None, expected: str
) -> None:
    packet = build_attachment_authority(
        company_id="company-1",
        acquired_at=ACQUIRED,
        inventory_complete=True,
        records=[_attachment(state=state, error_reason=reason)],
        known_parents={"job": {"job_1"}},
    )
    assert packet["records"][0]["disposition"] == expected


def test_attachment_retry_queue_includes_only_retryable_failures() -> None:
    packet = build_attachment_authority(
        company_id="company-1",
        acquired_at=ACQUIRED,
        inventory_complete=True,
        records=[
            _attachment(
                provider_attachment_id="att-retry",
                state="RETRY_REQUIRED",
                error_reason="temporary provider error",
            ),
            _attachment(
                provider_attachment_id="att-export",
                state="OWNER_EXPORT_REQUIRED",
            ),
        ],
        known_parents={"job": {"job_1"}},
    )

    queue = attachment_retry_queue(packet)

    assert [row["provider_attachment_id"] for row in queue] == ["att-retry"]


def test_attachment_content_custody_is_verified_and_replay_safe(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"real exported evidence")
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    custody = tmp_path / "custody"

    first = import_attachment_content(
        source_path=source,
        custody_root=custody,
        company_id="company-1",
        provider_attachment_id="att-1",
        expected_digest=expected,
        expected_size=source.stat().st_size,
    )
    replay = import_attachment_content(
        source_path=source,
        custody_root=custody,
        company_id="company-1",
        provider_attachment_id="att-1",
        expected_digest=expected,
        expected_size=source.stat().st_size,
    )

    target = custody / "company-1" / expected
    assert first.replayed is False
    assert replay.replayed is True
    assert target.read_bytes() == source.read_bytes()
    assert target.stat().st_mode & 0o777 == 0o600
    assert target.parent.stat().st_mode & 0o777 == 0o700


def test_attachment_content_rejects_digest_drift(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"unexpected")
    with pytest.raises(ValueError, match="does not match"):
        import_attachment_content(
            source_path=source,
            custody_root=tmp_path / "custody",
            company_id="company-1",
            provider_attachment_id="att-1",
            expected_digest="0" * 64,
            expected_size=source.stat().st_size,
        )

    with pytest.raises(ValueError, match="safe path component"):
        import_attachment_content(
            source_path=source,
            custody_root=tmp_path / "custody",
            company_id="../other-company",
            provider_attachment_id="att-1",
            expected_digest=hashlib.sha256(source.read_bytes()).hexdigest(),
            expected_size=source.stat().st_size,
        )


def test_manifest_import_is_bounded_and_returns_record_level_retry(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    good = source_root / "good.jpg"
    good.write_bytes(b"good")
    records = [
        _attachment(
            provider_attachment_id="att-good",
            filename="good.jpg",
            content_digest=hashlib.sha256(good.read_bytes()).hexdigest(),
            byte_size=good.stat().st_size,
        ),
        _attachment(
            provider_attachment_id="att-missing",
            filename="missing.jpg",
            content_digest="0" * 64,
            byte_size=1,
        ),
    ]

    imported, counts = import_attachment_manifest(
        source_root=source_root,
        custody_root=tmp_path / "custody",
        company_id="company-1",
        records=records,
    )

    assert counts == {"IMPORTED": 1, "RETRY_REQUIRED": 1}
    assert {row["state"] for row in imported} == {"IMPORTED", "RETRY_REQUIRED"}
    failed = next(row for row in imported if row["state"] == "RETRY_REQUIRED")
    assert failed["error_reason"]


def test_attachment_manifest_rejects_paths_duplicates_and_unverified_imports() -> None:
    common = {
        "company_id": "company-1",
        "acquired_at": ACQUIRED,
        "inventory_complete": True,
        "known_parents": {"job": {"job_1"}},
    }
    with pytest.raises(ValueError, match="must not contain a path"):
        build_attachment_authority(
            **common, records=[_attachment(filename="../secret")]
        )
    with pytest.raises(ValueError, match="duplicate"):
        build_attachment_authority(
            **common, records=[_attachment(), _attachment()]
        )
    with pytest.raises(ValueError, match="content_digest"):
        build_attachment_authority(
            **common, records=[_attachment(state="IMPORTED")]
        )


def test_membership_packet_never_fabricates_current_entitlement() -> None:
    packet = build_membership_authority(
        company_id="company-1",
        acquired_at=ACQUIRED,
        records=[
            {
                "provider_plan_id": "plan-history",
                "customer_source_id": "customer-1",
                "status": "active_at_source_time",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "source_version": "v1",
                "current_assertion": False,
                "recurring_obligations": None,
                "benefits": [{"description": "source-described discount"}],
                "provenance": PROVENANCE,
            },
            {
                "provider_plan_id": "plan-current-unbound",
                "customer_source_id": "customer-2",
                "status": "active",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
                "source_version": "v2",
                "current_assertion": True,
                "provenance": PROVENANCE,
            },
        ],
    )

    assert packet["counts"]["source"] == 1
    assert packet["counts"]["held"] == 1
    historical = next(row for row in packet["records"] if row["history_only"])
    assert historical["disposition"] == "SOURCE"


def test_membership_exact_native_binding_is_admitted() -> None:
    packet = build_membership_authority(
        company_id="company-1",
        acquired_at=ACQUIRED,
        records=[
            {
                "provider_plan_id": "plan-1",
                "customer_source_id": "customer-1",
                "native_service_agreement_id": "agreement-1",
                "status": "active",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
                "source_version": "v3",
                "current_assertion": True,
                "provenance": PROVENANCE,
            }
        ],
    )
    assert packet["counts"]["admitted"] == 1


def test_reviews_are_historical_and_not_marketing_authority() -> None:
    packet = build_review_authority(
        company_id="company-1",
        acquired_at=ACQUIRED,
        records=[
            {
                "provider_review_id": "review-1",
                "rating": 4.5,
                "review_text": "source review",
                "reviewed_at": "2025-05-01T12:00:00Z",
                "customer_source_id": "customer-1",
                "job_source_id": "job-1",
                "provenance": PROVENANCE,
            }
        ],
    )
    row = packet["records"][0]
    assert row["authority"] == "OPERATIONAL_HISTORY_ONLY"
    assert row["public_marketing_authority"] is False


def test_review_rejects_invalid_rating_and_duplicate_provider_id() -> None:
    base = {
        "provider_review_id": "review-1",
        "rating": 6,
        "reviewed_at": "2025-05-01T12:00:00Z",
        "provenance": PROVENANCE,
    }
    with pytest.raises(ValueError, match="between zero and five"):
        build_review_authority(
            company_id="company-1", acquired_at=ACQUIRED, records=[base]
        )
    base["rating"] = 5
    with pytest.raises(ValueError, match="duplicate"):
        build_review_authority(
            company_id="company-1", acquired_at=ACQUIRED, records=[base, base]
        )


def test_supplemental_delta_is_deterministic_and_never_drops_silently() -> None:
    before = build_review_authority(
        company_id="company-1",
        acquired_at=ACQUIRED,
        records=[
            {
                "provider_review_id": "review-1",
                "rating": 4,
                "reviewed_at": "2025-05-01T12:00:00Z",
                "provenance": PROVENANCE,
            }
        ],
    )
    after = build_review_authority(
        company_id="company-1",
        acquired_at="2026-10-04T15:00:00Z",
        records=[
            {
                "provider_review_id": "review-2",
                "rating": 5,
                "reviewed_at": "2025-05-02T12:00:00Z",
                "provenance": PROVENANCE,
            }
        ],
    )

    first = build_supplemental_delta(
        domain="reviews", prior_packet=before, current_packet=after
    )
    second = build_supplemental_delta(
        domain="reviews", prior_packet=before, current_packet=after
    )

    assert first == second
    assert first["changes"] == [
        {"source_id": "review-1", "state": "SOURCE_UNAVAILABLE"},
        {"source_id": "review-2", "state": "CREATE"},
    ]
