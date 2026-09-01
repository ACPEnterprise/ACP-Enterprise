"""Approved intelligence-source adapters into the generic LIA envelope."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol, cast

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


def economics_evidence(
    packet: Mapping[str, Any], *, observed_at: datetime
) -> EvidenceEnvelope:
    """Adapt the authoritative owner-intelligence context without recalculation."""
    if packet.get("contract_version") != "economics.owner-intelligence.v1":
        raise ValueError("Unsupported Economics intelligence contract.")
    context = packet.get("context_packet")
    if not isinstance(context, Mapping):
        raise TypeError("Economics context packet is required.")
    digest = context.get("evidence_digest")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("Economics evidence digest is invalid.")
    classification = str(context.get("classification", "UNAVAILABLE"))
    state = {
        "KNOWN": EvidenceState.KNOWN,
        "INCOMPLETE": EvidenceState.PARTIAL,
        "STALE": EvidenceState.STALE,
        "CONFLICTING": EvidenceState.CONFLICTING,
        "UNAVAILABLE": EvidenceState.UNAVAILABLE,
    }.get(classification, EvidenceState.UNRESOLVED)
    limitations = context.get("limitations", ())
    if not isinstance(limitations, (list, tuple)) or not all(
        isinstance(item, str) for item in limitations
    ):
        raise ValueError("Economics limitations are invalid.")
    answer = packet.get("answer")
    answer_kind = answer.get("kind") if isinstance(answer, Mapping) else None
    return EvidenceEnvelope(
        evidence_id=f"economics:{digest}",
        source_id="ECONOMICS_INTELLIGENCE",
        source_domain="Business Economics",
        source_entity_type="owner_intelligence_result",
        source_entity_id=None,
        version_or_digest=digest,
        effective_at=None,
        observed_at=observed_at,
        state=state,
        freshness=str(context.get("freshness", "UNAVAILABLE")),
        confidence=classification,
        completeness=str(context.get("completeness", "unavailable")),
        reconciliation=str(context.get("result_authority", "unavailable")),
        limitations=tuple(limitations),
        safe_summary=f"Authorized Economics evidence: {answer_kind or 'unavailable'}.",
        drillback_path="/business-economics",
    )


def cash_operational_evidence(
    packet: Mapping[str, Any], *, observed_at: datetime
) -> EvidenceEnvelope:
    """Explain truth-plane readiness without recalculating or exposing source rows."""
    if packet.get("version") != "economics.cash-operational-composition.v1":
        raise ValueError("Unsupported cash and operational Economics contract.")
    digest = packet.get("projection_digest")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("Cash and operational Economics digest is invalid.")
    work = packet.get("work_period")
    operational = packet.get("operational_current_state")
    accounting = packet.get("cash_accounting_period")
    if not all(isinstance(value, Mapping) for value in (work, operational, accounting)):
        raise TypeError("All three economic truth planes are required.")
    work = cast(Mapping[str, object], work)
    operational = cast(Mapping[str, object], operational)
    accounting = cast(Mapping[str, object], accounting)
    states = (str(work["state"]), str(operational["state"]), str(accounting["state"]))
    if "CONFLICTING" in states:
        state = EvidenceState.CONFLICTING
    elif any(
        value in {"EXTERNAL_GATE", "PARTIAL", "AVAILABLE_BASIS_ONLY"}
        for value in states
    ):
        state = EvidenceState.PARTIAL
    else:
        state = EvidenceState.KNOWN
    return EvidenceEnvelope(
        evidence_id=f"cash-operational:{digest}",
        source_id="ECONOMICS_CASH_OPERATIONAL",
        source_domain="Business Economics",
        source_entity_type="cash_operational_projection",
        source_entity_id=None,
        version_or_digest=digest,
        effective_at=None,
        observed_at=observed_at,
        state=state,
        freshness="CURRENT_OR_EXPLICITLY_INCOMPLETE",
        confidence="DETERMINISTIC",
        completeness="complete" if state is EvidenceState.KNOWN else "partial",
        reconciliation="three_truth_planes_preserved",
        limitations=(
            "LIA cannot infer cash from an Invoice, Payment assertion, settlement, or deposit.",
            "LIA cannot choose Accounting recognition policy or mutate AR/AP.",
        ),
        safe_summary=(
            "Earned-work Economics, operational AR/AP, and cash-basis Accounting are "
            "separate admitted truth planes. Open the owner Economics view for values."
        ),
        drillback_path="/business-economics",
    )


class EconomicsIntelligenceAdapter(Protocol):
    """Stable seam; Economics owns calculations and admitted result authority."""

    async def get_admitted_evidence(
        self, *, principal_digest: str
    ) -> tuple[EvidenceEnvelope, ...]: ...
