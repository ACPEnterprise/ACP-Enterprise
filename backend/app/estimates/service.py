from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.estimates.contracts import CreateEstimateSpec, EstimateRecord
from app.estimates.errors import EstimateConflictError, EstimateValidationError
from app.estimates.models import (
    Estimate,
    EstimateCommercialSnapshotReference,
    EstimateLifecycleHistory,
    EstimateLineItem,
    EstimateRevision,
)
from app.estimates.repository import EstimateRepository
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType


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


estimate_service = EstimateService()
