"""Non-activating review and successor-price proposal contracts."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from hashlib import sha256


class TransformationKind(StrEnum):
    PERCENT = "percentage"
    FIXED = "fixed_amount"


@dataclass(frozen=True)
class RecommendationProvenance:
    source_price_book_version: str
    recommendation_identity: str
    affected_service_codes: tuple[str, ...]
    transformation_kind: TransformationKind
    transformation_value: Decimal
    effective_date: str
    economics_evidence_version: str | None = None
    model_version: str | None = None
    owner_exclusions: tuple[str, ...] = ()

    @property
    def digest(self) -> str:
        payload = {
            "affected_service_codes": self.affected_service_codes,
            "economics_evidence_version": self.economics_evidence_version,
            "effective_date": self.effective_date,
            "model_version": self.model_version,
            "owner_exclusions": self.owner_exclusions,
            "recommendation_identity": self.recommendation_identity,
            "source_price_book_version": self.source_price_book_version,
            "transformation_kind": self.transformation_kind.value,
            "transformation_value": str(self.transformation_value),
        }
        return sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


@dataclass(frozen=True)
class PriceImpact:
    service_code: str
    current_price: Decimal
    proposed_price: Decimal
    absolute_change: Decimal
    percentage_change: Decimal | None
    cost_completeness: str
    limitations: tuple[str, ...]


def preview_successor_prices(
    *,
    provenance: RecommendationProvenance,
    prices: dict[str, Decimal],
    cost_completeness: dict[str, str],
) -> tuple[PriceImpact, ...]:
    """Create a deterministic draft preview; never mutates or activates prices."""
    excluded = set(provenance.owner_exclusions)
    impacts: list[PriceImpact] = []
    for code in provenance.affected_service_codes:
        if code in excluded:
            continue
        current = prices[code]
        if provenance.transformation_kind is TransformationKind.PERCENT:
            proposed = current * (Decimal(1) + provenance.transformation_value / 100)
        else:
            proposed = current + provenance.transformation_value
        proposed = proposed.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if proposed < 0:
            raise ValueError("A successor price cannot be negative.")
        absolute = proposed - current
        percentage = (
            None
            if current == 0
            else (absolute / current * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        )
        completeness = cost_completeness.get(code, "MISSING")
        limitations = (
            ("Cost evidence is incomplete; no profit effect is asserted.",)
            if completeness != "COMPLETE"
            else ()
        )
        impacts.append(
            PriceImpact(
                service_code=code,
                current_price=current,
                proposed_price=proposed,
                absolute_change=absolute,
                percentage_change=percentage,
                cost_completeness=completeness,
                limitations=limitations,
            )
        )
    return tuple(impacts)


def validate_bulk_review_selection(
    *, selected: Iterable[str], expected: Iterable[str]
) -> tuple[str, ...]:
    """Bind bulk review to an exact, duplicate-free service set."""
    values = tuple(selected)
    if len(values) != len(set(values)):
        raise ValueError("Bulk review selection contains duplicate services.")
    if set(values) != set(expected):
        raise ValueError("Bulk review selection is stale or incomplete.")
    return tuple(sorted(values))
