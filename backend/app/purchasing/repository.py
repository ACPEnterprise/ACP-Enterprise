from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    OperationalVendor,
    PurchaseOrder,
    PurchaseOrderChangeOrder,
    PurchaseOrderDiscrepancy,
    PurchaseOrderDispositionEvidence,
    PurchaseOrderIssuanceEvidence,
    PurchaseOrderLine,
    PurchaseOrderReceipt,
    PurchaseOrderReceiptLine,
    PurchaseOrderRevision,
    PurchaseReturn,
    PurchasingCommandReceipt,
)


class PurchasingRepository:
    async def vendor(
        self,
        session: AsyncSession,
        company_id: UUID,
        vendor_id: UUID,
        *,
        lock: bool = False,
    ) -> OperationalVendor | None:
        query = select(OperationalVendor).where(
            OperationalVendor.company_id == company_id,
            OperationalVendor.id == vendor_id,
        )
        return await session.scalar(query.with_for_update() if lock else query)

    async def vendors(
        self, session: AsyncSession, company_id: UUID, search: str | None = None
    ) -> tuple[OperationalVendor, ...]:
        query: Select[tuple[OperationalVendor]] = select(OperationalVendor).where(
            OperationalVendor.company_id == company_id
        )
        if search:
            value = f"%{search.strip()}%"
            query = query.where(
                OperationalVendor.display_name.ilike(value)
                | OperationalVendor.code.ilike(value)
            )
        return tuple(
            (
                await session.scalars(query.order_by(OperationalVendor.display_name))
            ).all()
        )

    async def purchase_order(
        self,
        session: AsyncSession,
        company_id: UUID,
        po_id: UUID,
        *,
        lock: bool = False,
    ) -> PurchaseOrder | None:
        query = select(PurchaseOrder).where(
            PurchaseOrder.company_id == company_id, PurchaseOrder.id == po_id
        )
        return await session.scalar(query.with_for_update() if lock else query)

    async def purchase_orders(
        self, session: AsyncSession, company_id: UUID, branch_ids: tuple[UUID, ...]
    ) -> tuple[PurchaseOrder, ...]:
        return tuple(
            (
                await session.scalars(
                    select(PurchaseOrder)
                    .where(
                        PurchaseOrder.company_id == company_id,
                        PurchaseOrder.branch_id.in_(branch_ids),
                    )
                    .order_by(PurchaseOrder.created_at.desc())
                )
            ).all()
        )

    async def purchase_orders_for_vendor(
        self,
        session: AsyncSession,
        company_id: UUID,
        vendor_id: UUID,
        branch_ids: tuple[UUID, ...],
    ) -> tuple[PurchaseOrder, ...]:
        return tuple(
            (
                await session.scalars(
                    select(PurchaseOrder)
                    .where(
                        PurchaseOrder.company_id == company_id,
                        PurchaseOrder.vendor_id == vendor_id,
                        PurchaseOrder.branch_id.in_(branch_ids),
                    )
                    .order_by(PurchaseOrder.issued_at, PurchaseOrder.id)
                )
            ).all()
        )

    async def lines(
        self, session: AsyncSession, company_id: UUID, po_id: UUID
    ) -> tuple[PurchaseOrderLine, ...]:
        return tuple(
            (
                await session.scalars(
                    select(PurchaseOrderLine)
                    .where(
                        PurchaseOrderLine.company_id == company_id,
                        PurchaseOrderLine.purchase_order_id == po_id,
                    )
                    .order_by(PurchaseOrderLine.line_number)
                )
            ).all()
        )

    async def line(
        self,
        session: AsyncSession,
        company_id: UUID,
        po_id: UUID,
        line_id: UUID,
        *,
        lock: bool = False,
    ) -> PurchaseOrderLine | None:
        query = select(PurchaseOrderLine).where(
            PurchaseOrderLine.company_id == company_id,
            PurchaseOrderLine.purchase_order_id == po_id,
            PurchaseOrderLine.id == line_id,
        )
        return await session.scalar(query.with_for_update() if lock else query)

    async def next_line_number(
        self, session: AsyncSession, company_id: UUID, po_id: UUID
    ) -> int:
        current = await session.scalar(
            select(func.max(PurchaseOrderLine.line_number)).where(
                PurchaseOrderLine.company_id == company_id,
                PurchaseOrderLine.purchase_order_id == po_id,
            )
        )
        return (current or 0) + 1

    async def evidence(
        self, session: AsyncSession, company_id: UUID, po_id: UUID
    ) -> PurchaseOrderIssuanceEvidence | None:
        return await session.scalar(
            select(PurchaseOrderIssuanceEvidence).where(
                PurchaseOrderIssuanceEvidence.company_id == company_id,
                PurchaseOrderIssuanceEvidence.purchase_order_id == po_id,
            )
        )

    async def receipt(
        self, session: AsyncSession, company_id: UUID, key: str
    ) -> PurchasingCommandReceipt | None:
        return await session.scalar(
            select(PurchasingCommandReceipt).where(
                PurchasingCommandReceipt.company_id == company_id,
                PurchasingCommandReceipt.idempotency_key == key,
            )
        )

    async def receiving_events(
        self, session: AsyncSession, company_id: UUID, po_id: UUID
    ) -> tuple[PurchaseOrderReceipt, ...]:
        return tuple(
            (
                await session.scalars(
                    select(PurchaseOrderReceipt)
                    .where(
                        PurchaseOrderReceipt.company_id == company_id,
                        PurchaseOrderReceipt.purchase_order_id == po_id,
                    )
                    .order_by(PurchaseOrderReceipt.received_at, PurchaseOrderReceipt.id)
                )
            ).all()
        )

    async def receiving_event(
        self, session: AsyncSession, company_id: UUID, receipt_id: UUID
    ) -> PurchaseOrderReceipt | None:
        return await session.scalar(
            select(PurchaseOrderReceipt).where(
                PurchaseOrderReceipt.company_id == company_id,
                PurchaseOrderReceipt.id == receipt_id,
            )
        )

    async def receipt_lines(
        self, session: AsyncSession, company_id: UUID, receipt_id: UUID
    ) -> tuple[PurchaseOrderReceiptLine, ...]:
        return tuple(
            (
                await session.scalars(
                    select(PurchaseOrderReceiptLine)
                    .where(
                        PurchaseOrderReceiptLine.company_id == company_id,
                        PurchaseOrderReceiptLine.receipt_id == receipt_id,
                    )
                    .order_by(PurchaseOrderReceiptLine.purchase_order_line_id)
                )
            ).all()
        )

    async def accepted_totals(
        self, session: AsyncSession, company_id: UUID, po_id: UUID
    ) -> dict[UUID, Decimal]:
        rows = (
            await session.execute(
                select(
                    PurchaseOrderReceiptLine.purchase_order_line_id,
                    func.coalesce(
                        func.sum(PurchaseOrderReceiptLine.accepted_quantity), 0
                    ),
                )
                .join(
                    PurchaseOrderReceipt,
                    PurchaseOrderReceipt.id == PurchaseOrderReceiptLine.receipt_id,
                )
                .where(
                    PurchaseOrderReceiptLine.company_id == company_id,
                    PurchaseOrderReceipt.purchase_order_id == po_id,
                )
                .group_by(PurchaseOrderReceiptLine.purchase_order_line_id)
            )
        ).all()
        return {line_id: total for line_id, total in rows}

    async def discrepancies(
        self, session: AsyncSession, company_id: UUID, po_id: UUID
    ) -> tuple[PurchaseOrderDiscrepancy, ...]:
        return tuple(
            (
                await session.scalars(
                    select(PurchaseOrderDiscrepancy)
                    .where(
                        PurchaseOrderDiscrepancy.company_id == company_id,
                        PurchaseOrderDiscrepancy.purchase_order_id == po_id,
                    )
                    .order_by(
                        PurchaseOrderDiscrepancy.opened_at, PurchaseOrderDiscrepancy.id
                    )
                )
            ).all()
        )

    async def discrepancy(
        self,
        session: AsyncSession,
        company_id: UUID,
        discrepancy_id: UUID,
        *,
        lock: bool = False,
    ) -> PurchaseOrderDiscrepancy | None:
        query = select(PurchaseOrderDiscrepancy).where(
            PurchaseOrderDiscrepancy.company_id == company_id,
            PurchaseOrderDiscrepancy.id == discrepancy_id,
        )
        return await session.scalar(query.with_for_update() if lock else query)

    async def purchase_returns(
        self, session: AsyncSession, company_id: UUID, po_id: UUID
    ) -> tuple[PurchaseReturn, ...]:
        return tuple(
            (
                await session.scalars(
                    select(PurchaseReturn)
                    .where(
                        PurchaseReturn.company_id == company_id,
                        PurchaseReturn.purchase_order_id == po_id,
                    )
                    .order_by(PurchaseReturn.requested_at, PurchaseReturn.id)
                )
            ).all()
        )

    async def purchase_return(
        self,
        session: AsyncSession,
        company_id: UUID,
        return_id: UUID,
        *,
        lock: bool = False,
    ) -> PurchaseReturn | None:
        query = select(PurchaseReturn).where(
            PurchaseReturn.company_id == company_id, PurchaseReturn.id == return_id
        )
        return await session.scalar(query.with_for_update() if lock else query)

    async def committed_return_quantity(
        self, session: AsyncSession, company_id: UUID, receipt_line_id: UUID
    ) -> Decimal:
        value = await session.scalar(
            select(func.coalesce(func.sum(PurchaseReturn.quantity), 0)).where(
                PurchaseReturn.company_id == company_id,
                PurchaseReturn.receipt_line_id == receipt_line_id,
                PurchaseReturn.status != "canceled",
            )
        )
        return Decimal(value or 0)

    async def change_orders(
        self, session: AsyncSession, company_id: UUID, po_id: UUID
    ) -> tuple[PurchaseOrderChangeOrder, ...]:
        return tuple(
            (
                await session.scalars(
                    select(PurchaseOrderChangeOrder)
                    .where(
                        PurchaseOrderChangeOrder.company_id == company_id,
                        PurchaseOrderChangeOrder.purchase_order_id == po_id,
                    )
                    .order_by(
                        PurchaseOrderChangeOrder.requested_at,
                        PurchaseOrderChangeOrder.id,
                    )
                )
            ).all()
        )

    async def change_order(
        self,
        session: AsyncSession,
        company_id: UUID,
        change_id: UUID,
        *,
        lock: bool = False,
    ) -> PurchaseOrderChangeOrder | None:
        query = select(PurchaseOrderChangeOrder).where(
            PurchaseOrderChangeOrder.company_id == company_id,
            PurchaseOrderChangeOrder.id == change_id,
        )
        return await session.scalar(query.with_for_update() if lock else query)

    async def revisions(
        self, session: AsyncSession, company_id: UUID, po_id: UUID
    ) -> tuple[PurchaseOrderRevision, ...]:
        return tuple(
            (
                await session.scalars(
                    select(PurchaseOrderRevision)
                    .where(
                        PurchaseOrderRevision.company_id == company_id,
                        PurchaseOrderRevision.purchase_order_id == po_id,
                    )
                    .order_by(PurchaseOrderRevision.revision_number)
                )
            ).all()
        )

    async def disposition(
        self, session: AsyncSession, company_id: UUID, po_id: UUID
    ) -> PurchaseOrderDispositionEvidence | None:
        return await session.scalar(
            select(PurchaseOrderDispositionEvidence).where(
                PurchaseOrderDispositionEvidence.company_id == company_id,
                PurchaseOrderDispositionEvidence.purchase_order_id == po_id,
            )
        )


purchasing_repository = PurchasingRepository()
