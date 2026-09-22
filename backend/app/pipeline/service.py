from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.models import Customer
from app.estimates.models import Estimate
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.jobs.models import Job
from app.pipeline.models import ACTIVE_STAGES, Lead, LeadHistory
from app.pipeline.schemas import (
    ContactActivityCreate,
    LeadCreate,
    LeadTransition,
    PipelineBucket,
    PipelineProjection,
)
from app.platform.audit.service import AuditEntry, audit_service
from app.platform.company.membership_models import Membership
from app.platform.permissions.authorization import AuthorizationContext
from app.scheduling.models import Appointment

ALLOWED_TRANSITIONS = {
    "new": {
        "contacted",
        "qualified",
        "appointment_needed",
        "scheduled",
        "lost",
        "nurture",
    },
    "contacted": {"qualified", "appointment_needed", "scheduled", "lost", "nurture"},
    "qualified": {
        "appointment_needed",
        "scheduled",
        "estimate_follow_up",
        "won",
        "lost",
        "nurture",
    },
    "appointment_needed": {"scheduled", "estimate_follow_up", "lost", "nurture"},
    "scheduled": {"estimate_follow_up", "won", "lost", "nurture"},
    "estimate_follow_up": {"appointment_needed", "scheduled", "won", "lost", "nurture"},
    "nurture": {"contacted", "qualified", "appointment_needed", "lost"},
    "won": set(),
    "lost": set(),
}


class PipelineError(ValueError):
    pass


class PipelineNotFound(PipelineError):
    pass


class PipelineConflict(PipelineError):
    pass


def branch_ids(context: AuthorizationContext) -> frozenset[UUID]:
    if context.active_branch is not None:
        return frozenset({context.active_branch.id})
    return context.authorized_branch_ids


def attention_state(lead: Lead, now: datetime) -> str | None:
    if lead.stage not in ACTIVE_STAGES or lead.stage == "scheduled":
        return None
    if lead.stage == "new" and lead.first_contact_at is None:
        return "new_uncontacted"
    if (
        lead.stage in {"qualified", "appointment_needed"}
        and lead.appointment_id is None
    ):
        return "qualified_not_scheduled"
    if lead.stage == "estimate_follow_up":
        return "estimate_follow_up"
    if lead.next_action_type is None or lead.next_action_due_at is None:
        return "missing_next_action"
    if lead.next_action_due_at <= now:
        return "overdue" if lead.next_action_due_at < now else "due_now"
    if lead.last_action_at is not None and lead.last_action_at < now - timedelta(
        days=14
    ):
        return "stale"
    return None


class PipelineService:
    async def create(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        data: LeadCreate,
    ) -> Lead:
        if data.branch_id not in branch_ids(context):
            raise PipelineNotFound("Lead not found")
        customer: Customer | None = None
        if data.customer_id is not None:
            customer = await session.scalar(
                select(Customer).where(
                    Customer.id == data.customer_id,
                    Customer.company_id == context.company.id,
                )
            )
            if customer is None:
                raise PipelineNotFound("Lead not found")
        await self._validate_assignee(session, context, data.assigned_user_id)
        if data.source_provider_id:
            existing = await session.scalar(
                select(Lead).where(
                    Lead.company_id == context.company.id,
                    Lead.source_system == data.source_system,
                    Lead.source_provider_id == data.source_provider_id,
                )
            )
            if existing is not None:
                if existing.branch_id not in branch_ids(context):
                    raise PipelineNotFound("Lead not found")
                return existing

        now = datetime.now(timezone.utc)
        values = data.model_dump()
        if customer is not None and not values["prospect_name"]:
            values["prospect_name"] = customer.display_name
        lead = Lead(
            company_id=context.company.id,
            created_by_user_id=context.user.id,
            updated_by_user_id=context.user.id,
            **values,
        )
        session.add(lead)
        await session.flush()
        self._history(session, lead, context.user.id, "created", to_stage="new")
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=EventType.LEAD_CREATED,
                entity_type="lead",
                entity_id=lead.id,
                company_id=lead.company_id,
                branch_id=lead.branch_id,
                user_id=context.user.id,
                payload={
                    "version": "1.0",
                    "lead_source": lead.lead_source,
                    "stage": "new",
                },
                occurred_at=now,
            ),
        )
        audit_service.stage(
            session,
            AuditEntry(
                action="pipeline.lead.create",
                resource_type="lead",
                actor_user_id=context.user.id,
                company_id=lead.company_id,
                branch_id=lead.branch_id,
                resource_id=lead.id,
                details={"stage": "new", "source": lead.lead_source},
            ),
        )
        await session.commit()
        await session.refresh(lead)
        return lead

    async def get(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        lead_id: UUID,
    ) -> Lead:
        record = await session.scalar(
            select(Lead).where(
                Lead.id == lead_id,
                Lead.company_id == context.company.id,
                Lead.branch_id.in_(branch_ids(context)),
            )
        )
        if record is None:
            raise PipelineNotFound("Lead not found")
        return record

    async def transition(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        lead_id: UUID,
        data: LeadTransition,
    ) -> Lead:
        lead = await self.get(session, context=context, lead_id=lead_id)
        if lead.version != data.version:
            raise PipelineConflict("Lead changed; refresh")
        target = data.stage.value
        if target not in ALLOWED_TRANSITIONS[lead.stage]:
            raise PipelineConflict("Lead stage transition is not allowed")
        if target == "lost" and not (data.lost_reason or "").strip():
            raise PipelineConflict("Lost reason is required")
        await self._validate_links(session, context, lead.branch_id, data)
        await self._validate_assignee(session, context, data.assigned_user_id)
        appointment_id = data.appointment_id or lead.appointment_id
        if target == "scheduled" and appointment_id is None:
            raise PipelineConflict("Scheduled stage requires Appointment evidence")

        old = lead.stage
        lead.stage = target
        lead.outcome = target if target in {"won", "lost", "nurture"} else None
        for field in (
            "next_action_type",
            "next_action_due_at",
            "assigned_user_id",
            "appointment_id",
            "job_id",
            "estimate_id",
            "lost_reason",
            "attributable_value_minor",
            "value_currency",
            "value_authority",
        ):
            value = getattr(data, field)
            if value is not None:
                setattr(lead, field, value)
        if target in {"won", "lost"}:
            lead.next_action_type = None
            lead.next_action_due_at = None
        lead.last_action_at = datetime.now(timezone.utc)
        lead.updated_by_user_id = context.user.id
        lead.version += 1
        self._history(
            session,
            lead,
            context.user.id,
            "stage_changed",
            from_stage=old,
            to_stage=target,
        )
        event = (
            EventType.LEAD_CONVERTED
            if target == "won"
            else EventType.LEAD_QUALIFIED
            if target == "qualified"
            else EventType.LEAD_UPDATED
        )
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event,
                entity_type="lead",
                entity_id=lead.id,
                company_id=lead.company_id,
                branch_id=lead.branch_id,
                user_id=context.user.id,
                payload={"version": "1.0", "from_stage": old, "to_stage": target},
            ),
        )
        audit_service.stage(
            session,
            AuditEntry(
                action="pipeline.lead.transition",
                resource_type="lead",
                actor_user_id=context.user.id,
                company_id=lead.company_id,
                branch_id=lead.branch_id,
                resource_id=lead.id,
                details={"from_stage": old, "to_stage": target},
            ),
        )
        await session.commit()
        await session.refresh(lead)
        return lead

    async def record_contact(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        lead_id: UUID,
        data: ContactActivityCreate,
    ) -> Lead:
        lead = await self.get(session, context=context, lead_id=lead_id)
        duplicate = await session.scalar(
            select(LeadHistory.id).where(
                LeadHistory.company_id == lead.company_id,
                LeadHistory.lead_id == lead.id,
                LeadHistory.idempotency_key == data.idempotency_key,
            )
        )
        if duplicate is not None:
            return lead
        lead.contact_attempt_count += 1
        lead.first_contact_at = lead.first_contact_at or data.occurred_at
        lead.last_action_at = data.occurred_at
        lead.next_action_type = data.next_action_type
        lead.next_action_due_at = data.next_action_due_at
        lead.updated_by_user_id = context.user.id
        lead.version += 1
        if lead.stage == "new":
            lead.stage = "contacted"
        self._history(
            session,
            lead,
            context.user.id,
            f"contact:{data.channel}",
            detail=data.disposition,
            idempotency_key=data.idempotency_key,
        )
        await session.commit()
        await session.refresh(lead)
        return lead

    async def list(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        view: str = "all",
        stage: str | None = None,
        assigned_user_id: UUID | None = None,
        source: str | None = None,
        service_category: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Lead], int]:
        now = datetime.now(timezone.utc)
        query = select(Lead).where(
            Lead.company_id == context.company.id,
            Lead.branch_id.in_(branch_ids(context)),
        )
        if stage:
            query = query.where(Lead.stage == stage)
        if assigned_user_id:
            query = query.where(Lead.assigned_user_id == assigned_user_id)
        if source:
            query = query.where(Lead.lead_source == source)
        if service_category:
            query = query.where(Lead.service_category == service_category)
        if view == "new":
            query = query.where(Lead.stage == "new")
        elif view == "scheduled" or view == "moving_forward":
            query = query.where(Lead.stage == "scheduled")
        elif view == "estimate_follow_up":
            query = query.where(Lead.stage == "estimate_follow_up")
        elif view in {"won", "lost", "nurture"}:
            query = query.where(Lead.stage == view)

        # Attention is derived from several authoritative fields, so apply that
        # deterministic classification before pagination.
        if view == "needs_attention":
            candidates = list((await session.scalars(query)).all())
            candidates = [item for item in candidates if attention_state(item, now)]
            candidates.sort(
                key=lambda item: (
                    item.next_action_due_at or item.created_at,
                    item.created_at,
                )
            )
            return candidates[offset : offset + limit], len(candidates)

        count = await session.scalar(select(func.count()).select_from(query.subquery()))
        records = list(
            (
                await session.scalars(
                    query.order_by(
                        Lead.next_action_due_at.asc().nullsfirst(),
                        Lead.created_at.asc(),
                    )
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
        )
        return records, int(count or 0)

    async def projection(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
    ) -> PipelineProjection:
        now = datetime.now(timezone.utc)
        query = select(Lead).where(
            Lead.company_id == context.company.id,
            Lead.branch_id.in_(branch_ids(context)),
        )
        all_records = list((await session.scalars(query)).all())
        moving = [record for record in all_records if record.stage == "scheduled"]
        attention = [record for record in all_records if attention_state(record, now)]
        return PipelineProjection(
            as_of=now,
            company_id=context.company.id,
            branch_ids=tuple(sorted(branch_ids(context), key=str)),
            moving_forward=self._bucket(
                "moving_forward", "Scheduled / moving forward", moving
            ),
            needs_attention=self._bucket(
                "needs_attention", "Needs attention", attention
            ),
        )

    async def history(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        lead_id: UUID,
    ) -> tuple[LeadHistory, ...]:
        await self.get(session, context=context, lead_id=lead_id)
        rows = await session.scalars(
            select(LeadHistory)
            .where(
                LeadHistory.company_id == context.company.id,
                LeadHistory.lead_id == lead_id,
            )
            .order_by(LeadHistory.occurred_at)
        )
        return tuple(rows.all())

    async def _validate_links(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        branch_id: UUID,
        data: LeadTransition,
    ) -> None:
        for record_id, model in (
            (data.appointment_id, Appointment),
            (data.job_id, Job),
            (data.estimate_id, Estimate),
        ):
            if record_id is None:
                continue
            exists = await session.scalar(
                select(model.id).where(
                    model.id == record_id,
                    model.company_id == context.company.id,
                    model.branch_id == branch_id,
                )
            )
            if exists is None:
                raise PipelineNotFound("Lead not found")

    async def _validate_assignee(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        user_id: UUID | None,
    ) -> None:
        if user_id is None:
            return
        membership = await session.scalar(
            select(Membership.id).where(
                Membership.user_id == user_id,
                Membership.company_id == context.company.id,
                Membership.status == "active",
            )
        )
        if membership is None:
            raise PipelineNotFound("Lead not found")

    @staticmethod
    def _bucket(key: str, label: str, records: Sequence[Lead]) -> PipelineBucket:
        complete = bool(records) and all(
            record.attributable_value_minor is not None and record.value_currency
            for record in records
        )
        currencies = {
            record.value_currency for record in records if record.value_currency
        }
        complete = complete and len(currencies) == 1
        return PipelineBucket(
            key=key,
            label=label,
            count=len(records),
            value_minor=(
                sum(record.attributable_value_minor or 0 for record in records)
                if complete
                else None
            ),
            currency=next(iter(currencies)) if complete else None,
            value_complete=complete,
            drilldown_path=f"/pipeline?{urlencode({'view': key})}",
        )

    @staticmethod
    def _history(
        session: AsyncSession,
        lead: Lead,
        actor: UUID,
        action: str,
        *,
        from_stage: str | None = None,
        to_stage: str | None = None,
        detail: str | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        session.add(
            LeadHistory(
                company_id=lead.company_id,
                branch_id=lead.branch_id,
                lead_id=lead.id,
                action_type=action,
                from_stage=from_stage,
                to_stage=to_stage,
                detail=detail,
                idempotency_key=idempotency_key,
                actor_user_id=actor,
            )
        )


pipeline_service = PipelineService()
