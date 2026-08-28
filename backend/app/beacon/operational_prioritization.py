"""Deterministic attention ordering for admitted operational Beacon signals."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.beacon.catalog import OPERATIONAL_SIGNAL_CATALOG
from app.beacon.contracts import BeaconPriorityBand, BeaconSeverity
from app.beacon.records import BeaconSignal

RANKING_VERSION = "BANK.BEA.004.v1"

_SEVERITY_ORDER = {
    BeaconSeverity.CRITICAL: 4,
    BeaconSeverity.IMPORTANT: 3,
    BeaconSeverity.ATTENTION: 2,
    BeaconSeverity.INFORMATION: 1,
}
_BAND_ORDER = {
    BeaconPriorityBand.CRITICAL: 4,
    BeaconPriorityBand.IMMEDIATE: 3,
    BeaconPriorityBand.IMPORTANT: 2,
    BeaconPriorityBand.MONITOR: 1,
}


@dataclass(frozen=True)
class OperationalUrgencyPolicy:
    policy_id: str
    version: int
    fact_name: str
    unit: str


URGENCY_POLICIES = {
    "operational.scheduling.appointment_overdue": OperationalUrgencyPolicy(
        policy_id="beacon.operational.overdue_duration",
        version=1,
        fact_name="oldest_overdue_hours",
        unit="hours",
    ),
    "operational.job.intermediate_state_stalled": OperationalUrgencyPolicy(
        policy_id="beacon.operational.stalled_duration",
        version=1,
        fact_name="oldest_pause_hours",
        unit="hours",
    ),
}


@dataclass(frozen=True)
class OperationalRanking:
    position: int
    ranking_version: str
    ranking_digest: str
    severity: BeaconSeverity
    priority_band: BeaconPriorityBand
    urgency_policy_id: str | None
    urgency_policy_version: int | None
    urgency_value: str | None
    urgency_unit: str | None
    confidence_state: str
    freshness_state: str
    tie_break_identity: UUID
    ranking_reason: str


@dataclass(frozen=True)
class PrioritizedOperationalSignal:
    signal: BeaconSignal
    ranking: OperationalRanking


@dataclass(frozen=True)
class OperationalAttentionQueue:
    company_id: UUID
    branch_id: UUID | None
    evaluated_at: datetime
    ranking_version: str
    ranking_digest: str
    items: tuple[PrioritizedOperationalSignal, ...]


class OperationalSignalPrioritizer:
    """Orders only admitted operational signals using explicit dimensions."""

    def prioritize(
        self,
        signals: tuple[BeaconSignal, ...],
        *,
        company_id: UUID,
        branch_id: UUID | None,
        evaluated_at: datetime,
    ) -> OperationalAttentionQueue:
        admitted = tuple(
            signal
            for signal in signals
            if signal.evidence_quality is not None
            and signal.evidence_quality.conclusion_admissible
            and not signal.lifecycle.temporarily_suppressed
            and signal.expires_at > evaluated_at
        )
        ordered = tuple(sorted(admitted, key=self._sort_key))
        digest = self._digest(ordered, company_id, branch_id)
        return OperationalAttentionQueue(
            company_id=company_id,
            branch_id=branch_id,
            evaluated_at=evaluated_at,
            ranking_version=RANKING_VERSION,
            ranking_digest=digest,
            items=tuple(
                PrioritizedOperationalSignal(
                    signal=signal,
                    ranking=self._ranking(signal, index, digest),
                )
                for index, signal in enumerate(ordered, start=1)
            ),
        )

    def _sort_key(self, signal: BeaconSignal) -> tuple[int, int, Decimal, str]:
        definition = OPERATIONAL_SIGNAL_CATALOG.definition(
            signal.evidence_quality.definition_id  # type: ignore[union-attr]
        )
        urgency = self._urgency(signal)
        return (
            -_SEVERITY_ORDER[signal.severity],
            -_BAND_ORDER[definition.base_priority],
            -urgency,
            str(signal.id),
        )

    @staticmethod
    def _urgency(signal: BeaconSignal) -> Decimal:
        quality = signal.evidence_quality
        policy = URGENCY_POLICIES.get(quality.definition_id) if quality else None
        if policy is None:
            return Decimal(0)
        fact = next(
            (item for item in signal.supporting_facts if item.name == policy.fact_name),
            None,
        )
        if fact is None or isinstance(fact.value, bool):
            return Decimal(0)
        return Decimal(str(fact.value))

    def _ranking(
        self, signal: BeaconSignal, position: int, digest: str
    ) -> OperationalRanking:
        quality = signal.evidence_quality
        assert quality is not None
        definition = OPERATIONAL_SIGNAL_CATALOG.definition(quality.definition_id)
        policy = URGENCY_POLICIES.get(quality.definition_id)
        urgency = self._urgency(signal) if policy else None
        urgency_reason = (
            f"accepted {policy.fact_name}={urgency} {policy.unit}"
            if policy
            else "no approved urgency policy; time was not ranked"
        )
        return OperationalRanking(
            position=position,
            ranking_version=RANKING_VERSION,
            ranking_digest=digest,
            severity=signal.severity,
            priority_band=definition.base_priority,
            urgency_policy_id=policy.policy_id if policy else None,
            urgency_policy_version=policy.version if policy else None,
            urgency_value=str(urgency) if urgency is not None else None,
            urgency_unit=policy.unit if policy else None,
            confidence_state=quality.confidence.value,
            freshness_state=quality.freshness.value,
            tie_break_identity=signal.id,
            ranking_reason=(
                f"Position {position}: severity={signal.severity.value}; "
                f"definition priority={definition.base_priority.value}; "
                f"{urgency_reason}; final ties use stable signal identity."
            ),
        )

    def _digest(
        self,
        ordered: tuple[BeaconSignal, ...],
        company_id: UUID,
        branch_id: UUID | None,
    ) -> str:
        payload = {
            "ranking_version": RANKING_VERSION,
            "company_id": str(company_id),
            "branch_id": str(branch_id) if branch_id else None,
            "signals": [
                {
                    "signal_id": str(item.id),
                    "definition_id": item.evidence_quality.definition_id,
                    "definition_version": item.evidence_quality.definition_version,
                    "severity": item.severity.value,
                    "priority_band": OPERATIONAL_SIGNAL_CATALOG.definition(
                        item.evidence_quality.definition_id
                    ).base_priority.value,
                    "urgency": str(self._urgency(item)),
                    "quality_digest": item.evidence_quality.quality_digest,
                }
                for item in ordered
                if item.evidence_quality is not None
            ],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


operational_signal_prioritizer = OperationalSignalPrioritizer()
