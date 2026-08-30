"""Approved intelligence-source adapters into the generic LIA envelope."""

from __future__ import annotations

from typing import Protocol

from app.beacon.intelligence import BeaconIntelligencePacket

from .foundation import EvidenceEnvelope, EvidenceState


def beacon_evidence(packet: BeaconIntelligencePacket) -> EvidenceEnvelope:
    """Preserve Beacon quality and scope without reinterpreting its conclusion."""
    state = {
        "conflicting": EvidenceState.CONFLICTING,
        "unknown": EvidenceState.UNRESOLVED,
        "limited": EvidenceState.PARTIAL,
    }.get(packet.reconciliation, EvidenceState.KNOWN)
    if packet.freshness == "stale":
        state = EvidenceState.STALE
    elif packet.completeness != "complete" and state is EvidenceState.KNOWN:
        state = EvidenceState.PARTIAL
    return EvidenceEnvelope(
        evidence_id=f"beacon:{packet.signal_id}:{packet.packet_digest}",
        source_id="BEACON_INTELLIGENCE",
        source_domain="Beacon",
        source_entity_type="beacon_signal",
        source_entity_id=packet.signal_id,
        version_or_digest=packet.packet_digest,
        effective_at=packet.generated_at,
        observed_at=packet.generated_at,
        state=state,
        freshness=packet.freshness,
        confidence=packet.confidence,
        completeness=packet.completeness,
        reconciliation=packet.reconciliation,
        limitations=packet.limitations,
        safe_summary=packet.explanation,
        drillback_path=f"/command-center?signal={packet.signal_id}",
    )


class EconomicsIntelligenceAdapter(Protocol):
    """Stable seam; Economics owns calculations and admitted result authority."""

    async def get_admitted_evidence(
        self, *, principal_digest: str
    ) -> tuple[EvidenceEnvelope, ...]: ...
