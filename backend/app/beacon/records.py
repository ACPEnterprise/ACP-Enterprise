from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, TypeAlias
from uuid import UUID

from app.beacon.contracts import (
    BeaconCategory,
    BeaconConfidence,
    BeaconEvidence,
    BeaconExpirationPolicy,
    BeaconLifecycleAction,
    BeaconLifecycleStatus,
    BeaconPriorityBand,
    BeaconRankingFactorAvailability,
    BeaconSeverity,
    BeaconSignalSource,
    BeaconWorkflowAction,
)

if TYPE_CHECKING:
    from app.beacon.quality import EvidenceQualityEnvelope

BeaconFactValue: TypeAlias = str | int | bool


@dataclass(frozen=True)
class BeaconSupportingFact:
    name: str
    value: BeaconFactValue
    source: str
    measured_at: datetime
    evidence: tuple[BeaconEvidence, ...] = ()
    unit: str | None = None


@dataclass(frozen=True)
class BeaconRankingFactor:
    name: str
    value: BeaconFactValue | None
    unit: str | None
    availability: BeaconRankingFactorAvailability
    contribution: int
    explanation: str


@dataclass(frozen=True)
class BeaconPriority:
    band: BeaconPriorityBand
    score: int
    rank: int
    ranking_factors: tuple[BeaconRankingFactor, ...]
    explanation: str
    evaluated_at: datetime
    tie_break_semantics: str


@dataclass(frozen=True)
class BeaconLifecycleEvent:
    id: UUID
    company_id: UUID
    condition_key: UUID
    signal_id: UUID
    rule_code: str
    signal_source: BeaconSignalSource
    evidence_digest: str
    action: BeaconLifecycleAction
    actor_membership_id: UUID
    action_at: datetime
    snooze_until: datetime | None
    created_at: datetime


@dataclass(frozen=True)
class BeaconLifecycleProjection:
    status: BeaconLifecycleStatus
    latest_event: BeaconLifecycleEvent | None
    temporarily_suppressed: bool


@dataclass(frozen=True)
class BeaconCondition:
    company_id: UUID
    scope_identity: str
    definition_id: str
    definition_version: int
    rule_code: str
    source: BeaconSignalSource
    category: BeaconCategory
    severity: BeaconSeverity
    confidence: BeaconConfidence
    supporting_facts: tuple[BeaconSupportingFact, ...]
    evidence_digest: str
    evaluated_at: datetime
    expires_at: datetime
    expiration_policy: BeaconExpirationPolicy


@dataclass(frozen=True)
class BeaconSignal:
    id: UUID
    condition_key: UUID
    evidence_digest: str
    definition_id: str
    definition_version: int
    rule_code: str
    source: BeaconSignalSource
    title: str
    category: BeaconCategory
    severity: BeaconSeverity
    priority: BeaconPriority
    lifecycle: BeaconLifecycleProjection
    confidence: BeaconConfidence
    evidence_quality: EvidenceQualityEnvelope | None
    supporting_facts: tuple[BeaconSupportingFact, ...]
    recommended_action: str
    created_at: datetime
    expires_at: datetime
    expiration_policy: BeaconExpirationPolicy


@dataclass(frozen=True)
class BeaconAttentionQueue:
    active: tuple[BeaconSignal, ...]
    snoozed: tuple[BeaconSignal, ...]


@dataclass(frozen=True)
class BeaconWorkflowState:
    company_id: UUID
    branch_id: UUID | None
    condition_key: UUID
    signal_id: UUID
    definition_id: str
    definition_version: int
    evidence_digest: str
    workflow_version: int
    acknowledged: bool
    acknowledged_by_user_id: UUID | None
    acknowledged_at: datetime | None
    owner_user_id: UUID | None
    owned_since: datetime | None
    last_action: BeaconWorkflowAction | None
    last_actor_user_id: UUID | None
    updated_at: datetime | None


@dataclass(frozen=True)
class BeaconWorkflowEvent:
    id: UUID
    state: BeaconWorkflowState
    action: BeaconWorkflowAction
    actor_user_id: UUID
    previous_owner_user_id: UUID | None
    request_id: UUID
    occurred_at: datetime
