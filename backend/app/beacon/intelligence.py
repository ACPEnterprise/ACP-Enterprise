"""Permission-bounded, provider-neutral Beacon intelligence contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.beacon.escalation import EscalationProjection
from app.beacon.operational_prioritization import PrioritizedOperationalSignal
from app.beacon.records import BeaconWorkflowState
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import BeaconPermission

INTELLIGENCE_CONTRACT_VERSION = "BEACON.INTELLIGENCE.v1"


@dataclass(frozen=True)
class BeaconActionContract:
    action: str
    available: bool
    required_permission: str
    execution_authority: str


@dataclass(frozen=True)
class BeaconSourceReference:
    domain: str
    entity_type: str
    entity_id: UUID
    evidence_event_id: UUID | None
    observed_at: datetime | None


@dataclass(frozen=True)
class BeaconIntelligencePacket:
    contract_version: str
    company_id: UUID
    branch_id: UUID | None
    signal_id: UUID
    condition_key: UUID
    definition_id: str
    definition_version: int
    evidence_digest: str
    title: str
    state: str
    explanation: str
    recommended_human_action: str
    priority_position: int
    priority_band: str
    priority_reason: str
    severity: str
    confidence: str
    completeness: str
    freshness: str
    reconciliation: str
    limitations: tuple[str, ...]
    owner_user_id: UUID | None
    acknowledged: bool
    escalation_state: str
    escalation_reason: str
    source_references: tuple[BeaconSourceReference, ...]
    actions: tuple[BeaconActionContract, ...]
    generated_at: datetime
    packet_digest: str


def build_intelligence_packet(
    item: PrioritizedOperationalSignal,
    *,
    context: AuthorizationContext,
    workflow: BeaconWorkflowState | None,
    escalation: EscalationProjection,
) -> BeaconIntelligencePacket:
    """Build a deterministic packet with no authority beyond its ACP principal."""
    signal = item.signal
    quality = signal.evidence_quality
    if quality is None or not quality.conclusion_admissible:
        raise ValueError("Only an admitted Beacon signal can produce a packet.")
    source_map = {
        (
            signal.source.value,
            evidence.entity_type,
            evidence.entity_id,
            evidence.event_id,
        ): BeaconSourceReference(
            domain=signal.source.value,
            entity_type=evidence.entity_type,
            entity_id=evidence.entity_id,
            evidence_event_id=evidence.event_id,
            observed_at=evidence.occurred_at,
        )
        for fact in signal.supporting_facts
        for evidence in fact.evidence
    }
    sources = tuple(
        sorted(
            source_map.values(),
            key=lambda value: (
                value.domain,
                value.entity_type,
                str(value.entity_id),
                str(value.evidence_event_id or ""),
            ),
        )
    )
    actions = (
        _action(context, "acknowledge", BeaconPermission.REVIEW),
        _action(context, "take_ownership", BeaconPermission.OWN),
        _action(context, "assign_or_transfer", BeaconPermission.ASSIGN),
        BeaconActionContract(
            action="navigate_to_authoritative_source",
            available=True,
            required_permission="SOURCE_DOMAIN_PERMISSION_REQUIRED",
            execution_authority="source_domain",
        ),
    )
    payload = {
        "contract_version": INTELLIGENCE_CONTRACT_VERSION,
        "company_id": str(context.company.id),
        "branch_id": str(context.active_branch.id) if context.active_branch else None,
        "signal_id": str(signal.id),
        "condition_key": str(signal.condition_key),
        "definition_id": quality.definition_id,
        "definition_version": quality.definition_version,
        "evidence_digest": signal.evidence_digest,
        "priority_position": item.ranking.position,
        "priority_band": item.ranking.priority_band.value,
        "quality_digest": quality.quality_digest,
        "owner_user_id": str(workflow.owner_user_id)
        if workflow and workflow.owner_user_id
        else None,
        "acknowledged": bool(workflow and workflow.acknowledged),
        "escalation_state": escalation.state.value,
        "sources": [
            {
                "domain": source.domain,
                "entity_type": source.entity_type,
                "entity_id": str(source.entity_id),
                "event_id": str(source.evidence_event_id)
                if source.evidence_event_id
                else None,
                "observed_at": source.observed_at.isoformat()
                if source.observed_at
                else None,
            }
            for source in sources
        ],
        "actions": [
            {
                "action": action.action,
                "available": action.available,
                "required_permission": action.required_permission,
                "execution_authority": action.execution_authority,
            }
            for action in actions
        ],
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return BeaconIntelligencePacket(
        contract_version=INTELLIGENCE_CONTRACT_VERSION,
        company_id=context.company.id,
        branch_id=context.active_branch.id if context.active_branch else None,
        signal_id=signal.id,
        condition_key=signal.condition_key,
        definition_id=quality.definition_id,
        definition_version=quality.definition_version,
        evidence_digest=signal.evidence_digest,
        title=signal.title,
        state=signal.lifecycle.status.value,
        explanation=quality.explanation,
        recommended_human_action=signal.recommended_action,
        priority_position=item.ranking.position,
        priority_band=item.ranking.priority_band.value,
        priority_reason=item.ranking.ranking_reason,
        severity=signal.severity.value,
        confidence=quality.confidence.value,
        completeness=quality.completeness.value,
        freshness=quality.freshness.value,
        reconciliation=quality.reconciliation.value,
        limitations=quality.limitations,
        owner_user_id=workflow.owner_user_id if workflow else None,
        acknowledged=bool(workflow and workflow.acknowledged),
        escalation_state=escalation.state.value,
        escalation_reason=escalation.reason,
        source_references=sources,
        actions=actions,
        generated_at=signal.created_at,
        packet_digest=digest,
    )


def _action(
    context: AuthorizationContext, action: str, permission: str
) -> BeaconActionContract:
    return BeaconActionContract(
        action=action,
        available=context.has_permission(permission),
        required_permission=permission,
        execution_authority="beacon_workflow",
    )
