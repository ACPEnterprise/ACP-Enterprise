"""Version-aware preflight for repeatable HCP operational deltas.

This module does not acquire provider data or mutate native records.  It turns a
sealed current-provider observation plus a read-only native/source observation
into the existing current-overlay contract.  Ambiguous chronology and native
changes are deliberately held for review.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.operational_migration.hcp_current_overlay import (
    CurrentOverlayManifest,
    OverlayAssertion,
    OverlayKey,
    OverlayRecord,
)

CONTRACT = "hcp-continuous-delta-preflight/v1"
MUTABLE_DOMAINS = frozenset({"customer", "job", "appointment"})
CREATE_DOMAINS = frozenset(
    {"customer", "service_location", "job", "appointment"}
)


class DeltaDisposition(StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    UNCHANGED_REPLAY = "UNCHANGED_REPLAY"
    HOLD_NATIVE_NEWER = "HOLD_NATIVE_NEWER"
    HOLD_SOURCE_CHRONOLOGY = "HOLD_SOURCE_CHRONOLOGY"
    HOLD_UNSUPPORTED_MUTATION = "HOLD_UNSUPPORTED_MUTATION"


@dataclass(frozen=True)
class ProviderObservation:
    domain: str
    source_id: str
    source_digest: str
    acquired_at: str
    source_updated_at: str | None
    payload: dict[str, Any]
    parent_keys: tuple[OverlayKey, ...] = ()
    native_fingerprint: str | None = None

    @property
    def key(self) -> OverlayKey:
        return OverlayKey(self.domain, self.source_id)


@dataclass(frozen=True)
class NativeObservation:
    source_digest: str
    source_applied_at: str
    native_updated_at: str


@dataclass(frozen=True)
class DeltaDecision:
    key: OverlayKey
    disposition: DeltaDisposition
    reason: str
    before_digest: str | None
    after_digest: str


@dataclass(frozen=True)
class ContinuousDeltaPlan:
    contract: str
    cutoff: str
    decisions: tuple[DeltaDecision, ...]
    manifest: CurrentOverlayManifest | None
    digest: str


def build_continuous_delta(
    *,
    cutoff: str,
    base_source4_digest: str,
    company_id: str,
    branch_id: str,
    acquired_at: str,
    provider: tuple[ProviderObservation, ...],
    native: dict[OverlayKey, NativeObservation],
) -> ContinuousDeltaPlan:
    """Classify a sealed delta without allowing provider truth to erase ACP work."""
    cutoff_time = _time(cutoff, "cutoff")
    acquired_time = _time(acquired_at, "acquired_at")
    if acquired_time <= cutoff_time:
        raise ValueError("delta acquisition must be newer than its cutoff")
    keys = [item.key for item in provider]
    if len(keys) != len(set(keys)):
        raise ValueError("continuous delta provider identities must be unique")

    records: list[OverlayRecord] = []
    decisions: list[DeltaDecision] = []
    for item in sorted(provider, key=lambda value: value.key):
        state = native.get(item.key)
        disposition, reason = _classify(item, state, cutoff_time, acquired_time)
        decisions.append(
            DeltaDecision(
                item.key,
                disposition,
                reason,
                state.source_digest if state else None,
                item.source_digest,
            )
        )
        if disposition is DeltaDisposition.UNCHANGED_REPLAY:
            continue
        assertion = {
            DeltaDisposition.CREATE: OverlayAssertion.CREATE,
            DeltaDisposition.UPDATE: OverlayAssertion.UPDATE,
        }.get(disposition, OverlayAssertion.HOLD)
        records.append(
            OverlayRecord(
                domain=item.domain,
                source_id=item.source_id,
                assertion=assertion,
                source_digest=item.source_digest,
                acquired_at=item.acquired_at,
                payload=item.payload
                if assertion in {OverlayAssertion.CREATE, OverlayAssertion.UPDATE}
                else {},
                prior_source_digest=(
                    state.source_digest
                    if assertion is OverlayAssertion.UPDATE and state
                    else None
                ),
                parent_keys=item.parent_keys,
                native_fingerprint=item.native_fingerprint,
                reason=reason if assertion is OverlayAssertion.HOLD else "",
            )
        )

    delta_payload = {
        "contract": CONTRACT,
        "cutoff": cutoff,
        "acquired_at": acquired_at,
        "decisions": [_decision_value(item) for item in decisions],
    }
    delta_digest = _digest(delta_payload)
    manifest = (
        CurrentOverlayManifest.build(
            base_source4_digest=base_source4_digest,
            delta_digest=delta_digest,
            company_id=company_id,
            branch_id=branch_id,
            acquired_at=acquired_at,
            records=tuple(records),
        )
        if records
        else None
    )
    plan_payload = delta_payload | {
        "manifest_digest": manifest.digest if manifest else None
    }
    return ContinuousDeltaPlan(
        CONTRACT,
        cutoff,
        tuple(decisions),
        manifest,
        _digest(plan_payload),
    )


def _classify(
    item: ProviderObservation,
    state: NativeObservation | None,
    cutoff: datetime,
    acquired_at: datetime,
) -> tuple[DeltaDisposition, str]:
    _digest_value(item.source_digest, "provider source")
    item_acquired = _time(item.acquired_at, "record acquired_at")
    if item_acquired > acquired_at or item_acquired <= cutoff:
        return (
            DeltaDisposition.HOLD_SOURCE_CHRONOLOGY,
            "provider observation is outside the sealed delta window",
        )
    source_updated = (
        _time(item.source_updated_at, "source updated_at")
        if item.source_updated_at
        else None
    )
    if state is None:
        if item.domain not in CREATE_DOMAINS:
            return (
                DeltaDisposition.HOLD_UNSUPPORTED_MUTATION,
                "domain is evidence-only in the operational delta executor",
            )
        return DeltaDisposition.CREATE, "new exact provider identity"
    _digest_value(state.source_digest, "native source")
    if state.source_digest == item.source_digest:
        return DeltaDisposition.UNCHANGED_REPLAY, "identical sealed source digest"
    if item.domain not in MUTABLE_DOMAINS:
        return (
            DeltaDisposition.HOLD_UNSUPPORTED_MUTATION,
            "domain update is not supported by canonical native services",
        )
    if source_updated is None:
        return (
            DeltaDisposition.HOLD_SOURCE_CHRONOLOGY,
            "changed provider record lacks an authoritative updated_at",
        )
    applied_at = _time(state.source_applied_at, "source applied_at")
    native_updated = _time(state.native_updated_at, "native updated_at")
    if native_updated > applied_at:
        return (
            DeltaDisposition.HOLD_NATIVE_NEWER,
            "native record changed after the last applied provider assertion",
        )
    if source_updated <= applied_at:
        return (
            DeltaDisposition.HOLD_SOURCE_CHRONOLOGY,
            "changed digest is not a newer provider version",
        )
    return DeltaDisposition.UPDATE, "newer provider version with unchanged native target"


def _decision_value(value: DeltaDecision) -> dict[str, object]:
    return {
        "domain": value.key.domain,
        "source_id": value.key.source_id,
        "disposition": value.disposition.value,
        "reason": value.reason,
        "before_digest": value.before_digest,
        "after_digest": value.after_digest,
    }


def _time(value: str, label: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed


def _digest_value(value: str, label: str) -> None:
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
