from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.beacon.contracts import (
    BeaconEvidence,
    BeaconLifecycleAction,
    BeaconSignalSource,
    BeaconSnapshot,
    OverdueAppointmentFacts,
    PastDueInvoiceFacts,
    PausedJobFacts,
)
from app.beacon.models import BeaconSignalReviewEventModel
from app.beacon.records import BeaconLifecycleEvent
from app.events.models import BusinessEvent
from app.financials.models import Invoice
from app.jobs.models import Job
from app.scheduling.models import Appointment

EVIDENCE_LIMIT = 25


class SqlBeaconFactRepository:
    """Company-scoped, read-only authoritative fact queries for Beacon rules."""

    @classmethod
    async def load_snapshot(
        cls,
        session: AsyncSession,
        *,
        company_id: UUID,
        measured_at: datetime,
    ) -> BeaconSnapshot:
        appointment_rows = tuple(
            (
                await session.execute(
                    select(Appointment.id, Appointment.arrival_window_start_at)
                    .where(
                        Appointment.company_id == company_id,
                        Appointment.status.in_(("scheduled", "confirmed")),
                        Appointment.arrival_window_start_at < measured_at,
                    )
                    .order_by(Appointment.arrival_window_start_at, Appointment.id)
                    .limit(EVIDENCE_LIMIT)
                )
            ).all()
        )
        appointment_count = int(
            await session.scalar(
                select(func.count(Appointment.id)).where(
                    Appointment.company_id == company_id,
                    Appointment.status.in_(("scheduled", "confirmed")),
                    Appointment.arrival_window_start_at < measured_at,
                )
            )
            or 0
        )
        paused_job_rows = tuple(
            (
                await session.execute(
                    select(Job.id, Job.paused_at)
                    .where(Job.company_id == company_id, Job.status == "paused")
                    .order_by(Job.paused_at, Job.id)
                    .limit(EVIDENCE_LIMIT)
                )
            ).all()
        )
        paused_job_count = int(
            await session.scalar(
                select(func.count(Job.id)).where(
                    Job.company_id == company_id, Job.status == "paused"
                )
            )
            or 0
        )
        invoice_rows = tuple(
            (
                await session.execute(
                    select(Invoice.id, Invoice.due_on, Invoice.total_amount)
                    .where(
                        Invoice.company_id == company_id,
                        Invoice.status.in_(("issued", "partially_paid")),
                        Invoice.due_on.is_not(None),
                        Invoice.due_on < measured_at.date(),
                    )
                    .order_by(Invoice.due_on, Invoice.id)
                    .limit(EVIDENCE_LIMIT)
                )
            ).all()
        )
        invoice_count, invoice_total = (
            await session.execute(
                select(
                    func.count(Invoice.id),
                    func.coalesce(func.sum(Invoice.total_amount), 0),
                ).where(
                    Invoice.company_id == company_id,
                    Invoice.status.in_(("issued", "partially_paid")),
                    Invoice.due_on.is_not(None),
                    Invoice.due_on < measured_at.date(),
                )
            )
        ).one()
        entity_ids = {
            *(row.id for row in appointment_rows),
            *(row.id for row in paused_job_rows),
            *(row.id for row in invoice_rows),
        }
        events = await cls._events_by_entity(
            session,
            company_id=company_id,
            entity_ids=entity_ids,
            measured_at=measured_at,
        )
        return BeaconSnapshot(
            company_id=company_id,
            measured_at=measured_at,
            overdue_appointments=OverdueAppointmentFacts(
                count=appointment_count,
                earliest_window_start=(
                    appointment_rows[0].arrival_window_start_at
                    if appointment_rows
                    else None
                ),
                evidence=tuple(
                    cls._evidence("appointment", row.id, events.get(row.id))
                    for row in appointment_rows
                ),
            ),
            paused_jobs=PausedJobFacts(
                count=paused_job_count,
                earliest_paused_at=paused_job_rows[0].paused_at
                if paused_job_rows
                else None,
                evidence=tuple(
                    cls._evidence("job", row.id, events.get(row.id))
                    for row in paused_job_rows
                ),
            ),
            past_due_invoices=PastDueInvoiceFacts(
                count=int(invoice_count),
                total_amount=Decimal(invoice_total),
                earliest_due_on=invoice_rows[0].due_on if invoice_rows else None,
                evidence=tuple(
                    cls._evidence("invoice", row.id, events.get(row.id))
                    for row in invoice_rows
                ),
            ),
        )

    @staticmethod
    async def _events_by_entity(
        session: AsyncSession,
        *,
        company_id: UUID,
        entity_ids: set[UUID],
        measured_at: datetime,
    ) -> dict[UUID, BusinessEvent]:
        if not entity_ids:
            return {}
        statement: Select[tuple[BusinessEvent]] = (
            select(BusinessEvent)
            .where(
                BusinessEvent.company_id == company_id,
                BusinessEvent.entity_id.in_(entity_ids),
                BusinessEvent.occurred_at <= measured_at,
            )
            .order_by(
                BusinessEvent.entity_id,
                BusinessEvent.occurred_at.desc(),
                BusinessEvent.created_at.desc(),
                BusinessEvent.id.desc(),
            )
        )
        rows = tuple((await session.scalars(statement)).all())
        latest: dict[UUID, BusinessEvent] = {}
        for event in rows:
            if event.entity_id is not None:
                latest.setdefault(event.entity_id, event)
        return latest

    @staticmethod
    def _evidence(
        entity_type: str,
        entity_id: UUID,
        event: BusinessEvent | None,
    ) -> BeaconEvidence:
        return BeaconEvidence(
            entity_type=entity_type,
            entity_id=entity_id,
            event_id=event.id if event else None,
            event_type=event.event_type if event else None,
            occurred_at=event.occurred_at if event else None,
        )


beacon_fact_repository = SqlBeaconFactRepository()


class BeaconLifecycleRepository:
    @staticmethod
    async def append(
        session: AsyncSession,
        *,
        company_id: UUID,
        condition_key: UUID,
        signal_id: UUID,
        rule_code: str,
        signal_source: BeaconSignalSource,
        evidence_digest: str,
        action: BeaconLifecycleAction,
        actor_membership_id: UUID,
        action_at: datetime,
        snooze_until: datetime | None,
    ) -> BeaconLifecycleEvent:
        entity = BeaconSignalReviewEventModel(
            company_id=company_id,
            condition_key=condition_key,
            signal_id=signal_id,
            rule_code=rule_code,
            signal_source=signal_source.value,
            evidence_digest=evidence_digest,
            action=action.value,
            actor_membership_id=actor_membership_id,
            action_at=action_at,
            snooze_until=snooze_until,
            created_at=action_at,
        )
        session.add(entity)
        await session.flush()
        return _lifecycle_event(entity)

    @staticmethod
    async def latest_for_conditions(
        session: AsyncSession,
        *,
        company_id: UUID,
        condition_keys: tuple[UUID, ...],
    ) -> dict[UUID, BeaconLifecycleEvent]:
        if not condition_keys:
            return {}
        entities = tuple(
            (
                await session.scalars(
                    select(BeaconSignalReviewEventModel)
                    .where(
                        BeaconSignalReviewEventModel.company_id == company_id,
                        BeaconSignalReviewEventModel.condition_key.in_(condition_keys),
                    )
                    .order_by(
                        BeaconSignalReviewEventModel.condition_key,
                        BeaconSignalReviewEventModel.action_at.desc(),
                        BeaconSignalReviewEventModel.id.desc(),
                    )
                )
            ).all()
        )
        latest: dict[UUID, BeaconLifecycleEvent] = {}
        for entity in entities:
            latest.setdefault(entity.condition_key, _lifecycle_event(entity))
        return latest

    @staticmethod
    async def list_history(
        session: AsyncSession,
        *,
        company_id: UUID,
        condition_key: UUID,
        limit: int,
    ) -> tuple[BeaconLifecycleEvent, ...]:
        entities = (
            await session.scalars(
                select(BeaconSignalReviewEventModel)
                .where(
                    BeaconSignalReviewEventModel.company_id == company_id,
                    BeaconSignalReviewEventModel.condition_key == condition_key,
                )
                .order_by(
                    BeaconSignalReviewEventModel.action_at.desc(),
                    BeaconSignalReviewEventModel.id.desc(),
                )
                .limit(limit)
            )
        ).all()
        return tuple(_lifecycle_event(entity) for entity in entities)


def _lifecycle_event(entity: BeaconSignalReviewEventModel) -> BeaconLifecycleEvent:
    return BeaconLifecycleEvent(
        id=entity.id,
        company_id=entity.company_id,
        condition_key=entity.condition_key,
        signal_id=entity.signal_id,
        rule_code=entity.rule_code,
        signal_source=BeaconSignalSource(entity.signal_source),
        evidence_digest=entity.evidence_digest,
        action=BeaconLifecycleAction(entity.action),
        actor_membership_id=entity.actor_membership_id,
        action_at=entity.action_at,
        snooze_until=entity.snooze_until,
        created_at=entity.created_at,
    )


beacon_lifecycle_repository = BeaconLifecycleRepository()
