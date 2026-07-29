from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


class BeaconCategory(StrEnum):
    OPERATIONS = "operations"
    REVENUE = "revenue"
    CUSTOMER = "customer"
    SCHEDULING = "scheduling"
    WORKFORCE = "workforce"


class BeaconSeverity(StrEnum):
    INFORMATION = "information"
    ATTENTION = "attention"
    IMPORTANT = "important"
    CRITICAL = "critical"


class BeaconSignalSource(StrEnum):
    SCHEDULING = "scheduling"
    JOBS = "jobs"
    INVOICES = "invoices"


class BeaconPriorityBand(StrEnum):
    CRITICAL = "critical"
    IMMEDIATE = "immediate"
    IMPORTANT = "important"
    MONITOR = "monitor"


class BeaconRankingFactorAvailability(StrEnum):
    MEASURED = "measured"
    NOT_APPLICABLE = "not_applicable"


class BeaconConfidenceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class BeaconExpirationPolicy(StrEnum):
    REPLACE_ON_NEXT_EVALUATION = "replace_on_next_evaluation"


class BeaconConditionKind(StrEnum):
    OVERDUE_APPOINTMENTS = "overdue_appointments"
    PAUSED_JOBS = "paused_jobs"
    PAST_DUE_INVOICES = "past_due_invoices"


class BeaconEscalationMatch(StrEnum):
    ANY = "any"
    ALL = "all"


class BeaconLifecycleAction(StrEnum):
    ACKNOWLEDGE = "acknowledge"
    REVIEW = "review"
    SNOOZE = "snooze"


class BeaconLifecycleStatus(StrEnum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    REVIEWED = "reviewed"
    SNOOZED = "snoozed"


@dataclass(frozen=True)
class BeaconConfidence:
    level: BeaconConfidenceLevel
    basis: str


@dataclass(frozen=True)
class BeaconEscalationThreshold:
    severity: BeaconSeverity
    minimum_age: int | None = None
    minimum_count: int | None = None
    match: BeaconEscalationMatch = BeaconEscalationMatch.ALL


@dataclass(frozen=True)
class BeaconSignalDefinition:
    definition_id: str
    version: int
    rule_code: str
    condition_kind: BeaconConditionKind
    source: BeaconSignalSource
    category: BeaconCategory
    title: str
    recommended_action: str
    confidence: BeaconConfidence
    base_severity: BeaconSeverity
    escalation_thresholds: tuple[BeaconEscalationThreshold, ...]
    expiration_policy: BeaconExpirationPolicy
    ttl_seconds: int
    evidence_entity_type: str


@dataclass(frozen=True)
class BeaconEvidence:
    entity_type: str
    entity_id: UUID
    event_id: UUID | None
    event_type: str | None
    occurred_at: datetime | None


@dataclass(frozen=True)
class OverdueAppointmentFacts:
    count: int
    earliest_window_start: datetime | None
    evidence: tuple[BeaconEvidence, ...]


@dataclass(frozen=True)
class PausedJobFacts:
    count: int
    earliest_paused_at: datetime | None
    evidence: tuple[BeaconEvidence, ...]


@dataclass(frozen=True)
class PastDueInvoiceFacts:
    count: int
    total_amount: Decimal
    earliest_due_on: date | None
    evidence: tuple[BeaconEvidence, ...]


@dataclass(frozen=True)
class BeaconSnapshot:
    company_id: UUID
    measured_at: datetime
    overdue_appointments: OverdueAppointmentFacts
    paused_jobs: PausedJobFacts
    past_due_invoices: PastDueInvoiceFacts


class BeaconFactRepository(Protocol):
    async def load_snapshot(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        measured_at: datetime,
    ) -> BeaconSnapshot: ...
