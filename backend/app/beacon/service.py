from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.ext.asyncio import AsyncSession

from app.beacon.contracts import (
    BeaconCategory,
    BeaconConfidence,
    BeaconConfidenceLevel,
    BeaconEvidence,
    BeaconExpirationPolicy,
    BeaconFactRepository,
    BeaconPriorityBand,
    BeaconSeverity,
    BeaconSignalSource,
    BeaconSnapshot,
)
from app.beacon.prioritization import beacon_prioritizer
from app.beacon.records import BeaconPriority, BeaconSignal, BeaconSupportingFact
from app.beacon.repository import beacon_fact_repository
from app.platform.permissions.authorization import (
    AuthorizationContext,
    authorization_service,
)
from app.platform.permissions.codes import AnalyticsPermission

SIGNAL_TTL = timedelta(minutes=15)
CONFIDENCE = BeaconConfidence(
    level=BeaconConfidenceLevel.HIGH,
    basis="Authoritative Company-scoped records measured by a deterministic rule.",
)


class BeaconQueryService:
    def __init__(
        self, repository: BeaconFactRepository = beacon_fact_repository
    ) -> None:
        self.repository = repository

    async def list_signals(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        now: datetime | None = None,
    ) -> tuple[BeaconSignal, ...]:
        authorization_service.require_permission(context, AnalyticsPermission.READ)
        measured_at = now or datetime.now(timezone.utc)
        snapshot = await self.repository.load_snapshot(
            session,
            company_id=context.company.id,
            measured_at=measured_at,
        )
        signals = tuple(
            signal
            for signal in (
                self._overdue_appointments(snapshot),
                self._paused_jobs(snapshot),
                self._past_due_invoices(snapshot),
            )
            if signal is not None
        )
        return beacon_prioritizer.prioritize(signals)

    @classmethod
    def _overdue_appointments(cls, snapshot: BeaconSnapshot) -> BeaconSignal | None:
        facts = snapshot.overdue_appointments
        if facts.count == 0 or facts.earliest_window_start is None:
            return None
        age_hours = max(
            0,
            int(
                (snapshot.measured_at - facts.earliest_window_start).total_seconds()
                // 3600
            ),
        )
        severity = (
            BeaconSeverity.CRITICAL
            if age_hours >= 24
            else BeaconSeverity.IMPORTANT
            if age_hours >= 4
            else BeaconSeverity.ATTENTION
        )
        supporting = (
            cls._fact(
                "overdue_appointment_count",
                facts.count,
                "appointments",
                snapshot,
                facts.evidence,
                "appointments",
            ),
            cls._fact(
                "oldest_overdue_hours",
                age_hours,
                "appointments",
                snapshot,
                facts.evidence,
                "hours",
            ),
        )
        return cls._signal(
            snapshot,
            rule_code="scheduling.overdue_committed_appointments",
            source=BeaconSignalSource.SCHEDULING,
            title="Committed appointments are past their arrival window",
            category=BeaconCategory.SCHEDULING,
            severity=severity,
            supporting_facts=supporting,
            recommended_action=(
                "Review the listed committed appointments and record an authoritative "
                "completion, no-show, cancellation, or reschedule outcome."
            ),
        )

    @classmethod
    def _paused_jobs(cls, snapshot: BeaconSnapshot) -> BeaconSignal | None:
        facts = snapshot.paused_jobs
        if facts.count == 0 or facts.earliest_paused_at is None:
            return None
        age_hours = max(
            0,
            int(
                (snapshot.measured_at - facts.earliest_paused_at).total_seconds()
                // 3600
            ),
        )
        severity = (
            BeaconSeverity.IMPORTANT
            if age_hours >= 24 or facts.count >= 5
            else BeaconSeverity.ATTENTION
        )
        return cls._signal(
            snapshot,
            rule_code="operations.paused_jobs",
            source=BeaconSignalSource.JOBS,
            title="Jobs remain paused",
            category=BeaconCategory.OPERATIONS,
            severity=severity,
            supporting_facts=(
                cls._fact(
                    "paused_job_count",
                    facts.count,
                    "jobs",
                    snapshot,
                    facts.evidence,
                    "jobs",
                ),
                cls._fact(
                    "oldest_pause_hours",
                    age_hours,
                    "jobs",
                    snapshot,
                    facts.evidence,
                    "hours",
                ),
            ),
            recommended_action=(
                "Review each paused job's recorded reason and either resume, cancel, "
                "or leave it paused with current operational evidence."
            ),
        )

    @classmethod
    def _past_due_invoices(cls, snapshot: BeaconSnapshot) -> BeaconSignal | None:
        facts = snapshot.past_due_invoices
        if facts.count == 0 or facts.earliest_due_on is None:
            return None
        days_past_due = max(
            0, (snapshot.measured_at.date() - facts.earliest_due_on).days
        )
        severity = (
            BeaconSeverity.CRITICAL
            if days_past_due >= 30
            else BeaconSeverity.IMPORTANT
            if days_past_due >= 7
            else BeaconSeverity.ATTENTION
        )
        return cls._signal(
            snapshot,
            rule_code="revenue.past_due_invoices",
            source=BeaconSignalSource.INVOICES,
            title="Issued invoices are past due",
            category=BeaconCategory.REVENUE,
            severity=severity,
            supporting_facts=(
                cls._fact(
                    "past_due_invoice_count",
                    facts.count,
                    "invoices",
                    snapshot,
                    facts.evidence,
                    "invoices",
                ),
                cls._fact(
                    "past_due_invoice_face_value",
                    str(facts.total_amount.quantize(Decimal("0.01"))),
                    "invoices",
                    snapshot,
                    facts.evidence,
                    "currency_amount",
                ),
                cls._fact(
                    "oldest_days_past_due",
                    days_past_due,
                    "invoices",
                    snapshot,
                    facts.evidence,
                    "days",
                ),
            ),
            recommended_action=(
                "Review the authoritative invoice and payment records before beginning "
                "the Company's approved collection workflow."
            ),
        )

    @classmethod
    def _signal(
        cls,
        snapshot: BeaconSnapshot,
        *,
        rule_code: str,
        source: BeaconSignalSource,
        title: str,
        category: BeaconCategory,
        severity: BeaconSeverity,
        supporting_facts: tuple[BeaconSupportingFact, ...],
        recommended_action: str,
    ) -> BeaconSignal:
        return BeaconSignal(
            id=cls._signal_id(snapshot.company_id, rule_code, supporting_facts),
            rule_code=rule_code,
            source=source,
            title=title,
            category=category,
            severity=severity,
            priority=BeaconPriority(
                band=BeaconPriorityBand.MONITOR,
                score=0,
                rank=0,
                ranking_factors=(),
                explanation="Priority has not been evaluated.",
                evaluated_at=snapshot.measured_at,
                tie_break_semantics="Priority has not been evaluated.",
            ),
            confidence=CONFIDENCE,
            supporting_facts=supporting_facts,
            recommended_action=recommended_action,
            created_at=snapshot.measured_at,
            expires_at=snapshot.measured_at + SIGNAL_TTL,
            expiration_policy=BeaconExpirationPolicy.REPLACE_ON_NEXT_EVALUATION,
        )

    @staticmethod
    def _fact(
        name: str,
        value: str | int | bool,
        source: str,
        snapshot: BeaconSnapshot,
        evidence: tuple[BeaconEvidence, ...],
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
    def _signal_id(
        company_id: UUID,
        rule_code: str,
        supporting_facts: tuple[BeaconSupportingFact, ...],
    ) -> UUID:
        payload = json.dumps(
            [
                {
                    "name": fact.name,
                    "value": fact.value,
                    "source": fact.source,
                    "evidence": sorted(
                        (
                            str(item.entity_id),
                            str(item.event_id) if item.event_id else None,
                            item.event_type,
                        )
                        for item in fact.evidence
                    ),
                    "unit": fact.unit,
                }
                for fact in supporting_facts
            ],
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(payload.encode()).hexdigest()
        return uuid5(NAMESPACE_URL, f"beacon:{company_id}:{rule_code}:{digest}")


beacon_query_service = BeaconQueryService()
