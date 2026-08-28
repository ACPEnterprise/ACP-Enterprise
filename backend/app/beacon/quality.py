"""Deterministic confidence and freshness semantics for Beacon evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.beacon.catalog import OPERATIONAL_SIGNAL_CATALOG
from app.beacon.evidence_evaluation import (
    EVIDENCE_EVALUATION_REGISTRY,
    EvaluationReadiness,
)


class EvidenceConfidenceState(StrEnum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    UNKNOWN = "unknown"
    CONFLICTING = "conflicting"


class EvidenceFreshnessState(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"


class EvidenceCompletenessState(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class EvidenceReconciliationState(StrEnum):
    RECONCILED = "reconciled"
    LIMITED = "limited"
    UNKNOWN = "unknown"
    CONFLICTING = "conflicting"


class StaleEvidenceBehavior(StrEnum):
    BLOCK_EVALUATION = "block_evaluation"
    DOWNGRADE_CONFIDENCE = "downgrade_confidence"
    LABEL_STALE_SIGNAL = "label_stale_signal"


@dataclass(frozen=True)
class EvidenceFreshnessPolicy:
    policy_id: str
    version: int
    definition_id: str
    maximum_as_of_lag_seconds: int
    stale_behavior: StaleEvidenceBehavior
    policy_source: str


@dataclass(frozen=True)
class EvidenceQualityInput:
    definition_id: str
    source_authority: str
    evidence_identities: tuple[str, ...]
    effective_at: datetime | None
    observed_as_of: datetime | None
    evaluated_at: datetime
    completeness: EvidenceCompletenessState
    reconciliation: EvidenceReconciliationState
    limitations: tuple[str, ...] = ()
    conflict_identities: tuple[str, ...] = ()
    evidence_digest: str = ""


@dataclass(frozen=True)
class EvidenceQualityEnvelope:
    definition_id: str
    definition_version: int
    source_authority: str
    evidence_identities: tuple[str, ...]
    effective_at: datetime | None
    observed_as_of: datetime | None
    evaluated_at: datetime
    completeness: EvidenceCompletenessState
    reconciliation: EvidenceReconciliationState
    freshness: EvidenceFreshnessState
    confidence: EvidenceConfidenceState
    freshness_policy_id: str | None
    freshness_policy_version: int | None
    stale_behavior: StaleEvidenceBehavior | None
    limitations: tuple[str, ...]
    conflict_identities: tuple[str, ...]
    evidence_digest: str
    quality_digest: str
    conclusion_admissible: bool
    explanation: str


@dataclass(frozen=True)
class DefinitionQualitySemantics:
    definition_id: str
    readiness: EvaluationReadiness
    confidence_semantics_available: bool
    freshness_semantics_available: bool
    freshness_policy_id: str | None
    freshness_policy_version: int | None
    policy_source: str | None
    blocker: str | None


class EvidenceQualityService:
    def __init__(self, policies: tuple[EvidenceFreshnessPolicy, ...]) -> None:
        self.policies = policies
        ids = [policy.definition_id for policy in policies]
        if len(ids) != len(set(ids)):
            raise ValueError("A definition may have only one active freshness policy.")
        for policy in policies:
            OPERATIONAL_SIGNAL_CATALOG.definition(policy.definition_id)
            if policy.version < 1 or policy.maximum_as_of_lag_seconds <= 0:
                raise ValueError(
                    "Freshness policies require positive versions and lag."
                )

    def semantics(self) -> tuple[DefinitionQualitySemantics, ...]:
        policies = {policy.definition_id: policy for policy in self.policies}
        return tuple(
            DefinitionQualitySemantics(
                definition_id=registration.definition_id,
                readiness=registration.readiness,
                confidence_semantics_available=True,
                freshness_semantics_available=registration.definition_id in policies,
                freshness_policy_id=(
                    policies[registration.definition_id].policy_id
                    if registration.definition_id in policies
                    else None
                ),
                freshness_policy_version=(
                    policies[registration.definition_id].version
                    if registration.definition_id in policies
                    else None
                ),
                policy_source=(
                    policies[registration.definition_id].policy_source
                    if registration.definition_id in policies
                    else None
                ),
                blocker=(
                    registration.blocker
                    if registration.blocker
                    else None
                    if registration.definition_id in policies
                    else "No approved definition-bound freshness policy exists."
                ),
            )
            for registration in EVIDENCE_EVALUATION_REGISTRY.registrations
        )

    def evaluate(self, value: EvidenceQualityInput) -> EvidenceQualityEnvelope:
        definition = OPERATIONAL_SIGNAL_CATALOG.definition(value.definition_id)
        registration = EVIDENCE_EVALUATION_REGISTRY.registration(value.definition_id)
        policy = next(
            (
                item
                for item in self.policies
                if item.definition_id == value.definition_id
            ),
            None,
        )
        limitations = list(value.limitations)
        if value.conflict_identities or (
            value.reconciliation is EvidenceReconciliationState.CONFLICTING
        ):
            freshness = self._freshness(value, policy)
            confidence = EvidenceConfidenceState.CONFLICTING
            admissible = False
            explanation = (
                "Accepted evidence conflicts and no approved precedence resolves it."
            )
        else:
            freshness = self._freshness(value, policy)
            confidence = self._confidence(value, freshness)
            admissible = (
                registration.readiness is EvaluationReadiness.EVALUABLE
                and value.completeness is EvidenceCompletenessState.COMPLETE
                and value.reconciliation
                in {
                    EvidenceReconciliationState.RECONCILED,
                    EvidenceReconciliationState.LIMITED,
                }
                and freshness is EvidenceFreshnessState.CURRENT
            )
            if registration.readiness is not EvaluationReadiness.EVALUABLE:
                limitations.append(
                    f"Readiness remains {registration.readiness.value}; quality cannot admit evaluation."
                )
            if policy is None:
                limitations.append("No approved freshness policy exists.")
            if freshness is EvidenceFreshnessState.STALE:
                limitations.append("Evidence exceeds its approved freshness policy.")
            explanation = self._explanation(confidence, freshness, admissible)
        canonical_limitations = tuple(sorted(set(limitations)))
        evidence_identities = tuple(sorted(set(value.evidence_identities)))
        conflict_identities = tuple(sorted(set(value.conflict_identities)))
        payload = {
            "definition_id": value.definition_id,
            "definition_version": definition.version,
            "source_authority": value.source_authority,
            "evidence_identities": evidence_identities,
            "effective_at": value.effective_at.isoformat()
            if value.effective_at
            else None,
            "observed_as_of": value.observed_as_of.isoformat()
            if value.observed_as_of
            else None,
            "evaluated_at": value.evaluated_at.isoformat(),
            "completeness": value.completeness.value,
            "reconciliation": value.reconciliation.value,
            "freshness": freshness.value,
            "confidence": confidence.value,
            "policy_id": policy.policy_id if policy else None,
            "policy_version": policy.version if policy else None,
            "limitations": canonical_limitations,
            "conflict_identities": conflict_identities,
            "evidence_digest": value.evidence_digest,
            "conclusion_admissible": admissible,
        }
        quality_digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return EvidenceQualityEnvelope(
            definition_id=value.definition_id,
            definition_version=definition.version,
            source_authority=value.source_authority,
            evidence_identities=evidence_identities,
            effective_at=value.effective_at,
            observed_as_of=value.observed_as_of,
            evaluated_at=value.evaluated_at,
            completeness=value.completeness,
            reconciliation=value.reconciliation,
            freshness=freshness,
            confidence=confidence,
            freshness_policy_id=policy.policy_id if policy else None,
            freshness_policy_version=policy.version if policy else None,
            stale_behavior=policy.stale_behavior if policy else None,
            limitations=canonical_limitations,
            conflict_identities=conflict_identities,
            evidence_digest=value.evidence_digest,
            quality_digest=quality_digest,
            conclusion_admissible=admissible,
            explanation=explanation,
        )

    @staticmethod
    def _freshness(
        value: EvidenceQualityInput,
        policy: EvidenceFreshnessPolicy | None,
    ) -> EvidenceFreshnessState:
        if policy is None or value.observed_as_of is None:
            return EvidenceFreshnessState.UNKNOWN
        if value.observed_as_of.tzinfo is None or value.evaluated_at.tzinfo is None:
            return EvidenceFreshnessState.UNKNOWN
        lag = (value.evaluated_at - value.observed_as_of).total_seconds()
        if lag < 0:
            return EvidenceFreshnessState.UNKNOWN
        if lag > policy.maximum_as_of_lag_seconds:
            return EvidenceFreshnessState.STALE
        return EvidenceFreshnessState.CURRENT

    @staticmethod
    def _confidence(
        value: EvidenceQualityInput,
        freshness: EvidenceFreshnessState,
    ) -> EvidenceConfidenceState:
        if freshness is EvidenceFreshnessState.UNKNOWN:
            return EvidenceConfidenceState.UNKNOWN
        if freshness is EvidenceFreshnessState.STALE:
            return EvidenceConfidenceState.LOW
        if value.completeness is EvidenceCompletenessState.UNKNOWN or (
            value.reconciliation is EvidenceReconciliationState.UNKNOWN
        ):
            return EvidenceConfidenceState.UNKNOWN
        if value.completeness is EvidenceCompletenessState.PARTIAL:
            return EvidenceConfidenceState.LOW
        if value.reconciliation is EvidenceReconciliationState.LIMITED or (
            value.limitations
        ):
            return EvidenceConfidenceState.MODERATE
        return EvidenceConfidenceState.HIGH

    @staticmethod
    def _explanation(
        confidence: EvidenceConfidenceState,
        freshness: EvidenceFreshnessState,
        admissible: bool,
    ) -> str:
        conclusion = "admissible" if admissible else "not admissible"
        return (
            f"Evidence confidence is {confidence.value}; freshness is "
            f"{freshness.value}; the operational conclusion is {conclusion}."
        )


EVIDENCE_QUALITY_SERVICE = EvidenceQualityService(
    policies=(
        EvidenceFreshnessPolicy(
            policy_id="beacon.snapshot-recency.scheduling-overdue.v1",
            version=1,
            definition_id="operational.scheduling.appointment_overdue",
            maximum_as_of_lag_seconds=900,
            stale_behavior=StaleEvidenceBehavior.BLOCK_EVALUATION,
            policy_source="BANK.BEA.001 definition v1 ttl_seconds=900",
        ),
        EvidenceFreshnessPolicy(
            policy_id="beacon.snapshot-recency.paused-jobs.v1",
            version=1,
            definition_id="operational.job.intermediate_state_stalled",
            maximum_as_of_lag_seconds=900,
            stale_behavior=StaleEvidenceBehavior.BLOCK_EVALUATION,
            policy_source="BANK.BEA.001 definition v1 ttl_seconds=900",
        ),
    )
)


__all__ = [
    "EVIDENCE_QUALITY_SERVICE",
    "DefinitionQualitySemantics",
    "EvidenceCompletenessState",
    "EvidenceConfidenceState",
    "EvidenceFreshnessPolicy",
    "EvidenceFreshnessState",
    "EvidenceQualityEnvelope",
    "EvidenceQualityInput",
    "EvidenceQualityService",
    "EvidenceReconciliationState",
    "StaleEvidenceBehavior",
]
