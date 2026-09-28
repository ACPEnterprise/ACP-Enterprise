import hashlib
import json
from datetime import datetime, timezone
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.models import Customer
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.jobs.models import Job
from app.pipeline.models import Lead
from app.platform.audit.service import AuditEntry, audit_service
from app.platform.permissions.authorization import AuthorizationContext
from app.scheduling.models import Appointment

from .contracts import AttributionMethod, AttributionTargetType
from .models import (
    MarketingAppointmentAttribution,
    MarketingAttributionAssignment,
    MarketingCampaign,
    MarketingChannel,
    MarketingCustomerAttribution,
    MarketingJobAttribution,
    MarketingLeadAttribution,
    MarketingSource,
    MarketingTouch,
)
from .schemas import (
    AttributionResponse,
    CampaignResponse,
    CatalogResponse,
    ChannelResponse,
    EvidenceCoverageResponse,
    ManualAttributionConfirmation,
    SourceResponse,
)


class MarketingError(ValueError):
    pass


class MarketingNotFound(MarketingError):
    pass


class MarketingConflict(MarketingError):
    pass


LINK_MODELS = {
    AttributionTargetType.CUSTOMER: (MarketingCustomerAttribution, "customer_id"),
    AttributionTargetType.LEAD: (MarketingLeadAttribution, "lead_id"),
    AttributionTargetType.APPOINTMENT: (
        MarketingAppointmentAttribution,
        "appointment_id",
    ),
    AttributionTargetType.JOB: (MarketingJobAttribution, "job_id"),
}


def ordered_touch_ids(touches: list[MarketingTouch]) -> tuple[UUID, ...]:
    """Stable evidence order used by first/latest attribution policies."""
    return tuple(
        item.id
        for item in sorted(touches, key=lambda item: (item.observed_at, item.id))
    )


class MarketingService:
    async def catalog(
        self, session: AsyncSession, *, context: AuthorizationContext
    ) -> CatalogResponse:
        company_id = context.company.id
        channels = list(
            await session.scalars(
                select(MarketingChannel)
                .where(MarketingChannel.company_id == company_id)
                .order_by(MarketingChannel.code, MarketingChannel.id)
            )
        )
        sources = list(
            await session.scalars(
                select(MarketingSource)
                .where(MarketingSource.company_id == company_id)
                .order_by(MarketingSource.code, MarketingSource.id)
            )
        )
        campaigns = list(
            await session.scalars(
                select(MarketingCampaign)
                .where(MarketingCampaign.company_id == company_id)
                .order_by(MarketingCampaign.name, MarketingCampaign.id)
            )
        )
        return CatalogResponse(
            channels=tuple(ChannelResponse.model_validate(item) for item in channels),
            sources=tuple(SourceResponse.model_validate(item) for item in sources),
            campaigns=tuple(
                CampaignResponse.model_validate(item) for item in campaigns
            ),
        )

    async def attribution_history(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        target_type: AttributionTargetType,
        target_id: UUID,
    ) -> tuple[AttributionResponse, ...]:
        link_model, target_field = cast(tuple[Any, str], LINK_MODELS[target_type])
        records = list(
            await session.scalars(
                select(MarketingAttributionAssignment)
                .join(
                    link_model,
                    link_model.assignment_id == MarketingAttributionAssignment.id,
                )
                .where(
                    MarketingAttributionAssignment.company_id == context.company.id,
                    getattr(link_model, target_field) == target_id,
                )
                .order_by(
                    MarketingAttributionAssignment.assigned_at,
                    MarketingAttributionAssignment.id,
                )
            )
        )
        return tuple(self._response(item, target_type, target_id) for item in records)

    async def resolution_queue(
        self, session: AsyncSession, *, context: AuthorizationContext, limit: int
    ) -> tuple[AttributionResponse, ...]:
        assignments = list(
            await session.scalars(
                select(MarketingAttributionAssignment)
                .where(
                    MarketingAttributionAssignment.company_id == context.company.id,
                    MarketingAttributionAssignment.resolution.in_(
                        ("unknown", "conflicting")
                    ),
                )
                .order_by(
                    MarketingAttributionAssignment.assigned_at,
                    MarketingAttributionAssignment.id,
                )
                .limit(limit)
            )
        )
        result: list[AttributionResponse] = []
        for assignment in assignments:
            target = await self._target_for_assignment(session, assignment.id)
            if target is not None:
                result.append(self._response(assignment, *target))
        return tuple(result)

    async def coverage(
        self, session: AsyncSession, *, context: AuthorizationContext
    ) -> EvidenceCoverageResponse:
        rows = (
            await session.execute(
                select(
                    MarketingAttributionAssignment.resolution,
                    func.count(MarketingAttributionAssignment.id),
                )
                .where(MarketingAttributionAssignment.company_id == context.company.id)
                .group_by(MarketingAttributionAssignment.resolution)
            )
        ).all()
        counts = {str(key): int(value) for key, value in rows}
        total = sum(counts.values())
        resolved = counts.get("resolved", 0)
        coverage = round((resolved / total) * 100) if total else 0
        missing = tuple(
            key
            for key in ("unknown", "conflicting", "not_available")
            if counts.get(key, 0)
        )
        availability = (
            "unavailable"
            if total == 0
            else "complete"
            if resolved == total
            else "partial"
        )
        return EvidenceCoverageResponse(
            as_of=datetime.now(timezone.utc),
            total_assignments=total,
            resolved=resolved,
            unknown=counts.get("unknown", 0),
            conflicting=counts.get("conflicting", 0),
            not_available=counts.get("not_available", 0),
            coverage_percent=coverage,
            availability=availability,
            missing_components=missing,
        )

    async def confirm_manual(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        data: ManualAttributionConfirmation,
    ) -> AttributionResponse:
        digest = hashlib.sha256(
            json.dumps(
                data.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        existing = await session.scalar(
            select(MarketingAttributionAssignment).where(
                MarketingAttributionAssignment.company_id == context.company.id,
                MarketingAttributionAssignment.idempotency_key == data.idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_digest != digest:
                raise MarketingConflict(
                    "idempotency key was used for another confirmation"
                )
            target = await self._target_for_assignment(session, existing.id)
            if target is None:
                raise MarketingConflict("attribution target evidence is incomplete")
            return self._response(existing, *target)

        branch_id = await self._validate_target(
            session, context, data.target_type, data.target_id, data.branch_id
        )
        if branch_id is not None and not context.can_access_branch(branch_id):
            raise MarketingNotFound("Marketing attribution target not found")
        if data.touch_id is not None:
            touch = await session.scalar(
                select(MarketingTouch).where(
                    MarketingTouch.company_id == context.company.id,
                    MarketingTouch.id == data.touch_id,
                )
            )
            if touch is None or (
                touch.branch_id is not None
                and not context.can_access_branch(touch.branch_id)
            ):
                raise MarketingNotFound("Supporting touch evidence not found")
            if branch_id is not None and touch.branch_id not in (None, branch_id):
                raise MarketingConflict("Supporting touch has a different Branch scope")
        if data.supersedes_assignment_id is not None:
            prior = await session.scalar(
                select(MarketingAttributionAssignment).where(
                    MarketingAttributionAssignment.company_id == context.company.id,
                    MarketingAttributionAssignment.id == data.supersedes_assignment_id,
                )
            )
            prior_target = (
                await self._target_for_assignment(session, prior.id) if prior else None
            )
            if prior is None or prior_target != (data.target_type, data.target_id):
                raise MarketingConflict("superseded attribution does not match target")

        assignment = MarketingAttributionAssignment(
            company_id=context.company.id,
            branch_id=branch_id,
            touch_id=data.touch_id,
            role=data.role.value,
            method=AttributionMethod.MANUALLY_CONFIRMED.value,
            resolution=data.resolution.value,
            supporting_evidence_reference=data.supporting_evidence_reference,
            reason=data.reason,
            actor_user_id=context.user.id,
            supersedes_assignment_id=data.supersedes_assignment_id,
            idempotency_key=data.idempotency_key,
            request_digest=digest,
        )
        session.add(assignment)
        await session.flush()
        link_model, target_field = LINK_MODELS[data.target_type]
        session.add(
            link_model(
                assignment_id=assignment.id,
                company_id=assignment.company_id,
                branch_id=branch_id,
                **{target_field: data.target_id},
            )
        )
        event_payload: dict[str, object] = {
            "version": "1.0",
            "target_type": data.target_type.value,
            "target_id": str(data.target_id),
            "role": data.role.value,
            "method": AttributionMethod.MANUALLY_CONFIRMED.value,
            "resolution": data.resolution.value,
            "touch_id": str(data.touch_id) if data.touch_id else None,
            "supersedes_assignment_id": str(data.supersedes_assignment_id)
            if data.supersedes_assignment_id
            else None,
            # Keep the operator-entered evidence reference in the permissioned
            # Marketing record. Events and audit metadata receive only its
            # digest so arbitrary PII or secrets cannot propagate downstream.
            "supporting_evidence_digest": hashlib.sha256(
                data.supporting_evidence_reference.encode("utf-8")
            ).hexdigest(),
            "idempotency_key": data.idempotency_key,
        }
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=EventType.MARKETING_ATTRIBUTION_CONFIRMED,
                entity_type="marketing_attribution_assignment",
                entity_id=assignment.id,
                company_id=assignment.company_id,
                branch_id=branch_id,
                user_id=context.user.id,
                payload=event_payload,
            ),
        )
        audit_service.stage(
            session,
            AuditEntry(
                action="marketing.attribution.confirm",
                resource_type="marketing_attribution_assignment",
                actor_user_id=context.user.id,
                company_id=assignment.company_id,
                branch_id=branch_id,
                resource_id=assignment.id,
                reason_code="manual_confirmation",
                details=event_payload,
            ),
        )
        await session.commit()
        await session.refresh(assignment)
        return self._response(assignment, data.target_type, data.target_id)

    async def _validate_target(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        target_type: AttributionTargetType,
        target_id: UUID,
        requested_branch_id: UUID | None,
    ) -> UUID | None:
        company_id = context.company.id
        if target_type is AttributionTargetType.CUSTOMER:
            found = await session.scalar(
                select(Customer.id).where(
                    Customer.company_id == company_id, Customer.id == target_id
                )
            )
            if found is None:
                raise MarketingNotFound("Marketing attribution target not found")
            return requested_branch_id
        model = cast(
            Any,
            {
                AttributionTargetType.LEAD: Lead,
                AttributionTargetType.APPOINTMENT: Appointment,
                AttributionTargetType.JOB: Job,
            }[target_type],
        )
        branch_id = await session.scalar(
            select(model.branch_id).where(
                model.company_id == company_id, model.id == target_id
            )
        )
        if branch_id is None or (
            requested_branch_id is not None and requested_branch_id != branch_id
        ):
            raise MarketingNotFound("Marketing attribution target not found")
        return branch_id

    async def _target_for_assignment(
        self, session: AsyncSession, assignment_id: UUID
    ) -> tuple[AttributionTargetType, UUID] | None:
        for target_type, link_definition in LINK_MODELS.items():
            link_model, target_field = cast(tuple[Any, str], link_definition)
            target_id = await session.scalar(
                select(getattr(link_model, target_field)).where(
                    link_model.assignment_id == assignment_id
                )
            )
            if target_id is not None:
                return target_type, target_id
        return None

    @staticmethod
    def _response(
        assignment: MarketingAttributionAssignment,
        target_type: AttributionTargetType,
        target_id: UUID,
    ) -> AttributionResponse:
        return AttributionResponse(
            **{
                key: getattr(assignment, key)
                for key in AttributionResponse.model_fields
                if key not in {"target_type", "target_id"}
            },
            target_type=target_type,
            target_id=target_id,
        )


marketing_service = MarketingService()
