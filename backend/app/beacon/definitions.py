from __future__ import annotations

from dataclasses import dataclass

from app.beacon.contracts import (
    BeaconCategory,
    BeaconConditionKind,
    BeaconConfidence,
    BeaconConfidenceLevel,
    BeaconEscalationMatch,
    BeaconEscalationThreshold,
    BeaconExpirationPolicy,
    BeaconSeverity,
    BeaconSignalDefinition,
    BeaconSignalSource,
)

CONFIDENCE = BeaconConfidence(
    level=BeaconConfidenceLevel.HIGH,
    basis="Authoritative Company-scoped records measured by a deterministic rule.",
)


@dataclass(frozen=True)
class BeaconSignalDefinitionRegistry:
    definitions: tuple[BeaconSignalDefinition, ...]

    def __post_init__(self) -> None:
        identities = tuple(
            (definition.definition_id, definition.version)
            for definition in self.definitions
        )
        if len(identities) != len(set(identities)):
            raise ValueError("Beacon definition identity and version must be unique.")
        rule_codes = tuple(definition.rule_code for definition in self.definitions)
        if len(rule_codes) != len(set(rule_codes)):
            raise ValueError(
                "Exactly one active version is allowed for each rule code."
            )
        if any(definition.version < 1 for definition in self.definitions):
            raise ValueError("Beacon definition versions begin at one.")
        if any(definition.ttl_seconds <= 0 for definition in self.definitions):
            raise ValueError("Beacon definition expiration must be positive.")


BEACON_SIGNAL_DEFINITIONS = BeaconSignalDefinitionRegistry(
    definitions=(
        BeaconSignalDefinition(
            definition_id="scheduling.overdue_committed_appointments",
            version=1,
            rule_code="scheduling.overdue_committed_appointments",
            condition_kind=BeaconConditionKind.OVERDUE_APPOINTMENTS,
            source=BeaconSignalSource.SCHEDULING,
            category=BeaconCategory.SCHEDULING,
            title="Committed appointments are past their arrival window",
            recommended_action=(
                "Review the listed committed appointments and record an authoritative "
                "completion, no-show, cancellation, or reschedule outcome."
            ),
            confidence=CONFIDENCE,
            base_severity=BeaconSeverity.ATTENTION,
            escalation_thresholds=(
                BeaconEscalationThreshold(
                    severity=BeaconSeverity.CRITICAL,
                    minimum_age=24,
                ),
                BeaconEscalationThreshold(
                    severity=BeaconSeverity.IMPORTANT,
                    minimum_age=4,
                ),
            ),
            expiration_policy=BeaconExpirationPolicy.REPLACE_ON_NEXT_EVALUATION,
            ttl_seconds=900,
            evidence_entity_type="appointment",
        ),
        BeaconSignalDefinition(
            definition_id="operations.paused_jobs",
            version=1,
            rule_code="operations.paused_jobs",
            condition_kind=BeaconConditionKind.PAUSED_JOBS,
            source=BeaconSignalSource.JOBS,
            category=BeaconCategory.OPERATIONS,
            title="Jobs remain paused",
            recommended_action=(
                "Review each paused job's recorded reason and either resume, cancel, "
                "or leave it paused with current operational evidence."
            ),
            confidence=CONFIDENCE,
            base_severity=BeaconSeverity.ATTENTION,
            escalation_thresholds=(
                BeaconEscalationThreshold(
                    severity=BeaconSeverity.IMPORTANT,
                    minimum_age=24,
                    minimum_count=5,
                    match=BeaconEscalationMatch.ANY,
                ),
            ),
            expiration_policy=BeaconExpirationPolicy.REPLACE_ON_NEXT_EVALUATION,
            ttl_seconds=900,
            evidence_entity_type="job",
        ),
        BeaconSignalDefinition(
            definition_id="revenue.past_due_invoices",
            version=1,
            rule_code="revenue.past_due_invoices",
            condition_kind=BeaconConditionKind.PAST_DUE_INVOICES,
            source=BeaconSignalSource.INVOICES,
            category=BeaconCategory.REVENUE,
            title="Issued invoices are past due",
            recommended_action=(
                "Review the authoritative invoice and payment records before beginning "
                "the Company's approved collection workflow."
            ),
            confidence=CONFIDENCE,
            base_severity=BeaconSeverity.ATTENTION,
            escalation_thresholds=(
                BeaconEscalationThreshold(
                    severity=BeaconSeverity.CRITICAL,
                    minimum_age=30,
                ),
                BeaconEscalationThreshold(
                    severity=BeaconSeverity.IMPORTANT,
                    minimum_age=7,
                ),
            ),
            expiration_policy=BeaconExpirationPolicy.REPLACE_ON_NEXT_EVALUATION,
            ttl_seconds=900,
            evidence_entity_type="invoice",
        ),
    )
)
