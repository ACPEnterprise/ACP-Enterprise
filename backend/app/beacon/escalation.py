"""Versioned, fail-closed escalation semantics for operational Beacon signals."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.beacon.catalog import (
    BEACON_SIGNAL_CATALOG,
    OPERATIONAL_SIGNAL_CATALOG,
    OperationalSignalCatalog,
    OperationalSignalFamily,
)
from app.beacon.evidence_evaluation import (
    BEACON_EVIDENCE_EVALUATION_REGISTRY,
    EvaluationReadiness,
)
from app.beacon.records import BeaconSignal, BeaconWorkflowState


class EscalationState(StrEnum):
    NORMAL = "normal"
    ESCALATED = "escalated"


class EscalationEligibility(StrEnum):
    ESCALATION_READY = "escalation_ready"
    POLICY_MISSING = "policy_missing"
    NOT_EVALUABLE = "not_evaluable"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class EscalationRule:
    rule_id: str
    version: int
    definition_id: str
    definition_version: int
    triggering_condition: str
    required_evidence: tuple[str, ...]
    elapsed_time_fact: str | None
    elapsed_time_threshold_seconds: int | None
    resulting_state: EscalationState

    @property
    def rule_digest(self) -> str:
        payload = {
            "rule_id": self.rule_id,
            "version": self.version,
            "definition_id": self.definition_id,
            "definition_version": self.definition_version,
            "triggering_condition": self.triggering_condition,
            "required_evidence": self.required_evidence,
            "elapsed_time_fact": self.elapsed_time_fact,
            "elapsed_time_threshold_seconds": self.elapsed_time_threshold_seconds,
            "resulting_state": self.resulting_state.value,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class EscalationRegistration:
    definition_id: str
    definition_version: int
    family: OperationalSignalFamily
    evaluation_readiness: EvaluationReadiness
    eligibility: EscalationEligibility
    rule: EscalationRule | None
    blocker: str | None


@dataclass(frozen=True)
class EscalationProjection:
    signal_id: UUID
    condition_key: UUID
    company_id: UUID
    branch_id: UUID | None
    state: EscalationState
    eligibility: EscalationEligibility
    escalation_rule_id: str | None
    escalation_rule_version: int | None
    escalation_rule_digest: str | None
    escalated_at: datetime | None
    reason: str
    acknowledged: bool
    owner_user_id: UUID | None


@dataclass(frozen=True)
class EscalationHistoryEvent:
    """Immutable transition contract reserved for an approved rule transition."""

    signal_id: UUID
    definition_id: str
    definition_version: int
    previous_state: EscalationState
    resulting_state: EscalationState
    rule_id: str
    rule_version: int
    rule_digest: str
    evidence_digest: str
    company_id: UUID
    branch_id: UUID | None
    occurred_at: datetime
    workflow_version: int
    reason: str


class EscalationRegistry:
    def __init__(
        self,
        registrations: tuple[EscalationRegistration, ...],
        *,
        catalog: OperationalSignalCatalog = OPERATIONAL_SIGNAL_CATALOG,
    ) -> None:
        self.registrations = registrations
        self.catalog = catalog
        catalog_ids = {item.definition_id for item in catalog.definitions}
        registered_ids = {item.definition_id for item in registrations}
        if registered_ids != catalog_ids or len(registered_ids) != len(registrations):
            raise ValueError(
                "Escalation registry must cover each catalog definition once."
            )
        for registration in registrations:
            definition = catalog.definition(registration.definition_id)
            if registration.definition_version != definition.version:
                raise ValueError(
                    "Escalation registration version must match the catalog."
                )
            if registration.family is not definition.family:
                raise ValueError("Escalation family must match the catalog.")
            if registration.eligibility is EscalationEligibility.ESCALATION_READY:
                if registration.rule is None or registration.blocker is not None:
                    raise ValueError(
                        "Ready escalation requires one rule and no blocker."
                    )
            elif registration.rule is not None or not registration.blocker:
                raise ValueError(
                    "Blocked escalation requires no rule and an exact blocker."
                )

    def registration(self, definition_id: str) -> EscalationRegistration:
        try:
            return next(
                item
                for item in self.registrations
                if item.definition_id == definition_id
            )
        except StopIteration as error:
            raise KeyError(definition_id) from error


def _registration(definition_id: str) -> EscalationRegistration:
    definition = BEACON_SIGNAL_CATALOG.definition(definition_id)
    evaluation = BEACON_EVIDENCE_EVALUATION_REGISTRY.registration(definition_id)
    if evaluation.readiness is EvaluationReadiness.EVALUABLE:
        eligibility = EscalationEligibility.POLICY_MISSING
        blocker = (
            "No owner-approved versioned escalation interval or explicit escalation "
            "condition exists; freshness TTL is not an escalation policy."
        )
    else:
        eligibility = EscalationEligibility.NOT_EVALUABLE
        blocker = (
            f"Signal evaluation is {evaluation.readiness.value}: {evaluation.blocker}"
        )
    return EscalationRegistration(
        definition_id=definition_id,
        definition_version=definition.version,
        family=definition.family,
        evaluation_readiness=evaluation.readiness,
        eligibility=eligibility,
        rule=None,
        blocker=blocker,
    )


_ALL_ESCALATION_REGISTRATIONS = tuple(
    _registration(item.definition_id) for item in BEACON_SIGNAL_CATALOG.definitions
)
ESCALATION_REGISTRY = EscalationRegistry(_ALL_ESCALATION_REGISTRATIONS[:21])
BEACON_ESCALATION_REGISTRY = EscalationRegistry(
    _ALL_ESCALATION_REGISTRATIONS,
    catalog=BEACON_SIGNAL_CATALOG,
)


class EscalationService:
    def project(
        self,
        signal: BeaconSignal,
        *,
        company_id: UUID,
        branch_id: UUID | None,
        workflow: BeaconWorkflowState | None,
    ) -> EscalationProjection:
        quality = signal.evidence_quality
        if quality is None or not quality.conclusion_admissible:
            raise ValueError("Only an admitted operational signal may be projected.")
        registration = BEACON_ESCALATION_REGISTRY.registration(quality.definition_id)
        return EscalationProjection(
            signal_id=signal.id,
            condition_key=signal.condition_key,
            company_id=company_id,
            branch_id=branch_id,
            state=EscalationState.NORMAL,
            eligibility=registration.eligibility,
            escalation_rule_id=None,
            escalation_rule_version=None,
            escalation_rule_digest=None,
            escalated_at=None,
            reason=registration.blocker or "No escalation condition is active.",
            acknowledged=workflow.acknowledged if workflow else False,
            owner_user_id=workflow.owner_user_id if workflow else None,
        )


escalation_service = EscalationService()
