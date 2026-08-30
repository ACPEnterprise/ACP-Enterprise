import hashlib
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.estimates.contracts import (
    ConvertEstimateToJobSpec,
    CreateEstimateRevisionSpec,
    CreateEstimateSpec,
    EstimateConversionRecord,
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
    EstimateJobConversion,
    EstimateLifecycleHistory,
    EstimateLineItem,
    EstimateRevision,
)
from app.estimates.pricing import PricingLine, PricingResult, calculate
from app.estimates.repository import EstimateRepository
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.jobs.repository import job_repository
from app.jobs.service import JobService
from app.price_book.models import PriceBookCommercialSnapshot
from app.tax_policy.models import OperationalTaxPolicy


class EstimateService:
    def __init__(self, repository: EstimateRepository | None = None) -> None:
        self.repository = repository or EstimateRepository()

    async def convert_to_job(
        self, session: AsyncSession, *, spec: ConvertEstimateToJobSpec
    ) -> EstimateConversionRecord:
        idempotency_key = spec.idempotency_key.strip()
        if not idempotency_key:
            raise EstimateValidationError("Conversion idempotency key is required.")
        now = datetime.now(timezone.utc)
        async with session.begin():
            estimate = await self._locked_estimate(
                session,
                company_id=spec.company_id,
                branch_id=spec.branch_id,
                estimate_id=spec.estimate_id,
                expected_version=spec.expected_version,
            )
            existing = await self.repository.get_conversion(
                session, company_id=spec.company_id, estimate_id=spec.estimate_id
            )
            if existing is not None:
                if existing.idempotency_key != idempotency_key:
                    raise EstimateConflictError(
                        "Estimate has already been converted to a Job."
                    )
                job = await job_repository.get_job(
                    session, company_id=spec.company_id, job_id=existing.job_id
                )
                if job is None:
                    raise EstimateConflictError(
                        "Converted Job evidence is unavailable."
                    )
                return self.repository.conversion_record(
                    existing, job_number=job.job_number
                )
            if (
                estimate.status != "approved"
                or estimate.acceptance_status != "approved"
            ):
                raise EstimateValidationError(
                    "Only an approved Estimate may be converted to a Job."
                )
            if estimate.current_revision_id is None:
                raise EstimateConflictError(
                    "Approved Estimate revision is unavailable."
                )
            if estimate.service_location_id is None:
                raise EstimateValidationError(
                    "Estimate conversion requires a Service Location."
                )
            lineage_refs = await self.repository.get_snapshot_lineage(
                session,
                company_id=spec.company_id,
                revision_id=estimate.current_revision_id,
            )
            if not lineage_refs:
                raise EstimateConflictError(
                    "Approved Estimate has no commercial snapshot lineage."
                )
            lineage = [
                {
                    "line_item_id": str(ref.line_item_id),
                    "snapshot_id": str(ref.snapshot_id),
                    "snapshot_digest": ref.snapshot_digest,
                }
                for ref in lineage_refs
            ]
            lineage_digest = hashlib.sha256(
                json.dumps(lineage, separators=(",", ":"), sort_keys=True).encode()
            ).hexdigest()
            job = await JobService().stage_estimate_conversion_job(
                session,
                company_id=estimate.company_id,
                branch_id=estimate.branch_id,
                customer_id=estimate.customer_id,
                service_location_id=estimate.service_location_id,
                actor_user_id=spec.actor_user_id,
                job_type_code=spec.job_type_code,
                customer_reported_problem=spec.customer_reported_problem,
                internal_description=spec.internal_description,
                occurred_at=now,
            )
            conversion = EstimateJobConversion(
                id=uuid4(),
                company_id=estimate.company_id,
                branch_id=estimate.branch_id,
                estimate_id=estimate.id,
                estimate_revision_id=estimate.current_revision_id,
                job_id=job.id,
                estimate_version=estimate.version,
                snapshot_lineage=lineage,
                snapshot_lineage_digest=lineage_digest,
                idempotency_key=idempotency_key,
                converted_by_user_id=spec.actor_user_id,
                converted_at=now,
            )
            await self.repository.add_conversion(session, conversion=conversion)
            self._stage_event(
                session,
                estimate=estimate,
                revision_id=estimate.current_revision_id,
                actor_user_id=spec.actor_user_id,
                event_type=EventType.ESTIMATE_CONVERTED,
                payload={
                    "job_id": str(job.id),
                    "job_number": job.job_number,
                    "snapshot_lineage_digest": lineage_digest,
                },
            )
        return self.repository.conversion_record(conversion, job_number=job.job_number)

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
            pricing = await self._price_snapshots(
                session,
                company_id=spec.company_id,
                branch_id=spec.branch_id,
                snapshots=snapshots,
                discount_type=spec.discount_type,
                discount_value=spec.discount_value,
            )
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
                subtotal_amount=pricing.subtotal,
                discount_type=spec.discount_type,
                discount_value=spec.discount_value,
                discount_amount=pricing.discount,
                taxable_basis=pricing.taxable_basis,
                tax_amount=pricing.tax,
                total_amount=pricing.total,
                calculation_evidence=self._calculation_evidence(pricing),
                expires_at=spec.expires_at,
                created_by_user_id=spec.actor_user_id,
                created_at=now,
            )
            lines: list[EstimateLineItem] = []
            refs: list[EstimateCommercialSnapshotReference] = []
            priced_by_id = {line.key: line for line in pricing.lines}
            for position, line_spec in enumerate(spec.lines, start=1):
                snapshot = by_id[line_spec.snapshot_id]
                priced = priced_by_id[snapshot.id]
                tax_data = self._tax_data(snapshot)
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
                    discount_allocation=priced.discount,
                    discounted_basis=priced.basis,
                    tax_amount=priced.tax,
                    taxable=bool(tax_data.get("taxable", False)),
                    tax_classification_id=UUID(str(tax_data["id"]))
                    if tax_data.get("id")
                    else None,
                    tax_policy_id=priced.tax_policy_id,
                    tax_policy_version=priced.tax_policy_version,
                    applied_rate_basis_points=priced.rate_basis_points
                    if priced.taxable
                    else None,
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
                        **self._option_evidence(snapshot),
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
            pricing = await self._price_snapshots(
                session,
                company_id=spec.company_id,
                branch_id=spec.branch_id,
                snapshots=snapshots,
                discount_type=spec.discount_type,
                discount_value=spec.discount_value,
            )
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
                subtotal_amount=pricing.subtotal,
                discount_type=spec.discount_type,
                discount_value=spec.discount_value,
                discount_amount=pricing.discount,
                taxable_basis=pricing.taxable_basis,
                tax_amount=pricing.tax,
                total_amount=pricing.total,
                calculation_evidence=self._calculation_evidence(pricing),
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
                pricing=pricing,
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
        pricing: PricingResult,
    ) -> tuple[
        tuple[EstimateLineItem, ...],
        tuple[EstimateCommercialSnapshotReference, ...],
    ]:
        lines: list[EstimateLineItem] = []
        references: list[EstimateCommercialSnapshotReference] = []
        priced_by_id = {line.key: line for line in pricing.lines}
        for position, line_spec in enumerate(line_specs, start=1):
            snapshot = snapshots[line_spec.snapshot_id]
            priced = priced_by_id[snapshot.id]
            tax_data = EstimateService._tax_data(snapshot)
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
                discount_allocation=priced.discount,
                discounted_basis=priced.basis,
                tax_amount=priced.tax,
                taxable=bool(tax_data.get("taxable", False)),
                tax_classification_id=UUID(str(tax_data["id"]))
                if tax_data.get("id")
                else None,
                tax_policy_id=priced.tax_policy_id,
                tax_policy_version=priced.tax_policy_version,
                applied_rate_basis_points=priced.rate_basis_points
                if priced.taxable
                else None,
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
                    **EstimateService._option_evidence(snapshot),
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

    @staticmethod
    def _option_evidence(snapshot: PriceBookCommercialSnapshot) -> dict[str, object]:
        data = snapshot.snapshot_data
        constraints = data.get("option_group_constraints")
        group_id = data.get("option_group_id")
        option_id = data.get("option_id")
        if group_id is None and option_id is None:
            return {
                "option_group_id": None,
                "option_id": None,
                "minimum_selections": None,
                "maximum_selections": None,
            }
        if not isinstance(constraints, dict) or group_id is None or option_id is None:
            raise EstimateValidationError("Price Book option evidence is incomplete.")
        try:
            minimum = int(constraints["minimum_selections"])
            maximum = int(constraints["maximum_selections"])
            group_uuid = UUID(str(group_id))
            option_uuid = UUID(str(option_id))
        except (KeyError, TypeError, ValueError) as exc:
            raise EstimateValidationError(
                "Price Book option selection constraints are invalid."
            ) from exc
        if minimum < 0 or maximum < 1 or minimum > maximum:
            raise EstimateValidationError(
                "Price Book option selection constraints are invalid."
            )
        return {
            "option_group_id": group_uuid,
            "option_id": option_uuid,
            "minimum_selections": minimum,
            "maximum_selections": maximum,
        }

    async def _price_snapshots(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        snapshots: tuple[PriceBookCommercialSnapshot, ...],
        discount_type: str | None,
        discount_value: Decimal | None,
    ) -> PricingResult:
        groups: dict[UUID, tuple[int, int, set[UUID]]] = {}
        lines: list[PricingLine] = []
        for snapshot in snapshots:
            option = self._option_evidence(snapshot)
            group_id = option["option_group_id"]
            option_id = option["option_id"]
            if isinstance(group_id, UUID) and isinstance(option_id, UUID):
                minimum_value = option["minimum_selections"]
                maximum_value = option["maximum_selections"]
                if not isinstance(minimum_value, int) or not isinstance(
                    maximum_value, int
                ):
                    raise EstimateValidationError(
                        "Price Book option selection constraints are invalid."
                    )
                minimum = minimum_value
                maximum = maximum_value
                prior = groups.get(group_id)
                if prior is not None and prior[:2] != (minimum, maximum):
                    raise EstimateValidationError(
                        "Selected Price Book options contain conflicting group evidence."
                    )
                selected = prior[2] if prior else set()
                selected.add(option_id)
                groups[group_id] = (minimum, maximum, selected)

            tax_data = snapshot.snapshot_data.get("tax_classification")
            taxable = isinstance(tax_data, dict) and bool(tax_data.get("taxable"))
            policy: OperationalTaxPolicy | None = None
            if taxable:
                classification_id = (
                    tax_data.get("id") if isinstance(tax_data, dict) else None
                )
                if classification_id is None:
                    raise EstimateValidationError(
                        "Taxable Price Book evidence is incomplete."
                    )
                effective_at = snapshot.effective_at
                candidates = tuple(
                    (
                        await session.scalars(
                            select(OperationalTaxPolicy)
                            .where(
                                OperationalTaxPolicy.company_id == company_id,
                                OperationalTaxPolicy.tax_classification_id
                                == UUID(str(classification_id)),
                                OperationalTaxPolicy.currency == snapshot.currency,
                                OperationalTaxPolicy.effective_at <= effective_at,
                                or_(
                                    OperationalTaxPolicy.expires_at.is_(None),
                                    OperationalTaxPolicy.expires_at > effective_at,
                                ),
                                or_(
                                    OperationalTaxPolicy.branch_id == branch_id,
                                    OperationalTaxPolicy.branch_id.is_(None),
                                ),
                            )
                            .order_by(
                                OperationalTaxPolicy.branch_id.desc().nullslast(),
                                OperationalTaxPolicy.effective_at.desc(),
                            )
                        )
                    ).all()
                )
                if candidates:
                    preferred_branch = candidates[0].branch_id
                    same_scope = tuple(
                        candidate
                        for candidate in candidates
                        if candidate.branch_id == preferred_branch
                        and candidate.effective_at == candidates[0].effective_at
                    )
                    if len(same_scope) != 1:
                        raise EstimateValidationError(
                            "Tax policy resolution is ambiguous."
                        )
                    policy = candidates[0]
                elif discount_type is not None or group_id is not None:
                    raise EstimateValidationError(
                        "No effective operational tax policy exists for taxable pricing."
                    )
            lines.append(
                PricingLine(
                    key=snapshot.id,
                    amount=snapshot.extended_amount,
                    taxable=taxable,
                    rate_basis_points=policy.rate_basis_points if policy else 0,
                    tax_policy_id=policy.id if policy else None,
                    tax_policy_version=policy.version if policy else None,
                )
            )
        for minimum, maximum, selected in groups.values():
            if not minimum <= len(selected) <= maximum:
                raise EstimateValidationError(
                    "Price Book option selection violates its immutable group constraints."
                )
        try:
            return calculate(tuple(lines), discount_type, discount_value)
        except ValueError as exc:
            raise EstimateValidationError(str(exc)) from exc

    @staticmethod
    def _calculation_evidence(pricing: PricingResult) -> dict[str, object]:
        return {
            "rounding": "ROUND_HALF_EVEN",
            "calculation_order": [
                "line_amounts",
                "subtotal",
                "proportional_estimate_discount",
                "discounted_taxable_basis",
                "tax",
                "total",
            ],
            "lines": [
                {
                    "snapshot_id": str(line.key),
                    "discount_allocation": str(line.discount),
                    "discounted_basis": str(line.basis),
                    "tax": str(line.tax),
                    "taxable": line.taxable,
                    "tax_policy_id": str(line.tax_policy_id)
                    if line.tax_policy_id
                    else None,
                    "tax_policy_version": line.tax_policy_version,
                    "rate_basis_points": line.rate_basis_points,
                }
                for line in pricing.lines
            ],
        }

    @staticmethod
    def _tax_data(snapshot: PriceBookCommercialSnapshot) -> Mapping[str, object]:
        value = snapshot.snapshot_data.get("tax_classification")
        return value if isinstance(value, dict) else {}


estimate_service = EstimateService()
