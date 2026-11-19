"""Guarded HCP Estimate promotion and final-delta classification.

The planner never writes Estimates.  It proves whether sealed provider evidence
can be promoted through canonical ``estimate_proposals`` services, preserved as
history, replayed, or quarantined.  Execution must consume this immutable plan
and re-check every parent/native predicate transactionally.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

CONTRACT: Final = "hcp-estimate-promotion-plan/v1"
SUPPORTED_STATUSES: Final = frozenset(
    {
        "draft",
        "open",
        "pending",
        "sent",
        "viewed",
        "proposed",
        "approved",
        "accepted",
        "rejected",
        "declined",
        "expired",
        "cancelled",
    }
)
OPEN_STATUSES: Final = frozenset(
    {"draft", "open", "pending", "sent", "viewed", "proposed"}
)


class EstimatePromotionDisposition(StrEnum):
    CREATE = "CREATE"
    REUSE = "REUSE"
    UPDATE = "UPDATE"
    HISTORY_ONLY = "HISTORY_ONLY"
    CONFLICT = "CONFLICT"
    OWNER_DECISION_REQUIRED = "OWNER_DECISION_REQUIRED"
    UNSUPPORTED = "UNSUPPORTED"
    REPLAY = "REPLAY"


@dataclass(frozen=True)
class EstimateLineEvidence:
    source_id: str
    description: str
    quantity: str
    unit_price: str
    total_amount: str


@dataclass(frozen=True)
class EstimateOptionEvidence:
    source_id: str
    label: str
    status: str | None
    total_amount: str | None
    lines: tuple[EstimateLineEvidence, ...]


@dataclass(frozen=True)
class EstimateSourceEvidence:
    source_id: str
    source_version: str | None
    source_digest: str
    source_updated_at: str | None
    acquired_at: str
    as_of: str
    customer_source_id: str
    location_source_id: str | None
    job_source_id: str | None
    status: str
    currency: str
    subtotal_amount: str
    tax_amount: str
    total_amount: str
    notes: str | None
    salesperson_source_id: str | None
    options: tuple[EstimateOptionEvidence, ...]


@dataclass(frozen=True)
class ExactParentBindings:
    customer_ids: tuple[str, ...]
    location_ids: tuple[str, ...] = ()
    job_ids: tuple[str, ...] = ()
    line_snapshot_ids: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class NativeEstimateEvidence:
    estimate_id: str
    source_digest: str
    source_version: str | None
    source_applied_at: str
    native_updated_at: str


@dataclass(frozen=True)
class EstimatePromotionDecision:
    source_id: str
    disposition: EstimatePromotionDisposition
    reason: str
    native_estimate_id: str | None
    open_at_source: bool
    snapshot_digest: str


@dataclass(frozen=True)
class EstimatePromotionPlan:
    contract: str
    cutoff: str
    acquired_at: str
    decisions: tuple[EstimatePromotionDecision, ...]
    counts: dict[str, int]
    digest: str


def build_estimate_promotion_plan(
    *,
    cutoff: str,
    acquired_at: str,
    source: tuple[EstimateSourceEvidence, ...],
    bindings: dict[str, ExactParentBindings],
    native: dict[str, NativeEstimateEvidence],
) -> EstimatePromotionPlan:
    cutoff_time = _time(cutoff, "cutoff")
    acquired_time = _time(acquired_at, "acquired_at")
    if acquired_time <= cutoff_time:
        raise ValueError("Estimate acquisition must be newer than cutoff")
    ids = [row.source_id for row in source]
    if len(ids) != len(set(ids)):
        raise ValueError("Estimate provider identities must be unique")
    extra_bindings = set(bindings) - set(ids)
    extra_native = set(native) - set(ids)
    if extra_bindings or extra_native:
        raise ValueError("Estimate observations contain unknown provider identities")

    decisions = tuple(
        _classify(
            row,
            bindings.get(row.source_id),
            native.get(row.source_id),
            cutoff_time,
            acquired_time,
        )
        for row in sorted(source, key=lambda value: value.source_id)
    )
    counts = Counter(row.disposition.value for row in decisions)
    normalized_counts = {
        disposition.value: counts[disposition.value]
        for disposition in EstimatePromotionDisposition
    }
    payload = {
        "contract": CONTRACT,
        "cutoff": cutoff,
        "acquired_at": acquired_at,
        "decisions": [asdict(row) for row in decisions],
        "counts": normalized_counts,
    }
    return EstimatePromotionPlan(
        CONTRACT,
        cutoff,
        acquired_at,
        decisions,
        normalized_counts,
        _digest(payload),
    )


def _classify(
    source: EstimateSourceEvidence,
    bindings: ExactParentBindings | None,
    native: NativeEstimateEvidence | None,
    cutoff: datetime,
    acquired_at: datetime,
) -> EstimatePromotionDecision:
    snapshot_digest = _validate_source(source, cutoff, acquired_at)
    status = source.status.strip().lower()
    open_at_source = status in OPEN_STATUSES
    if status not in SUPPORTED_STATUSES:
        return _decision(
            source,
            EstimatePromotionDisposition.UNSUPPORTED,
            "provider Estimate status has no canonical lifecycle mapping",
            native,
            open_at_source,
            snapshot_digest,
        )
    if bindings is None or len(bindings.customer_ids) != 1:
        return _decision(
            source,
            EstimatePromotionDisposition.CONFLICT,
            "exact Customer binding is missing or ambiguous",
            native,
            open_at_source,
            snapshot_digest,
        )
    if source.location_source_id and len(bindings.location_ids) != 1:
        return _decision(
            source,
            EstimatePromotionDisposition.CONFLICT,
            "exact Location binding is missing or ambiguous",
            native,
            open_at_source,
            snapshot_digest,
        )
    if source.job_source_id is None:
        return _decision(
            source,
            EstimatePromotionDisposition.HISTORY_ONLY,
            "source Estimate has no authoritative Job relationship",
            native,
            open_at_source,
            snapshot_digest,
        )
    if len(bindings.job_ids) > 1:
        return _decision(
            source,
            EstimatePromotionDisposition.OWNER_DECISION_REQUIRED,
            "source Estimate resolves to multiple authoritative Jobs",
            native,
            open_at_source,
            snapshot_digest,
        )
    if len(bindings.job_ids) != 1:
        return _decision(
            source,
            EstimatePromotionDisposition.CONFLICT,
            "exact Job binding is missing",
            native,
            open_at_source,
            snapshot_digest,
        )
    line_ids = {line.source_id for option in source.options for line in option.lines}
    snapshot_pairs = bindings.line_snapshot_ids
    snapshot_source_ids = [source_id for source_id, _ in snapshot_pairs]
    if len(snapshot_source_ids) != len(set(snapshot_source_ids)):
        return _decision(
            source,
            EstimatePromotionDisposition.CONFLICT,
            "commercial snapshot bindings contain duplicate source lines",
            native,
            open_at_source,
            snapshot_digest,
        )
    if set(snapshot_source_ids) != line_ids or any(
        not native_id for _, native_id in snapshot_pairs
    ):
        disposition = (
            EstimatePromotionDisposition.OWNER_DECISION_REQUIRED
            if open_at_source
            else EstimatePromotionDisposition.HISTORY_ONLY
        )
        return _decision(
            source,
            disposition,
            "Estimate lines lack exact immutable ACP commercial snapshot bindings",
            native,
            open_at_source,
            snapshot_digest,
        )
    if native is None:
        return _decision(
            source,
            EstimatePromotionDisposition.CREATE,
            "all required parents resolve exactly and native source identity is absent",
            None,
            open_at_source,
            snapshot_digest,
        )
    _hex_digest(native.source_digest, "native source")
    if native.source_digest == source.source_digest:
        return _decision(
            source,
            EstimatePromotionDisposition.REPLAY,
            "identical source digest is already bound",
            native,
            open_at_source,
            snapshot_digest,
        )
    applied_at = _time(native.source_applied_at, "source_applied_at")
    native_updated_at = _time(native.native_updated_at, "native_updated_at")
    if native_updated_at > applied_at:
        return _decision(
            source,
            EstimatePromotionDisposition.CONFLICT,
            "ACP-native Estimate changed after prior provider application",
            native,
            open_at_source,
            snapshot_digest,
        )
    if source.source_version is None or source.source_updated_at is None:
        return _decision(
            source,
            EstimatePromotionDisposition.CONFLICT,
            "changed Estimate lacks authoritative provider successor chronology",
            native,
            open_at_source,
            snapshot_digest,
        )
    if source.source_version == native.source_version:
        return _decision(
            source,
            EstimatePromotionDisposition.CONFLICT,
            "same provider version produced a different sealed digest",
            native,
            open_at_source,
            snapshot_digest,
        )
    if _time(source.source_updated_at, "source_updated_at") <= applied_at:
        return _decision(
            source,
            EstimatePromotionDisposition.CONFLICT,
            "changed provider Estimate is not newer than applied evidence",
            native,
            open_at_source,
            snapshot_digest,
        )
    return _decision(
        source,
        EstimatePromotionDisposition.UPDATE,
        "newer provider version and unchanged native target",
        native,
        open_at_source,
        snapshot_digest,
    )


def _validate_source(
    value: EstimateSourceEvidence, cutoff: datetime, acquired_at: datetime
) -> str:
    if not value.source_id.strip() or not value.customer_source_id.strip():
        raise ValueError("Estimate and Customer provider identities are required")
    _hex_digest(value.source_digest, "Estimate source")
    observed = _time(value.acquired_at, "record acquired_at")
    as_of = _time(value.as_of, "record as_of")
    if observed != acquired_at or as_of > acquired_at or observed <= cutoff:
        raise ValueError("Estimate evidence is outside the sealed delta window")
    option_ids = [option.source_id for option in value.options]
    if not option_ids or len(option_ids) != len(set(option_ids)):
        raise ValueError("Estimate options must have unique provider identities")
    line_ids = [line.source_id for option in value.options for line in option.lines]
    if not line_ids or len(line_ids) != len(set(line_ids)):
        raise ValueError("Estimate lines must have unique provider identities")
    snapshot = asdict(value)
    return _digest(snapshot)


def _decision(
    source: EstimateSourceEvidence,
    disposition: EstimatePromotionDisposition,
    reason: str,
    native: NativeEstimateEvidence | None,
    open_at_source: bool,
    snapshot_digest: str,
) -> EstimatePromotionDecision:
    return EstimatePromotionDecision(
        source.source_id,
        disposition,
        reason,
        native.estimate_id if native else None,
        open_at_source,
        snapshot_digest,
    )


def _time(value: str, label: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed


def _hex_digest(value: str, label: str) -> None:
    if len(value) != 64:
        raise ValueError(f"{label} digest is invalid")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"{label} digest is invalid") from error


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
