import json
from decimal import Decimal
from pathlib import Path

import pytest
from app.price_book.activation_readiness import (
    RecommendationProvenance,
    TransformationKind,
    preview_successor_prices,
    validate_bulk_review_selection,
)

ROOT = Path(__file__).parents[3]
PACKET = ROOT / "docs/architecture/price-book/all-county-activation-readiness-1.json"


def test_all_services_are_independently_audited_without_cost_blocking_commerce() -> (
    None
):
    packet = json.loads(PACKET.read_text())
    assert packet["activation_status"] == "NOT_ACTIVATED"
    assert packet["counts"] == {
        "services": 218,
        "commercially_ready_before_cost_completion": 218,
        "blocked_solely_by_tax_after_owner_price_approval": 179,
        "blocked_by_source_conflict": 39,
        "ready_after_minimum_approvals": 218,
        "ready_for_activation_now": 0,
        "owner_review_required": 218,
        "accountant_review_required": 218,
    }
    assert len(packet["tax_decision_groups"]) == 16
    assert len(packet["service_audits"]) == 218
    assert all(
        not item["cost_effects"]["customer_pricing_blocked"]
        for item in packet["service_audits"]
    )
    assert all(
        not item["cost_effects"]["snapshot_blocked"]
        for item in packet["service_audits"]
    )


def test_successor_preview_is_deterministic_non_mutating_and_cost_truthful() -> None:
    provenance = RecommendationProvenance(
        source_price_book_version="candidate-1",
        recommendation_identity="owner-review-1",
        affected_service_codes=("A", "B"),
        transformation_kind=TransformationKind.PERCENT,
        transformation_value=Decimal(10),
        effective_date="2026-10-01",
        owner_exclusions=("B",),
    )
    prices = {"A": Decimal("100.00"), "B": Decimal("200.00")}
    impacts = preview_successor_prices(
        provenance=provenance,
        prices=prices,
        cost_completeness={"A": "INCOMPLETE"},
    )
    assert prices == {"A": Decimal("100.00"), "B": Decimal("200.00")}
    assert len(impacts) == 1
    assert impacts[0].proposed_price == Decimal("110.00")
    assert impacts[0].limitations == (
        "Cost evidence is incomplete; no profit effect is asserted.",
    )
    assert len(provenance.digest) == 64


def test_bulk_review_fails_closed_on_duplicates_stale_sets_and_negative_prices() -> (
    None
):
    with pytest.raises(ValueError, match="duplicate"):
        validate_bulk_review_selection(selected=("A", "A"), expected=("A",))
    with pytest.raises(ValueError, match="stale"):
        validate_bulk_review_selection(selected=("A",), expected=("A", "B"))
    provenance = RecommendationProvenance(
        source_price_book_version="candidate-1",
        recommendation_identity="owner-review-2",
        affected_service_codes=("A",),
        transformation_kind=TransformationKind.FIXED,
        transformation_value=Decimal(-101),
        effective_date="2026-10-01",
    )
    with pytest.raises(ValueError, match="negative"):
        preview_successor_prices(
            provenance=provenance,
            prices={"A": Decimal(100)},
            cost_completeness={},
        )
