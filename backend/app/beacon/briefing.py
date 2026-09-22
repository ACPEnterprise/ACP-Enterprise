from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.beacon.contracts import BeaconPriorityBand, BeaconSeverity
from app.beacon.history import BeaconEvaluationRecord, EvaluationDisposition
from app.beacon.records import BeaconSignal


class OwnerAttentionWindow(StrEnum):
    NOW = "now"
    TODAY = "today"
    THIS_WEEK = "this_week"
    WATCH = "watch"


@dataclass(frozen=True)
class OwnerAttentionGroup:
    window: OwnerAttentionWindow
    signal_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class BeaconMorningBrief:
    company_id: UUID
    branch_id: UUID | None
    evaluated_at: datetime
    groups: tuple[OwnerAttentionGroup, ...]
    unresolved_count: int
    acknowledged_count: int
    snoozed_count: int
    urgent_today_count: int
    historical_comparison_available: bool
    new_since_yesterday: int | None
    resolved_since_yesterday: int | None
    changed_since_yesterday: int | None
    expired_since_yesterday: int | None
    limitations: tuple[str, ...]
    dashboard_ready: bool
    mobile_inbox_ready: bool
    external_delivery_ready: bool
    brief_digest: str


def attention_window(signal: BeaconSignal) -> OwnerAttentionWindow:
    if signal.severity is BeaconSeverity.CRITICAL or signal.priority.band in {
        BeaconPriorityBand.CRITICAL,
        BeaconPriorityBand.IMMEDIATE,
    }:
        return OwnerAttentionWindow.NOW
    if (
        signal.severity is BeaconSeverity.IMPORTANT
        or signal.priority.band is BeaconPriorityBand.IMPORTANT
    ):
        return OwnerAttentionWindow.TODAY
    if signal.severity is BeaconSeverity.ATTENTION:
        return OwnerAttentionWindow.THIS_WEEK
    return OwnerAttentionWindow.WATCH


def build_morning_brief(
    *,
    company_id: UUID,
    branch_id: UUID | None,
    active: tuple[BeaconSignal, ...],
    snoozed: tuple[BeaconSignal, ...],
    evaluated_at: datetime,
    historical_deltas: tuple[BeaconEvaluationRecord, ...] | None = None,
) -> BeaconMorningBrief:
    grouped = {
        window: tuple(
            signal.id for signal in active if attention_window(signal) is window
        )
        for window in OwnerAttentionWindow
    }
    groups = tuple(
        OwnerAttentionGroup(window=window, signal_ids=grouped[window])
        for window in OwnerAttentionWindow
    )
    urgent = len(grouped[OwnerAttentionWindow.NOW]) + len(
        grouped[OwnerAttentionWindow.TODAY]
    )
    payload = {
        "company_id": str(company_id),
        "branch_id": str(branch_id) if branch_id else None,
        "evaluated_at": evaluated_at.isoformat(),
        "active": [
            {
                "signal_id": str(signal.id),
                "evidence_digest": signal.evidence_digest,
                "window": attention_window(signal).value,
            }
            for signal in active
        ],
        "snoozed": [
            {"signal_id": str(signal.id), "evidence_digest": signal.evidence_digest}
            for signal in snoozed
        ],
        "historical_comparison_available": historical_deltas is not None,
        "historical_deltas": sorted(
            (
                str(item.id),
                str(item.run_id),
                str(item.condition_key),
                item.evidence_digest,
                item.disposition.value,
                item.evaluated_at.isoformat(),
                item.evidence_as_of.isoformat(),
            )
            for item in historical_deltas or ()
        ),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    historical_available = historical_deltas is not None
    disposition_counts = {
        disposition: sum(
            item.disposition is disposition for item in historical_deltas or ()
        )
        for disposition in EvaluationDisposition
    }
    limitations = [
        "Snoozed conditions remain unresolved and are included in the unresolved total.",
        "The brief contains attention evidence only and cannot mutate a source domain.",
    ]
    if not historical_available:
        limitations.insert(
            0,
            "No persisted evaluation history is available for the requested comparison window.",
        )
    return BeaconMorningBrief(
        company_id=company_id,
        branch_id=branch_id,
        evaluated_at=evaluated_at,
        groups=groups,
        unresolved_count=len(active) + len(snoozed),
        acknowledged_count=sum(
            signal.lifecycle.status.value == "acknowledged" for signal in active
        ),
        snoozed_count=len(snoozed),
        urgent_today_count=urgent,
        historical_comparison_available=historical_available,
        new_since_yesterday=(
            disposition_counts[EvaluationDisposition.NEW]
            if historical_available
            else None
        ),
        resolved_since_yesterday=(
            disposition_counts[EvaluationDisposition.RESOLVED]
            if historical_available
            else None
        ),
        changed_since_yesterday=(
            disposition_counts[EvaluationDisposition.CHANGED]
            if historical_available
            else None
        ),
        expired_since_yesterday=(
            disposition_counts[EvaluationDisposition.EXPIRED]
            if historical_available
            else None
        ),
        limitations=tuple(limitations),
        dashboard_ready=True,
        mobile_inbox_ready=False,
        external_delivery_ready=False,
        brief_digest=digest,
    )
