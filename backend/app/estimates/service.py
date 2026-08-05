from collections.abc import Mapping
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.estimates.contracts import (
    CreateEstimateRevisionSpec,
    CreateEstimateSpec,
    EstimateDecisionSpec,
    EstimateLineSpec,
    EstimateRecord,
    EstimateTransitionSpec,
)
from app.estimates.errors import (
    EstimateConflictError,
    EstimateNotFoundError,
    EstimateValidationError,
)
from app.estimates.models import (
    Estimate,
    EstimateCommercialSnapshotReference,
    EstimateCustomerDecision,
    EstimateLifecycleHistory,
    EstimateLineItem,
    EstimateRevision,
)
from app.estimates.repository import EstimateRepository
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.price_book.models import PriceBookCommercialSnapshot


class EstimateService:
    def __init__(self, repository: EstimateRepository | None = None) -> None:
        self.repository = repository or EstimateRepository()

    async def create(
        self, session: AsyncSession, *, spec: CreateEstimateSpec
    ) -> EstimateRecord:
        if not spec.lines:
            raise EstimateValidationError(
                "An Estimate requires at least one commercial line."
            )
        snapshot_ids = tuple(line.snapshot_id for line in spec.lines)
        if len(snapshot_ids) != len(set(snapshot_ids)):
            raise EstimateValidationError(
                "A commercial snapshot may appear only once per revision."
            )
        async with session.begin():
            if not await self.repository.customer_belongs_to_company(
                session, company_id=spec.company_id, customer_id=spec.customer_id
            ):
                raise EstimateValidationError(
                    "Customer is outside the Estimate Company scope."
                )
            if (
                spec.service_location_id is not None
                and not await self.repository.location_belongs_to_customer(
                    session,
                    customer_id=spec.customer_id,
                    location_id=spec.service_location_id,
                )
            ):
                raise EstimateValidationError(
                    "Service Location is outside the Estimate Customer scope."
                )
            snapshots = await self.repository.get_snapshots(
                session,
                company_id=spec.company_id,
                branch_id=spec.branch_id,
                snapshot_ids=snapshot_ids,
            )
            by_id = {snapshot.id: snapshot for snapshot in snapshots}
            if set(by_id) != set(snapshot_ids):
                raise EstimateValidationError(
                    "Every Estimate line requires a Company- and Branch-scoped Price Book snapshot."
                )
            currencies = {snapshot.currency for snapshot in snapshots}
            if len(currencies) != 1:
                raise EstimateValidationError(
                    "An Estimate revision must use one currency."
                )
            now = datetime.now(timezone.utc)
            if spec.expires_at is not None and spec.expires_at <= now:
                raise EstimateValidationError("Estimate expiry must be in the future.")
            estimate = Estimate(
                id=uuid4(),
                company_id=spec.company_id,
                branch_id=spec.branch_id,
                customer_id=spec.customer_id,
                service_location_id=spec.service_location_id,
                estimate_number=await self.repository.next_estimate_number(
                    session, company_id=spec.company_id
                ),
                status="draft",
                acceptance_status="not_requested",
                created_by_user_id=spec.actor_user_id,
                updated_by_user_id=spec.actor_user_id,
                created_at=now,
                updated_at=now,
            )
            total = self.repository.snapshot_total(snapshots)
            revision = EstimateRevision(
                id=uuid4(),
                company_id=spec.company_id,
                estimate_id=estimate.id,
                parent_revision_id=None,
                revision_number=1,
                status="draft",
                proposal_title=spec.proposal_title,
                customer_message=spec.customer_message,
                terms=spec.terms,
                currency=next(iter(currencies)),
                subtotal_amount=total,
                total_amount=total,
                expires_at=spec.expires_at,
                created_by_user_id=spec.actor_user_id,
                created_at=now,
            )
            lines: list[EstimateLineItem] = []
            refs: list[EstimateCommercialSnapshotReference] = []
            for position, line_spec in enumerate(spec.lines, start=1):
                snapshot = by_id[line_spec.snapshot_id]
                line = EstimateLineItem(
                    id=uuid4(),
                    company_id=spec.company_id,
                    revision_id=revision.id,
                    position=position,
                    title=line_spec.title,
                    description=line_spec.description,
                    quantity=snapshot.quantity,
                    unit_price=snapshot.unit_price,
                    line_total=snapshot.extended_amount,
                    currency=snapshot.currency,
                    created_at=now,
                )
                lines.append(line)
                refs.append(
                    EstimateCommercialSnapshotReference(
                        id=uuid4(),
                        company_id=spec.company_id,
                        revision_id=revision.id,
                        line_item_id=line.id,
                        snapshot_id=snapshot.id,
                        snapshot_digest=snapshot.digest,
                        created_at=now,
                    )
                )
            history = EstimateLifecycleHistory(
                id=uuid4(),
                company_id=spec.company_id,
                branch_id=spec.branch_id,
                estimate_id=estimate.id,
                from_status=None,
                to_status="draft",
                from_acceptance_status=None,
                to_acceptance_status="not_requested",
                reason="Estimate created",
                actor_user_id=spec.actor_user_id,
                version=1,
                occurred_at=now,
            )
            await self.repository.add_foundation(
                session,
                estimate=estimate,
                revision=revision,
                lines=tuple(lines),
                references=tuple(refs),
                history=history,
            )
            BusinessEventService.stage(
                session,
                BusinessEventCreate(
                    event_type=EventType.ESTIMATE_CREATED,
                    entity_type="estimate",
                    entity_id=estimate.id,
                    company_id=spec.company_id,
                    branch_id=spec.branch_id,
                    user_id=spec.actor_user_id,
                    payload={
                        "estimate_number": estimate.estimate_number,
                        "revision_id": str(revision.id),
                        "commercial_snapshot_ids": [
                            str(value) for value in snapshot_ids
                        ],
                    },
                ),
            )
        result = await self.repository.get(
            session, company_id=spec.company_id, estimate_id=estimate.id
        )
        if result is None:
            raise EstimateConflictError("Created Estimate could not be reloaded.")
        return result

    async def revise(
        self, session: AsyncSession, *, spec: CreateEstimateRevisionSpec
    ) -> EstimateRecord:
        if not spec.lines:
            raise EstimateValidationError(
                "An Estimate revision requires at least one line."
            )
        snapshot_ids = tuple(line.snapshot_id for line in spec.lines)
        if len(snapshot_ids) != len(set(snapshot_ids)):
            raise EstimateValidationError(
                "A commercial snapshot may appear only once per revision."
            )
        async with session.begin():
            estimate = await self._locked_estimate(
                session,
                company_id=spec.company_id,
                branch_id=spec.branch_id,
                estimate_id=spec.estimate_id,
                expected_version=spec.expected_version,
            )
            if estimate.status in {"approved", "accepted", "cancelled"}:
                raise EstimateValidationError(
                    "An approved or cancelled Estimate cannot be revised."
                )
            if estimate.current_revision_id is None:
                raise EstimateConflictError("Estimate has no current revision.")
            prior = await self.repository.get_revision(
                session,
                company_id=spec.company_id,
                revision_id=estimate.current_revision_id,
            )
            if prior is None:
                raise EstimateConflictError("Current Estimate revision is unavailable.")
            snapshots = await self.repository.get_snapshots(
                session,
                company_id=spec.company_id,
                branch_id=spec.branch_id,
                snapshot_ids=snapshot_ids,
            )
            by_id = {snapshot.id: snapshot for snapshot in snapshots}
            if set(by_id) != set(snapshot_ids):
                raise EstimateValidationError(
                    "Every Estimate line requires a Company- and Branch-scoped Price Book snapshot."
                )
            currencies = {snapshot.currency for snapshot in snapshots}
            if len(currencies) != 1:
                raise EstimateValidationError(
                    "An Estimate revision must use one currency."
                )
            now = datetime.now(timezone.utc)
            if spec.expires_at is not None and spec.expires_at <= now:
                raise EstimateValidationError("Estimate expiry must be in the future.")
            revision = EstimateRevision(
                id=uuid4(),
                company_id=spec.company_id,
                estimate_id=estimate.id,
                parent_revision_id=prior.id,
                revision_number=prior.revision_number + 1,
                status="draft",
                proposal_title=spec.proposal_title,
                customer_message=spec.customer_message,
                terms=spec.terms,
                currency=next(iter(currencies)),
                subtotal_amount=self.repository.snapshot_total(snapshots),
                total_amount=self.repository.snapshot_total(snapshots),
                expires_at=spec.expires_at,
                created_by_user_id=spec.actor_user_id,
                created_at=now,
            )
            lines, references = self._revision_evidence(
                company_id=spec.company_id,
                revision_id=revision.id,
                line_specs=spec.lines,
                snapshots=by_id,
                created_at=now,
            )
            old_status = estimate.status
            old_acceptance = estimate.acceptance_status
            self._advance_aggregate(
                estimate,
                status="draft",
                acceptance_status="not_requested",
                actor_user_id=spec.actor_user_id,
                occurred_at=now,
            )
            history = self._history(
                estimate=estimate,
                from_status=old_status,
                from_acceptance_status=old_acceptance,
                reason="Estimate revision created",
                actor_user_id=spec.actor_user_id,
                occurred_at=now,
            )
            await self.repository.add_revision(
                session,
                estimate=estimate,
                revision=revision,
                lines=lines,
                references=references,
                history=history,
            )
            self._stage_event(
                session,
                estimate=estimate,
                revision_id=revision.id,
                actor_user_id=spec.actor_user_id,
                event_type=EventType.ESTIMATE_REVISION_CREATED,
                payload={
                    "parent_revision_id": str(prior.id),
                    "revision_number": revision.revision_number,
                    "commercial_snapshot_ids": [str(value) for value in snapshot_ids],
                },
            )
        return await self._reload(
            session, company_id=spec.company_id, estimate_id=spec.estimate_id
        )

    async def send(
        self, session: AsyncSession, *, spec: EstimateTransitionSpec
    ) -> EstimateRecord:
        return await self._transition(
            session,
            spec=spec,
            allowed_from={"draft"},
            to_status="sent",
            acceptance_status="pending",
            event_type=EventType.ESTIMATE_SENT,
            reason="Estimate sent",
        )

    async def mark_viewed(
        self, session: AsyncSession, *, spec: EstimateTransitionSpec
    ) -> EstimateRecord:
        return await self._transition(
            session,
            spec=spec,
            allowed_from={"sent"},
            to_status="viewed",
            acceptance_status="pending",
            event_type=EventType.ESTIMATE_VIEWED,
            reason="Estimate viewed",
        )

    async def approve(
        self, session: AsyncSession, *, spec: EstimateDecisionSpec
    ) -> EstimateRecord:
        if not spec.customer_name.strip():
            raise EstimateValidationError("Customer approval requires a customer name.")
        if spec.rejection_reason is not None:
            raise EstimateValidationError(
                "Customer approval cannot include a rejection reason."
            )
        return await self._decide(session, spec=spec, decision="approved")

    async def reject(
        self, session: AsyncSession, *, spec: EstimateDecisionSpec
    ) -> EstimateRecord:
        if not spec.customer_name.strip():
            raise EstimateValidationError(
                "Customer rejection requires a customer name."
            )
        if not spec.rejection_reason or not spec.rejection_reason.strip():
            raise EstimateValidationError("Customer rejection requires a reason.")
        return await self._decide(session, spec=spec, decision="rejected")

    async def expire(
        self, session: AsyncSession, *, spec: EstimateTransitionSpec
    ) -> EstimateRecord:
        async with session.begin():
            estimate = await self._locked_estimate(
                session,
                company_id=spec.company_id,
                branch_id=spec.branch_id,
                estimate_id=spec.estimate_id,
                expected_version=spec.expected_version,
            )
            if estimate.status not in {"sent", "viewed"}:
                raise EstimateValidationError(
                    f"Estimate cannot transition from {estimate.status} to expired."
                )
            revision = await self._current_revision(session, estimate=estimate)
            if revision.expires_at is None or spec.occurred_at < revision.expires_at:
                raise EstimateValidationError(
                    "Estimate cannot expire before its expiry time."
                )
            await self._apply_transition(
                session,
                estimate=estimate,
                actor_user_id=spec.actor_user_id,
                occurred_at=spec.occurred_at,
                to_status="expired",
                acceptance_status="expired",
                event_type=EventType.ESTIMATE_EXPIRED,
                reason="Estimate expired",
            )
        return await self._reload(
            session, company_id=spec.company_id, estimate_id=spec.estimate_id
        )

    async def _transition(
        self,
        session: AsyncSession,
        *,
        spec: EstimateTransitionSpec,
        allowed_from: set[str],
        to_status: str,
        acceptance_status: str,
        event_type: EventType,
        reason: str,
    ) -> EstimateRecord:
        async with session.begin():
            estimate = await self._locked_estimate(
                session,
                company_id=spec.company_id,
                branch_id=spec.branch_id,
                estimate_id=spec.estimate_id,
                expected_version=spec.expected_version,
            )
            if estimate.status not in allowed_from:
                raise EstimateValidationError(
                    f"Estimate cannot transition from {estimate.status} to {to_status}."
                )
            await self._apply_transition(
                session,
                estimate=estimate,
                actor_user_id=spec.actor_user_id,
                occurred_at=spec.occurred_at,
                to_status=to_status,
                acceptance_status=acceptance_status,
                event_type=event_type,
                reason=reason,
            )
        return await self._reload(
            session, company_id=spec.company_id, estimate_id=spec.estimate_id
        )

    async def _decide(
        self, session: AsyncSession, *, spec: EstimateDecisionSpec, decision: str
    ) -> EstimateRecord:
        async with session.begin():
            estimate = await self._locked_estimate(
                session,
                company_id=spec.company_id,
                branch_id=spec.branch_id,
                estimate_id=spec.estimate_id,
                expected_version=spec.expected_version,
            )
            if estimate.status not in {"sent", "viewed"}:
                raise EstimateValidationError(
                    f"Estimate cannot transition from {estimate.status} to {decision}."
                )
            revision = await self._current_revision(session, estimate=estimate)
            customer_decision = EstimateCustomerDecision(
                id=uuid4(),
                company_id=estimate.company_id,
                estimate_id=estimate.id,
                revision_id=revision.id,
                decision=decision,
                customer_name=spec.customer_name.strip(),
                customer_email=spec.customer_email,
                customer_comment=spec.customer_comment,
                rejection_reason=spec.rejection_reason.strip()
                if spec.rejection_reason
                else None,
                evidence_reference=spec.evidence_reference,
                recorded_by_user_id=spec.actor_user_id,
                occurred_at=spec.occurred_at,
                created_at=datetime.now(timezone.utc),
            )
            await self.repository.add_customer_decision(
                session, decision=customer_decision
            )
            await self._apply_transition(
                session,
                estimate=estimate,
                actor_user_id=spec.actor_user_id,
                occurred_at=spec.occurred_at,
                to_status=decision,
                acceptance_status=decision,
                event_type=(
                    EventType.ESTIMATE_APPROVED
                    if decision == "approved"
                    else EventType.ESTIMATE_REJECTED
                ),
                reason=f"Estimate {decision}",
                extra_payload={"decision_id": str(customer_decision.id)},
            )
        return await self._reload(
            session, company_id=spec.company_id, estimate_id=spec.estimate_id
        )

    async def _apply_transition(
        self,
        session: AsyncSession,
        *,
        estimate: Estimate,
        actor_user_id: UUID,
        occurred_at: datetime,
        to_status: str,
        acceptance_status: str,
        event_type: EventType,
        reason: str,
        extra_payload: dict[str, object] | None = None,
    ) -> None:
        old_status = estimate.status
        old_acceptance = estimate.acceptance_status
        self._advance_aggregate(
            estimate,
            status=to_status,
            acceptance_status=acceptance_status,
            actor_user_id=actor_user_id,
            occurred_at=occurred_at,
        )
        history = self._history(
            estimate=estimate,
            from_status=old_status,
            from_acceptance_status=old_acceptance,
            reason=reason,
            actor_user_id=actor_user_id,
            occurred_at=occurred_at,
        )
        await self.repository.add_lifecycle_history(session, history=history)
        self._stage_event(
            session,
            estimate=estimate,
            revision_id=estimate.current_revision_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            payload={
                "from_status": old_status,
                "to_status": to_status,
                **(extra_payload or {}),
            },
        )

    async def _locked_estimate(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        estimate_id: UUID,
        expected_version: int,
    ) -> Estimate:
        estimate = await self.repository.get_for_update(
            session, company_id=company_id, estimate_id=estimate_id
        )
        if estimate is None:
            raise EstimateNotFoundError("Estimate was not found.")
        if estimate.branch_id != branch_id:
            raise EstimateNotFoundError(
                "Estimate was not found in the authorized Branch."
            )
        if estimate.version != expected_version:
            raise EstimateConflictError("Estimate version is stale.")
        return estimate

    async def _current_revision(
        self, session: AsyncSession, *, estimate: Estimate
    ) -> EstimateRevision:
        if estimate.current_revision_id is None:
            raise EstimateConflictError("Estimate has no current revision.")
        revision = await self.repository.get_revision(
            session,
            company_id=estimate.company_id,
            revision_id=estimate.current_revision_id,
        )
        if revision is None:
            raise EstimateConflictError("Current Estimate revision is unavailable.")
        return revision

    @staticmethod
    def _advance_aggregate(
        estimate: Estimate,
        *,
        status: str,
        acceptance_status: str,
        actor_user_id: UUID,
        occurred_at: datetime,
    ) -> None:
        if occurred_at < estimate.updated_at:
            raise EstimateValidationError(
                "Estimate lifecycle evidence cannot move backward in time."
            )
        estimate.status = status
        estimate.acceptance_status = acceptance_status
        estimate.version += 1
        estimate.updated_by_user_id = actor_user_id
        estimate.updated_at = occurred_at

    @staticmethod
    def _history(
        *,
        estimate: Estimate,
        from_status: str,
        from_acceptance_status: str,
        reason: str,
        actor_user_id: UUID,
        occurred_at: datetime,
    ) -> EstimateLifecycleHistory:
        return EstimateLifecycleHistory(
            id=uuid4(),
            company_id=estimate.company_id,
            branch_id=estimate.branch_id,
            estimate_id=estimate.id,
            from_status=from_status,
            to_status=estimate.status,
            from_acceptance_status=from_acceptance_status,
            to_acceptance_status=estimate.acceptance_status,
            reason=reason,
            actor_user_id=actor_user_id,
            version=estimate.version,
            occurred_at=occurred_at,
        )

    @staticmethod
    def _revision_evidence(
        *,
        company_id: UUID,
        revision_id: UUID,
        line_specs: tuple[EstimateLineSpec, ...],
        snapshots: Mapping[UUID, PriceBookCommercialSnapshot],
        created_at: datetime,
    ) -> tuple[
        tuple[EstimateLineItem, ...],
        tuple[EstimateCommercialSnapshotReference, ...],
    ]:
        lines: list[EstimateLineItem] = []
        references: list[EstimateCommercialSnapshotReference] = []
        for position, line_spec in enumerate(line_specs, start=1):
            snapshot = snapshots[line_spec.snapshot_id]
            line = EstimateLineItem(
                id=uuid4(),
                company_id=company_id,
                revision_id=revision_id,
                position=position,
                title=line_spec.title,
                description=line_spec.description,
                quantity=snapshot.quantity,
                unit_price=snapshot.unit_price,
                line_total=snapshot.extended_amount,
                currency=snapshot.currency,
                created_at=created_at,
            )
            lines.append(line)
            references.append(
                EstimateCommercialSnapshotReference(
                    id=uuid4(),
                    company_id=company_id,
                    revision_id=revision_id,
                    line_item_id=line.id,
                    snapshot_id=snapshot.id,
                    snapshot_digest=snapshot.digest,
                    created_at=created_at,
                )
            )
        return tuple(lines), tuple(references)

    @staticmethod
    def _stage_event(
        session: AsyncSession,
        *,
        estimate: Estimate,
        revision_id: UUID | None,
        actor_user_id: UUID,
        event_type: EventType,
        payload: dict[str, object],
    ) -> None:
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="estimate",
                entity_id=estimate.id,
                company_id=estimate.company_id,
                branch_id=estimate.branch_id,
                user_id=actor_user_id,
                payload={
                    "estimate_number": estimate.estimate_number,
                    "revision_id": str(revision_id),
                    **payload,
                },
            ),
        )

    async def _reload(
        self, session: AsyncSession, *, company_id: UUID, estimate_id: UUID
    ) -> EstimateRecord:
        result = await self.repository.get(
            session, company_id=company_id, estimate_id=estimate_id
        )
        if result is None:
            raise EstimateConflictError("Estimate could not be reloaded.")
        return result


estimate_service = EstimateService()
