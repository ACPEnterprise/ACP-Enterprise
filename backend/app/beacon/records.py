from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TypeAlias
from uuid import UUID

from app.beacon.contracts import (
    BeaconCategory,
    BeaconConfidence,
    BeaconEvidence,
    BeaconExpirationPolicy,
    BeaconPriorityBand,
    BeaconRankingFactorAvailability,
    BeaconSeverity,
    BeaconSignalSource,
)

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
class BeaconSignal:
    id: UUID
    rule_code: str
    source: BeaconSignalSource
    title: str
    category: BeaconCategory
    severity: BeaconSeverity
    priority: BeaconPriority
    confidence: BeaconConfidence
    supporting_facts: tuple[BeaconSupportingFact, ...]
    recommended_action: str
    created_at: datetime
    expires_at: datetime
    expiration_policy: BeaconExpirationPolicy
