from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.inventory.models import InventoryQuantity
from app.inventory.schemas import (
    MaterialCostEvidenceResponse,
    MaterialCostReadinessResponse,
    MaterialValuationReadinessResponse,
)
from app.platform.permissions.authorization import AuthorizationContext
from app.purchasing.models import (
    OperationalVendor,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderReceipt,
    PurchaseOrderReceiptLine,
)


class MaterialCostingService:
    async def readiness(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
    ) -> MaterialCostReadinessResponse:
        branches = tuple(context.authorized_branch_ids)
        receipt_rows = (
            (
                await session.execute(
                    select(
                        PurchaseOrderLine.inventory_item_id,
                        PurchaseOrderReceipt.vendor_id,
                        OperationalVendor.display_name,
                        PurchaseOrder.id,
                        PurchaseOrderLine.id,
                        PurchaseOrderReceipt.id,
                        PurchaseOrderReceiptLine.id,
                        PurchaseOrderReceipt.received_at,
                        PurchaseOrderReceipt.effective_date,
                        PurchaseOrderReceiptLine.accepted_quantity,
                        PurchaseOrderReceiptLine.unit_snapshot,
                        PurchaseOrderReceiptLine.unit_cost_snapshot,
                        PurchaseOrderReceiptLine.currency_snapshot,
                        PurchaseOrderReceipt.source_reference,
                    )
                    .join(
                        PurchaseOrderReceiptLine,
                        PurchaseOrderReceiptLine.purchase_order_line_id
                        == PurchaseOrderLine.id,
                    )
                    .join(
                        PurchaseOrderReceipt,
                        PurchaseOrderReceipt.id == PurchaseOrderReceiptLine.receipt_id,
                    )
                    .join(
                        PurchaseOrder,
                        PurchaseOrder.id == PurchaseOrderLine.purchase_order_id,
                    )
                    .join(
                        OperationalVendor,
                        OperationalVendor.id == PurchaseOrderReceipt.vendor_id,
                    )
                    .where(
                        PurchaseOrderLine.company_id == context.company.id,
                        PurchaseOrder.company_id == context.company.id,
                        PurchaseOrderReceipt.company_id == context.company.id,
                        PurchaseOrderReceiptLine.company_id == context.company.id,
                        OperationalVendor.company_id == context.company.id,
                        PurchaseOrderReceipt.branch_id.in_(branches),
                        PurchaseOrderLine.inventory_item_id.is_not(None),
                        PurchaseOrderReceiptLine.accepted_quantity > 0,
                        PurchaseOrderReceiptLine.unit_cost_snapshot.is_not(None),
                        PurchaseOrderReceiptLine.currency_snapshot.is_not(None),
                    )
                    .order_by(
                        PurchaseOrderReceipt.received_at.desc(),
                        PurchaseOrderReceiptLine.id,
                    )
                )
            ).all()
            if branches
            else []
        )
        evidence = tuple(
            MaterialCostEvidenceResponse(
                inventory_item_id=row[0],
                vendor_id=row[1],
                vendor_name=row[2],
                purchase_order_id=row[3],
                purchase_order_line_id=row[4],
                receipt_id=row[5],
                receipt_line_id=row[6],
                received_at=row[7],
                effective_date=row[8],
                accepted_quantity=row[9],
                unit=row[10],
                unit_cost=row[11],
                currency=row[12],
                source_reference=row[13],
            )
            for row in receipt_rows
        )
        costs_by_item: dict[UUID, list[MaterialCostEvidenceResponse]] = defaultdict(
            list
        )
        for row in evidence:
            costs_by_item[row.inventory_item_id].append(row)
        quantity_rows = (
            (
                await session.execute(
                    select(InventoryQuantity.item_id, InventoryQuantity.on_hand).where(
                        InventoryQuantity.company_id == context.company.id,
                        InventoryQuantity.branch_id.in_(branches),
                    )
                )
            ).all()
            if branches
            else []
        )
        on_hand_by_item: dict[UUID, Decimal] = defaultdict(Decimal)
        for item_id, quantity in quantity_rows:
            on_hand_by_item[item_id] += Decimal(quantity)
        item_ids = set(on_hand_by_item) | set(costs_by_item)
        readiness: list[MaterialValuationReadinessResponse] = []
        for item_id in sorted(item_ids, key=str):
            costs = costs_by_item[item_id]
            currencies = tuple(sorted({row.currency for row in costs}))
            blockers: list[str] = []
            if on_hand_by_item[item_id] > 0 and not costs:
                blockers.append("UNVALUED_STOCK")
            if len(currencies) > 1:
                blockers.append("CURRENCY_MISMATCH")
            if on_hand_by_item[item_id] > 0:
                blockers.append("VALUATION_METHOD_POLICY_REQUIRED")
            readiness.append(
                MaterialValuationReadinessResponse(
                    inventory_item_id=item_id,
                    on_hand_quantity=on_hand_by_item[item_id],
                    actual_receipt_cost_available=bool(costs),
                    currencies=currencies,
                    readiness_state="READY"
                    if not blockers
                    else "POLICY_OR_SOURCE_REQUIRED",
                    blockers=tuple(blockers),
                )
            )
        return MaterialCostReadinessResponse(
            evidence=evidence, readiness=tuple(readiness)
        )


material_costing_service = MaterialCostingService()
