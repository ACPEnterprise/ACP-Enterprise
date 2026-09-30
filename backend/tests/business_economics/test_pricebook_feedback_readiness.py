from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.business_economics.pricebook_feedback_readiness import (
    project_pricebook_feedback,
)


def test_exact_snapshot_lineage_is_visible_but_not_review_ready_without_cost() -> None:
    conversion = SimpleNamespace(
        job_id=uuid4(),
        branch_id=uuid4(),
        estimate_id=uuid4(),
        estimate_revision_id=uuid4(),
    )
    snapshot = SimpleNamespace(
        id=uuid4(),
        service_item_id=uuid4(),
        price_version_id=uuid4(),
        digest="a" * 64,
        currency="USD",
        extended_amount=Decimal("250.00"),
        effective_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    reference = SimpleNamespace(snapshot_digest=snapshot.digest)

    result = project_pricebook_feedback(
        rows=((conversion, reference, snapshot),),
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
    )

    assert result["mapped_job_count"] == 1
    assert result["review_ready_job_count"] == 0
    assert result["jobs"][0]["configured_selling_value"] == "250.00"
    assert result["jobs"][0]["readiness"] == "COST_EVIDENCE_REQUIRED"
    assert result["mutation_authority"] == "none"


def test_missing_snapshot_mapping_remains_missing() -> None:
    conversion = SimpleNamespace(
        job_id=uuid4(),
        branch_id=uuid4(),
        estimate_id=uuid4(),
        estimate_revision_id=uuid4(),
    )
    result = project_pricebook_feedback(
        rows=((conversion, None, None),),
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
    )

    assert result["mapping_missing_job_count"] == 1
    assert result["jobs"][0]["readiness"] == "MAPPING_MISSING"


def test_snapshot_digest_conflict_fails_closed() -> None:
    conversion = SimpleNamespace(
        job_id=uuid4(),
        branch_id=uuid4(),
        estimate_id=uuid4(),
        estimate_revision_id=uuid4(),
    )
    reference = SimpleNamespace(snapshot_digest="b" * 64)
    snapshot = SimpleNamespace(
        id=uuid4(),
        digest="a" * 64,
        currency="USD",
        extended_amount=Decimal("1.00"),
    )
    result = project_pricebook_feedback(
        rows=((conversion, reference, snapshot),),
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
    )

    assert result["conflicting_job_count"] == 1
    assert result["jobs"][0]["readiness"] == "CONFLICTING"
