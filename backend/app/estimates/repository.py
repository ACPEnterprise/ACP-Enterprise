from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.models import Customer, ServiceLocation
from app.estimates.contracts import (
    EstimateLineRecord,
    EstimateRecord,
    EstimateRevisionRecord,
)
from app.estimates.models import (
    Estimate,
    EstimateCommercialSnapshotReference,
    EstimateLifecycleHistory,
    EstimateLineItem,
    EstimateNumberSequence,
    EstimateRevision,
)
from app.price_book.models import PriceBookCommercialSnapshot


class EstimateRepository:
    """Company-scoped Estimate persistence; Price Book snapshots remain authoritative."""

    @staticmethod
    async def next_estimate_number(session: AsyncSession, *, company_id: UUID) -> str:
        statement = (
            insert(EstimateNumberSequence)
            .values(company_id=company_id, last_value=1)
            .on_conflict_do_update(
                index_elements=[EstimateNumberSequence.company_id],
                set_={
                    "last_value": EstimateNumberSequence.last_value + 1,
                    "updated_at": func.now(),
                },
            )
            .returning(EstimateNumberSequence.last_value)
        )
        value = await session.scalar(statement)
        if value is None:
            raise RuntimeError("Estimate number allocation failed")
        return f"EST-{value:06d}"

    @staticmethod
    async def customer_belongs_to_company(
        session: AsyncSession, *, company_id: UUID, customer_id: UUID
    ) -> bool:
        return bool(
            await session.scalar(
                select(Customer.id).where(
                    Customer.id == customer_id, Customer.company_id == company_id
                )
            )
        )

    @staticmethod
    async def location_belongs_to_customer(
        session: AsyncSession, *, customer_id: UUID, location_id: UUID
    ) -> bool:
        return bool(
            await session.scalar(
                select(ServiceLocation.id).where(
                    ServiceLocation.id == location_id,
                    ServiceLocation.customer_id == customer_id,
                )
            )
        )

    @staticmethod
    async def get_snapshots(
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        snapshot_ids: tuple[UUID, ...],
    ) -> tuple[PriceBookCommercialSnapshot, ...]:
        rows = await session.scalars(
            select(PriceBookCommercialSnapshot)
            .where(
                PriceBookCommercialSnapshot.company_id == company_id,
                PriceBookCommercialSnapshot.branch_id == branch_id,
                PriceBookCommercialSnapshot.id.in_(snapshot_ids),
            )
            .order_by(PriceBookCommercialSnapshot.id)
        )
        return tuple(rows.all())

    @staticmethod
    async def add_foundation(
        session: AsyncSession,
        *,
        estimate: Estimate,
        revision: EstimateRevision,
        lines: tuple[EstimateLineItem, ...],
        references: tuple[EstimateCommercialSnapshotReference, ...],
        history: EstimateLifecycleHistory,
    ) -> None:
        session.add(estimate)
        await session.flush()
        session.add(revision)
        await session.flush()
        estimate.current_revision_id = revision.id
        session.add_all([*lines, history])
        await session.flush()
        session.add_all(references)
        await session.flush()

    @staticmethod
    async def get(
        session: AsyncSession, *, company_id: UUID, estimate_id: UUID
    ) -> EstimateRecord | None:
        estimate = await session.scalar(
            select(Estimate)
            .where(Estimate.company_id == company_id, Estimate.id == estimate_id)
            .execution_options(populate_existing=True)
        )
        if estimate is None or estimate.current_revision_id is None:
            return None
        revision = await session.scalar(
            select(EstimateRevision).where(
                EstimateRevision.company_id == company_id,
                EstimateRevision.id == estimate.current_revision_id,
            )
        )
        if revision is None:
            return None
        rows = (
            await session.execute(
                select(EstimateLineItem, EstimateCommercialSnapshotReference)
                .join(
                    EstimateCommercialSnapshotReference,
                    (
                        EstimateCommercialSnapshotReference.company_id
                        == EstimateLineItem.company_id
                    )
                    & (
                        EstimateCommercialSnapshotReference.line_item_id
                        == EstimateLineItem.id
                    ),
                )
                .where(
                    EstimateLineItem.company_id == company_id,
                    EstimateLineItem.revision_id == revision.id,
                )
                .order_by(EstimateLineItem.position)
            )
        ).all()
        line_records = tuple(
            EstimateLineRecord(
                id=line.id,
                position=line.position,
                title=line.title,
                description=line.description,
                snapshot_id=ref.snapshot_id,
                snapshot_digest=ref.snapshot_digest,
                quantity=line.quantity,
                unit_price=line.unit_price,
                line_total=line.line_total,
                currency=line.currency,
            )
            for line, ref in rows
        )
        revision_record = EstimateRevisionRecord(
            id=revision.id,
            revision_number=revision.revision_number,
            status=revision.status,
            proposal_title=revision.proposal_title,
            customer_message=revision.customer_message,
            terms=revision.terms,
            currency=revision.currency,
            subtotal_amount=revision.subtotal_amount,
            total_amount=revision.total_amount,
            expires_at=revision.expires_at,
            created_at=revision.created_at,
            lines=line_records,
        )
        return EstimateRecord(
            id=estimate.id,
            company_id=estimate.company_id,
            branch_id=estimate.branch_id,
            customer_id=estimate.customer_id,
            service_location_id=estimate.service_location_id,
            estimate_number=estimate.estimate_number,
            status=estimate.status,
            acceptance_status=estimate.acceptance_status,
            version=estimate.version,
            current_revision=revision_record,
        )

    @staticmethod
    async def next_revision_number(
        session: AsyncSession, *, company_id: UUID, estimate_id: UUID
    ) -> int:
        value = await session.scalar(
            select(func.coalesce(func.max(EstimateRevision.revision_number), 0))
            .where(
                EstimateRevision.company_id == company_id,
                EstimateRevision.estimate_id == estimate_id,
            )
            .with_for_update()
        )
        return int(value or 0) + 1

    @staticmethod
    def snapshot_total(snapshots: tuple[PriceBookCommercialSnapshot, ...]) -> Decimal:
        return sum(
            (snapshot.extended_amount for snapshot in snapshots), start=Decimal("0.00")
        )
