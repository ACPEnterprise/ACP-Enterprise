from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from app.beacon.contracts import (
    BeaconConditionKind,
    BeaconEscalationMatch,
    BeaconEscalationThreshold,
    BeaconLifecycleAction,
    BeaconLifecycleStatus,
    BeaconPriorityBand,
    BeaconSeverity,
    BeaconSignalDefinition,
    BeaconSnapshot,
)
from app.beacon.definitions import (
    BEACON_SIGNAL_DEFINITIONS,
    BeaconSignalDefinitionRegistry,
)
from app.beacon.prioritization import BeaconPrioritizer, beacon_prioritizer
from app.beacon.quality import (
    EVIDENCE_QUALITY_SERVICE,
    EvidenceCompletenessState,
    EvidenceQualityInput,
    EvidenceReconciliationState,
)
from app.beacon.records import (
    BeaconCondition,
    BeaconLifecycleEvent,
    BeaconLifecycleProjection,
    BeaconPriority,
    BeaconSignal,
    BeaconSupportingFact,
)


class SignalEvaluationService:
    """Evaluates immutable Beacon definitions against authoritative snapshots."""

    def __init__(
        self,
        *,
        registry: BeaconSignalDefinitionRegistry = BEACON_SIGNAL_DEFINITIONS,
        prioritizer: BeaconPrioritizer = beacon_prioritizer,
    ) -> None:
        self.registry = registry
        self.prioritizer = prioritizer

    def evaluate_conditions(
        self,
        snapshot: BeaconSnapshot,
    ) -> tuple[BeaconCondition, ...]:
        return tuple(
            condition
            for definition in self.registry.definitions
            if (condition := self._evaluate_definition(definition, snapshot))
            is not None
        )

    def evaluate_signals(self, snapshot: BeaconSnapshot) -> tuple[BeaconSignal, ...]:
        definitions = {
            (definition.definition_id, definition.version): definition
            for definition in self.registry.definitions
        }
        signals = tuple(
            self._signal(
                condition,
                definitions[(condition.definition_id, condition.definition_version)],
            )
            for condition in self.evaluate_conditions(snapshot)
        )
        return self.prioritizer.prioritize(signals)

    @staticmethod
    def project_lifecycle(
        signal: BeaconSignal,
        event: BeaconLifecycleEvent | None,
        evaluated_at: datetime,
    ) -> BeaconSignal:
        current = (
            event
            if event is not None
            and event.signal_id == signal.id
            and event.evidence_digest == signal.evidence_digest
            else None
        )
        snoozed = bool(
            current
            and current.action is BeaconLifecycleAction.SNOOZE
            and current.snooze_until
            and current.snooze_until > evaluated_at
        )
        if snoozed:
            status = BeaconLifecycleStatus.SNOOZED
        elif (
            current is not None and current.action is BeaconLifecycleAction.ACKNOWLEDGE
        ):
            status = BeaconLifecycleStatus.ACKNOWLEDGED
        elif current is not None and current.action is BeaconLifecycleAction.REVIEW:
            status = BeaconLifecycleStatus.REVIEWED
        else:
            status = BeaconLifecycleStatus.ACTIVE
        return replace(
            signal,
            lifecycle=BeaconLifecycleProjection(
                status=status,
                latest_event=current,
                temporarily_suppressed=snoozed,
            ),
        )

    def _evaluate_definition(
        self,
        definition: BeaconSignalDefinition,
        snapshot: BeaconSnapshot,
    ) -> BeaconCondition | None:
        extracted = self._extract(definition, snapshot)
        if extracted is None:
            return None
        supporting_facts, count, age = extracted
        self._validate_evidence(definition, supporting_facts)
        evidence_digest = self._evidence_digest(definition, supporting_facts)
        return BeaconCondition(
            company_id=snapshot.company_id,
            definition_id=definition.definition_id,
            definition_version=definition.version,
            rule_code=definition.rule_code,
            source=definition.source,
            category=definition.category,
            severity=self._severity(definition, count=count, age=age),
            confidence=definition.confidence,
            supporting_facts=supporting_facts,
            evidence_digest=evidence_digest,
            evaluated_at=snapshot.measured_at,
            expires_at=snapshot.measured_at + timedelta(seconds=definition.ttl_seconds),
            expiration_policy=definition.expiration_policy,
        )

    def _extract(
        self,
        definition: BeaconSignalDefinition,
        snapshot: BeaconSnapshot,
    ) -> tuple[tuple[BeaconSupportingFact, ...], int, int] | None:
        if definition.condition_kind is BeaconConditionKind.OVERDUE_APPOINTMENTS:
            appointment_facts = snapshot.overdue_appointments
            if (
                appointment_facts.count == 0
                or appointment_facts.earliest_window_start is None
            ):
                return None
            age = max(
                0,
                int(
                    (
                        snapshot.measured_at - appointment_facts.earliest_window_start
                    ).total_seconds()
                    // 3600
                ),
            )
            return (
                (
                    self._fact(
                        "overdue_appointment_count",
                        appointment_facts.count,
                        "appointments",
                        snapshot,
                        appointment_facts.evidence,
                        "appointments",
                    ),
                    self._fact(
                        "oldest_overdue_hours",
                        age,
                        "appointments",
                        snapshot,
                        appointment_facts.evidence,
                        "hours",
                    ),
                ),
                appointment_facts.count,
                age,
            )
        if definition.condition_kind is BeaconConditionKind.PAUSED_JOBS:
            paused_facts = snapshot.paused_jobs
            if paused_facts.count == 0 or paused_facts.earliest_paused_at is None:
                return None
            age = max(
                0,
                int(
                    (
                        snapshot.measured_at - paused_facts.earliest_paused_at
                    ).total_seconds()
                    // 3600
                ),
            )
            return (
                (
                    self._fact(
                        "paused_job_count",
                        paused_facts.count,
                        "jobs",
                        snapshot,
                        paused_facts.evidence,
                        "jobs",
                    ),
                    self._fact(
                        "oldest_pause_hours",
                        age,
                        "jobs",
                        snapshot,
                        paused_facts.evidence,
                        "hours",
                    ),
                ),
                paused_facts.count,
                age,
            )
        invoice_facts = snapshot.past_due_invoices
        if invoice_facts.count == 0 or invoice_facts.earliest_due_on is None:
            return None
        age = max(0, (snapshot.measured_at.date() - invoice_facts.earliest_due_on).days)
        return (
            (
                self._fact(
                    "past_due_invoice_count",
                    invoice_facts.count,
                    "invoices",
                    snapshot,
                    invoice_facts.evidence,
                    "invoices",
                ),
                self._fact(
                    "past_due_invoice_face_value",
                    str(invoice_facts.total_amount.quantize(Decimal("0.01"))),
                    "invoices",
                    snapshot,
                    invoice_facts.evidence,
                    "currency_amount",
                ),
                self._fact(
                    "oldest_days_past_due",
                    age,
                    "invoices",
                    snapshot,
                    invoice_facts.evidence,
                    "days",
                ),
            ),
            invoice_facts.count,
            age,
        )

    @classmethod
    def _severity(
        cls,
        definition: BeaconSignalDefinition,
        *,
        count: int,
        age: int,
    ) -> BeaconSeverity:
        return next(
            (
                threshold.severity
                for threshold in definition.escalation_thresholds
                if cls._threshold_matches(threshold, count=count, age=age)
            ),
            definition.base_severity,
        )

    @staticmethod
    def _threshold_matches(
        threshold: BeaconEscalationThreshold,
        *,
        count: int,
        age: int,
    ) -> bool:
        checks = tuple(
            check
            for check in (
                age >= threshold.minimum_age
                if threshold.minimum_age is not None
                else None,
                count >= threshold.minimum_count
                if threshold.minimum_count is not None
                else None,
            )
            if check is not None
        )
        if not checks:
            return False
        if threshold.match is BeaconEscalationMatch.ANY:
            return any(checks)
        return all(checks)

    @staticmethod
    def _validate_evidence(
        definition: BeaconSignalDefinition,
        supporting_facts: tuple[BeaconSupportingFact, ...],
    ) -> None:
        if any(
            item.entity_type != definition.evidence_entity_type
            for fact in supporting_facts
            for item in fact.evidence
        ):
            raise ValueError("Beacon evidence does not match its immutable definition.")

    @staticmethod
    def _fact(
        name: str,
        value: str | int | bool,
        source: str,
        snapshot: BeaconSnapshot,
        evidence,
        unit: str,
    ) -> BeaconSupportingFact:
        return BeaconSupportingFact(
            name=name,
            value=value,
            source=source,
            measured_at=snapshot.measured_at,
            evidence=evidence,
            unit=unit,
        )

    @staticmethod
    def _evidence_digest(
        definition: BeaconSignalDefinition,
        supporting_facts: tuple[BeaconSupportingFact, ...],
    ) -> str:
        payload = json.dumps(
            {
                "definition_id": definition.definition_id,
                "definition_version": definition.version,
                "facts": [
                    {
                        "name": fact.name,
                        "value": fact.value,
                        "source": fact.source,
                        "evidence": sorted(
                            (
                                str(item.entity_id),
                                str(item.event_id) if item.event_id else None,
                                item.event_type,
                                item.occurred_at.isoformat()
                                if item.occurred_at
                                else None,
                            )
                            for item in fact.evidence
                        ),
                        "unit": fact.unit,
                    }
                    for fact in supporting_facts
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _signal(
        condition: BeaconCondition,
        definition: BeaconSignalDefinition,
    ) -> BeaconSignal:
        quality_definition_id = {
            "scheduling.overdue_committed_appointments": (
                "operational.scheduling.appointment_overdue"
            ),
            "operations.paused_jobs": "operational.job.intermediate_state_stalled",
        }.get(condition.rule_code)
        evidence = tuple(
            item for fact in condition.supporting_facts for item in fact.evidence
        )
        evidence_quality = (
            EVIDENCE_QUALITY_SERVICE.evaluate(
                EvidenceQualityInput(
                    definition_id=quality_definition_id,
                    source_authority=(
                        "SqlBeaconFactRepository authoritative Company snapshot"
                    ),
                    evidence_identities=tuple(
                        f"{item.entity_type}:{item.entity_id}:"
                        f"{item.event_id or 'record-state'}"
                        for item in evidence
                    ),
                    effective_at=min(
                        (
                            item.occurred_at
                            for item in evidence
                            if item.occurred_at is not None
                        ),
                        default=None,
                    ),
                    observed_as_of=condition.evaluated_at,
                    evaluated_at=condition.evaluated_at,
                    completeness=EvidenceCompletenessState.COMPLETE,
                    reconciliation=EvidenceReconciliationState.RECONCILED,
                    limitations=(),
                    evidence_digest=condition.evidence_digest,
                )
            )
            if quality_definition_id
            else None
        )
        return BeaconSignal(
            id=uuid5(
                NAMESPACE_URL,
                f"beacon:{condition.company_id}:{condition.rule_code}:"
                f"{condition.evidence_digest}",
            ),
            condition_key=uuid5(
                NAMESPACE_URL,
                "beacon:condition:"
                f"{condition.company_id}:{condition.source.value}:{condition.rule_code}",
            ),
            evidence_digest=condition.evidence_digest,
            definition_id=condition.definition_id,
            definition_version=condition.definition_version,
            rule_code=condition.rule_code,
            source=condition.source,
            title=definition.title,
            category=condition.category,
            severity=condition.severity,
            priority=BeaconPriority(
                band=BeaconPriorityBand.MONITOR,
                score=0,
                rank=0,
                ranking_factors=(),
                explanation="Priority has not been evaluated.",
                evaluated_at=condition.evaluated_at,
                tie_break_semantics="Priority has not been evaluated.",
            ),
            lifecycle=BeaconLifecycleProjection(
                status=BeaconLifecycleStatus.ACTIVE,
                latest_event=None,
                temporarily_suppressed=False,
            ),
            confidence=condition.confidence,
            evidence_quality=evidence_quality,
            supporting_facts=condition.supporting_facts,
            recommended_action=definition.recommended_action,
            created_at=condition.evaluated_at,
            expires_at=condition.expires_at,
            expiration_policy=condition.expiration_policy,
        )


signal_evaluation_service = SignalEvaluationService()
