from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.models import Customer, ServiceLocation
from app.estimates.contracts import (
    EstimateConversionRecord,
    EstimateCustomerDecisionRecord,
    EstimateLineRecord,
    EstimateRecord,
    EstimateRevisionRecord,
)
from app.estimates.models import (
    Estimate,
    EstimateCommercialSnapshotReference,
    EstimateCustomerDecision,
    EstimateJobConversion,
    EstimateLifecycleHistory,
    EstimateLineItem,
    EstimateNumberSequence,
    EstimateRevision,
)
from app.estimates.schemas import EstimateSummary
from app.price_book.models import PriceBookCommercialSnapshot


class EstimateRepository:
    """Company-scoped Estimate persistence; Price Book snapshots remain authoritative."""

    @staticmethod
    async def list_summaries(
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_ids: frozenset[UUID],
        customer_id: UUID | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> tuple[EstimateSummary, ...]:
        statement = (
            select(Estimate, EstimateRevision)
            .join(
                EstimateRevision,
                (EstimateRevision.company_id == Estimate.company_id)
                & (EstimateRevision.id == Estimate.current_revision_id),
            )
            .where(
                Estimate.company_id == company_id,
                Estimate.branch_id.in_(branch_ids),
            )
        )
        if customer_id is not None:
            statement = statement.where(Estimate.customer_id == customer_id)
        if status is not None:
            statement = statement.where(Estimate.status == status)
        rows = (
            await session.execute(
                statement.order_by(Estimate.updated_at.desc(), Estimate.id).limit(limit)
            )
        ).all()
        return tuple(
            EstimateSummary(
                id=estimate.id,
                branch_id=estimate.branch_id,
                customer_id=estimate.customer_id,
                service_location_id=estimate.service_location_id,
                estimate_number=estimate.estimate_number,
                status=estimate.status,
                acceptance_status=estimate.acceptance_status,
                version=estimate.version,
                proposal_title=revision.proposal_title,
                currency=revision.currency,
                total_amount=revision.total_amount,
                expires_at=revision.expires_at,
                updated_at=estimate.updated_at,
            )
            for estimate, revision in rows
        )

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
                option_group_id=ref.option_group_id,
                option_id=ref.option_id,
                discount_allocation=line.discount_allocation,
                discounted_basis=line.discounted_basis,
                tax_amount=line.tax_amount,
                taxable=line.taxable,
                currency=line.currency,
            )
            for line, ref in rows
        )
        revision_record = EstimateRevisionRecord(
            id=revision.id,
            parent_revision_id=revision.parent_revision_id,
            revision_number=revision.revision_number,
            status=revision.status,
            proposal_title=revision.proposal_title,
            customer_message=revision.customer_message,
            terms=revision.terms,
            currency=revision.currency,
            subtotal_amount=revision.subtotal_amount,
            discount_type=revision.discount_type,
            discount_value=revision.discount_value,
            discount_amount=revision.discount_amount,
            taxable_basis=revision.taxable_basis,
            tax_amount=revision.tax_amount,
            total_amount=revision.total_amount,
            expires_at=revision.expires_at,
            created_at=revision.created_at,
            lines=line_records,
        )
        decision = await session.scalar(
            select(EstimateCustomerDecision).where(
                EstimateCustomerDecision.company_id == company_id,
                EstimateCustomerDecision.revision_id == revision.id,
            )
        )
        decision_record = (
            EstimateCustomerDecisionRecord(
                id=decision.id,
                revision_id=decision.revision_id,
                decision=decision.decision,
                customer_name=decision.customer_name,
                customer_email=decision.customer_email,
                customer_comment=decision.customer_comment,
                rejection_reason=decision.rejection_reason,
                evidence_reference=decision.evidence_reference,
                occurred_at=decision.occurred_at,
            )
            if decision is not None
            else None
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
            customer_decision=decision_record,
        )

    @staticmethod
    async def get_for_update(
        session: AsyncSession, *, company_id: UUID, estimate_id: UUID
    ) -> Estimate | None:
        return await session.scalar(
            select(Estimate)
            .where(
                Estimate.company_id == company_id,
                Estimate.id == estimate_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    @staticmethod
    async def get_revision(
        session: AsyncSession, *, company_id: UUID, revision_id: UUID
    ) -> EstimateRevision | None:
        return await session.scalar(
            select(EstimateRevision).where(
                EstimateRevision.company_id == company_id,
                EstimateRevision.id == revision_id,
            )
        )

    @staticmethod
    async def add_revision(
        session: AsyncSession,
        *,
        estimate: Estimate,
        revision: EstimateRevision,
        lines: tuple[EstimateLineItem, ...],
        references: tuple[EstimateCommercialSnapshotReference, ...],
        history: EstimateLifecycleHistory,
    ) -> None:
        session.add(revision)
        await session.flush()
        session.add_all([*lines, history])
        await session.flush()
        session.add_all(references)
        estimate.current_revision_id = revision.id
        await session.flush()

    @staticmethod
    async def add_lifecycle_history(
        session: AsyncSession, *, history: EstimateLifecycleHistory
    ) -> None:
        session.add(history)
        await session.flush()

    @staticmethod
    async def add_customer_decision(
        session: AsyncSession, *, decision: EstimateCustomerDecision
    ) -> None:
        session.add(decision)
        await session.flush()

    @staticmethod
    async def list_revisions(
        session: AsyncSession, *, company_id: UUID, estimate_id: UUID
    ) -> tuple[EstimateRevision, ...]:
        rows = await session.scalars(
            select(EstimateRevision)
            .where(
                EstimateRevision.company_id == company_id,
                EstimateRevision.estimate_id == estimate_id,
            )
            .order_by(EstimateRevision.revision_number)
        )
        return tuple(rows.all())

    @staticmethod
    async def get_snapshot_lineage(
        session: AsyncSession, *, company_id: UUID, revision_id: UUID
    ) -> tuple[EstimateCommercialSnapshotReference, ...]:
        rows = await session.scalars(
            select(EstimateCommercialSnapshotReference)
            .where(
                EstimateCommercialSnapshotReference.company_id == company_id,
                EstimateCommercialSnapshotReference.revision_id == revision_id,
            )
            .order_by(EstimateCommercialSnapshotReference.line_item_id)
        )
        return tuple(rows.all())

    @staticmethod
    async def get_conversion(
        session: AsyncSession, *, company_id: UUID, estimate_id: UUID
    ) -> EstimateJobConversion | None:
        return await session.scalar(
            select(EstimateJobConversion).where(
                EstimateJobConversion.company_id == company_id,
                EstimateJobConversion.estimate_id == estimate_id,
            )
        )

    @staticmethod
    async def add_conversion(
        session: AsyncSession, *, conversion: EstimateJobConversion
    ) -> None:
        session.add(conversion)
        await session.flush()

    @staticmethod
    def conversion_record(
        conversion: EstimateJobConversion, *, job_number: str
    ) -> EstimateConversionRecord:
        return EstimateConversionRecord(
            id=conversion.id,
            company_id=conversion.company_id,
            branch_id=conversion.branch_id,
            estimate_id=conversion.estimate_id,
            estimate_revision_id=conversion.estimate_revision_id,
            job_id=conversion.job_id,
            job_number=job_number,
            estimate_version=conversion.estimate_version,
            snapshot_lineage_digest=conversion.snapshot_lineage_digest,
            idempotency_key=conversion.idempotency_key,
            converted_by_user_id=conversion.converted_by_user_id,
            converted_at=conversion.converted_at,
        )

    @staticmethod
    def snapshot_total(snapshots: tuple[PriceBookCommercialSnapshot, ...]) -> Decimal:
        return sum(
            (snapshot.extended_amount for snapshot in snapshots), start=Decimal("0.00")
        )
