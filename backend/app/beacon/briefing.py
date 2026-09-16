from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.beacon.contracts import BeaconPriorityBand, BeaconSeverity
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
    limitations: tuple[str, ...]
    dashboard_ready: bool
    mobile_inbox_ready: bool
    external_delivery_ready: bool
    brief_digest: str


def attention_window(signal: BeaconSignal) -> OwnerAttentionWindow:
    if (
        signal.severity is BeaconSeverity.CRITICAL
        or signal.priority.band
        in {BeaconPriorityBand.CRITICAL, BeaconPriorityBand.IMMEDIATE}
    ):
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
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
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
        historical_comparison_available=False,
        new_since_yesterday=None,
        resolved_since_yesterday=None,
        limitations=(
            "Beacon does not persist periodic evaluation snapshots, so new and resolved counts since yesterday are unavailable.",
            "Snoozed conditions remain unresolved and are included in the unresolved total.",
            "The brief contains attention evidence only and cannot mutate a source domain.",
        ),
        dashboard_ready=True,
        mobile_inbox_ready=False,
        external_delivery_ready=False,
        brief_digest=digest,
    )
