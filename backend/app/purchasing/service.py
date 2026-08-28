import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.inventory.models import InventoryItem
from app.platform.permissions.authorization import AuthorizationContext

from .errors import PurchasingConflict, PurchasingNotFound, PurchasingValidation
from .models import (
    OperationalVendor,
    PurchaseOrder,
    PurchaseOrderIssuanceEvidence,
    PurchaseOrderLine,
    PurchasingCommandReceipt,
)
from .repository import PurchasingRepository, purchasing_repository
from .schemas import (
    PurchaseOrderCreate,
    PurchaseOrderItem,
    PurchaseOrderLineItem,
    PurchaseOrderLineUpdate,
    PurchaseOrderLineWrite,
    PurchaseOrderUpdate,
    PurchasingWorkspace,
    TransitionCommand,
    VendorCreate,
    VendorItem,
    VendorUpdate,
)


def now() -> datetime:
    return datetime.now(timezone.utc)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class PurchasingService:
    def __init__(self, repository: PurchasingRepository | None = None) -> None:
        self.repository = repository or purchasing_repository

    @staticmethod
    def branch(context: AuthorizationContext, branch_id: UUID) -> None:
        if not context.can_access_branch(branch_id):
            raise PurchasingNotFound("Purchasing Branch was not found")

    async def workspace(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        search: str | None = None,
    ) -> PurchasingWorkspace:
        vendors = await self.repository.vendors(session, context.company.id, search)
        orders = await self.repository.purchase_orders(
            session, context.company.id, tuple(context.authorized_branch_ids)
        )
        return PurchasingWorkspace(
            vendors=tuple(VendorItem.model_validate(vendor) for vendor in vendors),
            purchase_orders=tuple(
                [await self._item(session, order) for order in orders]
            ),
        )

    async def get_order(
        self, session: AsyncSession, *, context: AuthorizationContext, po_id: UUID
    ) -> PurchaseOrderItem:
        order = await self._order(session, context, po_id)
        return await self._item(session, order)

    async def create_vendor(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        payload: VendorCreate,
    ) -> OperationalVendor:
        data = payload.model_dump(mode="json")
        async with session.begin():
            replay = await self._replay(
                session,
                context,
                "vendor.create",
                payload.idempotency_key,
                data,
                "vendor",
            )
            if replay:
                record = await self.repository.vendor(
                    session, context.company.id, replay
                )
                if record is None:
                    raise PurchasingConflict("Vendor replay target is missing")
                return record
            record = OperationalVendor(
                company_id=context.company.id,
                code=payload.code.strip().upper(),
                display_name=payload.display_name.strip(),
                legal_name=payload.legal_name,
                contact_reference=payload.contact_reference,
                provenance_reference=payload.provenance_reference,
                created_by_user_id=context.user.id,
            )
            session.add(record)
            await session.flush()
            self._receipt(
                session,
                context,
                "vendor.create",
                payload.idempotency_key,
                data,
                "vendor",
                record.id,
            )
            self._event(
                session,
                context,
                EventType.PURCHASING_VENDOR_CREATED,
                "purchasing_vendor",
                record.id,
                None,
                {
                    "vendor_id": str(record.id),
                    "code": record.code,
                    "version": record.version,
                },
            )
        return record

    async def update_vendor(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        vendor_id: UUID,
        payload: VendorUpdate,
    ) -> OperationalVendor:
        data = {"vendor_id": str(vendor_id), **payload.model_dump(mode="json")}
        async with session.begin():
            replay = await self._replay(
                session,
                context,
                "vendor.update",
                payload.idempotency_key,
                data,
                "vendor",
            )
            if replay:
                record = await self.repository.vendor(
                    session, context.company.id, replay
                )
                if record is None:
                    raise PurchasingConflict("Vendor replay target is missing")
                return record
            record = await self.repository.vendor(
                session, context.company.id, vendor_id, lock=True
            )
            if record is None:
                raise PurchasingNotFound("Operational Vendor was not found")
            if record.version != payload.expected_version:
                raise PurchasingConflict("Operational Vendor version is stale")
            if payload.status not in {"active", "inactive", "archived"}:
                raise PurchasingValidation("Unsupported Vendor status")
            (
                record.display_name,
                record.legal_name,
                record.contact_reference,
                record.status,
            ) = (
                payload.display_name.strip(),
                payload.legal_name,
                payload.contact_reference,
                payload.status,
            )
            record.version += 1
            record.updated_at = now()
            self._receipt(
                session,
                context,
                "vendor.update",
                payload.idempotency_key,
                data,
                "vendor",
                record.id,
            )
            self._event(
                session,
                context,
                EventType.PURCHASING_VENDOR_UPDATED,
                "purchasing_vendor",
                record.id,
                None,
                {
                    "vendor_id": str(record.id),
                    "status": record.status,
                    "version": record.version,
                },
            )
        return record

    async def create_order(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        payload: PurchaseOrderCreate,
    ) -> PurchaseOrder:
        self.branch(context, payload.branch_id)
        data = payload.model_dump(mode="json")
        async with session.begin():
            replay = await self._replay(
                session,
                context,
                "po.create",
                payload.idempotency_key,
                data,
                "purchase_order",
            )
            if replay:
                record = await self.repository.purchase_order(
                    session, context.company.id, replay
                )
                if record is None:
                    raise PurchasingConflict("PO replay target is missing")
                return record
            vendor = await self.repository.vendor(
                session, context.company.id, payload.vendor_id
            )
            if vendor is None or vendor.status != "active":
                raise PurchasingValidation("Active operational Vendor is required")
            record = PurchaseOrder(
                company_id=context.company.id,
                branch_id=payload.branch_id,
                vendor_id=vendor.id,
                po_number=payload.po_number.strip().upper(),
                currency=payload.currency,
                expected_date=payload.expected_date,
                prepared_by_user_id=context.user.id,
            )
            session.add(record)
            await session.flush()
            self._receipt(
                session,
                context,
                "po.create",
                payload.idempotency_key,
                data,
                "purchase_order",
                record.id,
            )
            self._event(
                session,
                context,
                EventType.PURCHASING_PURCHASE_ORDER_CREATED,
                "purchase_order",
                record.id,
                record.branch_id,
                {
                    "purchase_order_id": str(record.id),
                    "vendor_id": str(record.vendor_id),
                    "status": record.status,
                    "version": record.version,
                },
            )
        return record

    async def update_order(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        po_id: UUID,
        payload: PurchaseOrderUpdate,
    ) -> PurchaseOrder:
        data = {"po_id": str(po_id), **payload.model_dump(mode="json")}
        async with session.begin():
            replay = await self._replay(
                session,
                context,
                "po.update",
                payload.idempotency_key,
                data,
                "purchase_order",
            )
            if replay:
                record = await self.repository.purchase_order(
                    session, context.company.id, replay
                )
                if record is None:
                    raise PurchasingConflict("PO replay target is missing")
                return record
            record = await self._order(session, context, po_id, lock=True)
            self._draft(record, payload.expected_version)
            vendor = await self.repository.vendor(
                session, context.company.id, payload.vendor_id
            )
            if vendor is None or vendor.status != "active":
                raise PurchasingValidation("Active operational Vendor is required")
            record.vendor_id, record.expected_date = vendor.id, payload.expected_date
            record.version += 1
            record.updated_at = now()
            self._receipt(
                session,
                context,
                "po.update",
                payload.idempotency_key,
                data,
                "purchase_order",
                record.id,
            )
        return record

    async def add_line(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        po_id: UUID,
        payload: PurchaseOrderLineWrite,
    ) -> PurchaseOrderLine:
        data = {"po_id": str(po_id), **payload.model_dump(mode="json")}
        async with session.begin():
            replay = await self._replay(
                session,
                context,
                "po.line.add",
                payload.idempotency_key,
                data,
                "purchase_order_line",
            )
            if replay:
                line = await session.get(PurchaseOrderLine, replay)
                if line is None or line.company_id != context.company.id:
                    raise PurchasingConflict("Line replay target is missing")
                return line
            order = await self._order(session, context, po_id, lock=True)
            self._draft(order, payload.expected_po_version)
            await self._inventory_item(
                session, context.company.id, payload.inventory_item_id
            )
            line = PurchaseOrderLine(
                company_id=context.company.id,
                purchase_order_id=order.id,
                line_number=await self.repository.next_line_number(
                    session, context.company.id, order.id
                ),
                inventory_item_id=payload.inventory_item_id,
                description=payload.description.strip(),
                quantity=payload.quantity,
                unit=payload.unit.strip(),
                unit_cost=payload.unit_cost,
                extended_cost=payload.quantity * payload.unit_cost,
                expected_date=payload.expected_date,
                created_by_user_id=context.user.id,
            )
            session.add(line)
            order.version += 1
            order.updated_at = now()
            await session.flush()
            self._receipt(
                session,
                context,
                "po.line.add",
                payload.idempotency_key,
                data,
                "purchase_order_line",
                line.id,
            )
        return line

    async def update_line(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        po_id: UUID,
        line_id: UUID,
        payload: PurchaseOrderLineUpdate,
    ) -> PurchaseOrderLine:
        data = {
            "po_id": str(po_id),
            "line_id": str(line_id),
            **payload.model_dump(mode="json"),
        }
        async with session.begin():
            replay = await self._replay(
                session,
                context,
                "po.line.update",
                payload.idempotency_key,
                data,
                "purchase_order_line",
            )
            if replay:
                line = await session.get(PurchaseOrderLine, replay)
                if line is None or line.company_id != context.company.id:
                    raise PurchasingConflict("Line replay target is missing")
                return line
            order = await self._order(session, context, po_id, lock=True)
            self._draft(order, payload.expected_po_version)
            line = await self.repository.line(
                session, context.company.id, po_id, line_id, lock=True
            )
            if line is None:
                raise PurchasingNotFound("Purchase Order line was not found")
            if line.version != payload.expected_line_version:
                raise PurchasingConflict("Purchase Order line version is stale")
            await self._inventory_item(
                session, context.company.id, payload.inventory_item_id
            )
            (
                line.inventory_item_id,
                line.description,
                line.quantity,
                line.unit,
                line.unit_cost,
                line.extended_cost,
                line.expected_date,
            ) = (
                payload.inventory_item_id,
                payload.description.strip(),
                payload.quantity,
                payload.unit.strip(),
                payload.unit_cost,
                payload.quantity * payload.unit_cost,
                payload.expected_date,
            )
            line.version += 1
            line.updated_at = now()
            order.version += 1
            order.updated_at = now()
            self._receipt(
                session,
                context,
                "po.line.update",
                payload.idempotency_key,
                data,
                "purchase_order_line",
                line.id,
            )
        return line

    async def transition(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        po_id: UUID,
        target: str,
        payload: TransitionCommand,
    ) -> PurchaseOrder:
        data = {
            "po_id": str(po_id),
            "target": target,
            **payload.model_dump(mode="json"),
        }
        operation = f"po.{target}"
        async with session.begin():
            replay = await self._replay(
                session,
                context,
                operation,
                payload.idempotency_key,
                data,
                "purchase_order",
            )
            if replay:
                record = await self.repository.purchase_order(
                    session, context.company.id, replay
                )
                if record is None:
                    raise PurchasingConflict("PO replay target is missing")
                return record
            order = await self._order(session, context, po_id, lock=True)
            if order.version != payload.expected_version:
                raise PurchasingConflict("Purchase Order version is stale")
            lines = await self.repository.lines(session, context.company.id, order.id)
            timestamp = now()
            if target == "submit":
                if order.status != "draft" or not lines:
                    raise PurchasingValidation("Only a nonempty draft may be submitted")
                order.status, order.submitted_by_user_id, order.submitted_at = (
                    "submitted",
                    context.user.id,
                    timestamp,
                )
            elif target == "approve":
                if order.status != "submitted":
                    raise PurchasingValidation("Only a submitted PO may be approved")
                if order.prepared_by_user_id == context.user.id:
                    raise PurchasingValidation("PO preparer cannot approve the same PO")
                order.status, order.approved_by_user_id, order.approved_at = (
                    "approved",
                    context.user.id,
                    timestamp,
                )
            elif target == "issue":
                if order.status != "approved":
                    raise PurchasingValidation("Only an approved PO may be issued")
                vendor = await self.repository.vendor(
                    session, context.company.id, order.vendor_id
                )
                if vendor is None:
                    raise PurchasingConflict("Operational Vendor is missing")
                snapshot = self._snapshot(
                    order, vendor, lines, timestamp, context.user.id
                )
                evidence = PurchaseOrderIssuanceEvidence(
                    company_id=order.company_id,
                    branch_id=order.branch_id,
                    purchase_order_id=order.id,
                    purchase_order_version=order.version + 1,
                    digest=digest(snapshot),
                    snapshot=snapshot,
                    issued_by_user_id=context.user.id,
                    issued_at=timestamp,
                )
                session.add(evidence)
                order.status, order.issued_by_user_id, order.issued_at = (
                    "issued",
                    context.user.id,
                    timestamp,
                )
            elif target == "cancel":
                if order.status not in {"draft", "submitted", "approved", "issued"}:
                    raise PurchasingValidation(
                        "Purchase Order cannot be cancelled from current state"
                    )
                if not payload.reason:
                    raise PurchasingValidation("Cancellation reason is required")
                order.status, order.lifecycle_reason = (
                    "cancelled",
                    payload.reason.strip(),
                )
            elif target == "close":
                if order.status != "issued":
                    raise PurchasingValidation(
                        "Only an issued PO may be manually closed in PUR.1"
                    )
                if not payload.reason:
                    raise PurchasingValidation("Non-receipt closure reason is required")
                (
                    order.status,
                    order.closed_by_user_id,
                    order.closed_at,
                    order.lifecycle_reason,
                ) = "closed", context.user.id, timestamp, payload.reason.strip()
            else:
                raise PurchasingValidation("Unsupported Purchase Order transition")
            order.version += 1
            order.updated_at = timestamp
            self._receipt(
                session,
                context,
                operation,
                payload.idempotency_key,
                data,
                "purchase_order",
                order.id,
            )
            event_type = {
                "submit": EventType.PURCHASING_PURCHASE_ORDER_SUBMITTED,
                "approve": EventType.PURCHASING_PURCHASE_ORDER_APPROVED,
                "issue": EventType.PURCHASING_PURCHASE_ORDER_ISSUED,
                "cancel": EventType.PURCHASING_PURCHASE_ORDER_CANCELLED,
                "close": EventType.PURCHASING_PURCHASE_ORDER_CLOSED,
            }[target]
            payload_data: dict[str, object] = {
                "purchase_order_id": str(order.id),
                "status": order.status,
                "version": order.version,
            }
            if target == "issue":
                payload_data["issuance_digest"] = evidence.digest
            self._event(
                session,
                context,
                event_type,
                "purchase_order",
                order.id,
                order.branch_id,
                payload_data,
            )
        return order

    async def _order(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        po_id: UUID,
        *,
        lock: bool = False,
    ) -> PurchaseOrder:
        order = await self.repository.purchase_order(
            session, context.company.id, po_id, lock=lock
        )
        if order is None:
            raise PurchasingNotFound("Purchase Order was not found")
        self.branch(context, order.branch_id)
        return order

    async def _item(
        self, session: AsyncSession, order: PurchaseOrder
    ) -> PurchaseOrderItem:
        lines = await self.repository.lines(session, order.company_id, order.id)
        evidence = await self.repository.evidence(session, order.company_id, order.id)
        return PurchaseOrderItem.model_validate(order).model_copy(
            update={
                "lines": tuple(
                    PurchaseOrderLineItem.model_validate(line) for line in lines
                ),
                "issuance_digest": evidence.digest if evidence else None,
            }
        )

    @staticmethod
    def _draft(order: PurchaseOrder, expected_version: int) -> None:
        if order.status != "draft":
            raise PurchasingValidation("Only a draft Purchase Order may be edited")
        if order.version != expected_version:
            raise PurchasingConflict("Purchase Order version is stale")

    @staticmethod
    async def _inventory_item(
        session: AsyncSession, company_id: UUID, item_id: UUID | None
    ) -> None:
        if item_id is None:
            return
        exists = await session.scalar(
            select(InventoryItem.id).where(
                InventoryItem.company_id == company_id, InventoryItem.id == item_id
            )
        )
        if exists is None:
            raise PurchasingValidation("Inventory item reference is invalid")

    async def _replay(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        operation: str,
        key: str,
        data: dict[str, Any],
        result_type: str,
    ) -> UUID | None:
        receipt = await self.repository.receipt(session, context.company.id, key)
        if receipt is None:
            return None
        if (
            receipt.operation != operation
            or receipt.result_type != result_type
            or receipt.payload_digest != digest(data)
        ):
            raise PurchasingConflict(
                "Idempotency key was already used with different command evidence"
            )
        return receipt.result_id

    @staticmethod
    def _receipt(
        session: AsyncSession,
        context: AuthorizationContext,
        operation: str,
        key: str,
        data: dict[str, Any],
        result_type: str,
        result_id: UUID,
    ) -> None:
        session.add(
            PurchasingCommandReceipt(
                company_id=context.company.id,
                operation=operation,
                idempotency_key=key,
                payload_digest=digest(data),
                result_type=result_type,
                result_id=result_id,
                actor_user_id=context.user.id,
            )
        )

    @staticmethod
    def _snapshot(
        order: PurchaseOrder,
        vendor: OperationalVendor,
        lines: tuple[PurchaseOrderLine, ...],
        issued_at: datetime,
        issuer: UUID,
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "company_id": str(order.company_id),
            "branch_id": str(order.branch_id),
            "purchase_order_id": str(order.id),
            "po_number": order.po_number,
            "currency": order.currency,
            "expected_date": order.expected_date.isoformat()
            if order.expected_date
            else None,
            "vendor": {
                "id": str(vendor.id),
                "version": vendor.version,
                "code": vendor.code,
                "display_name": vendor.display_name,
                "legal_name": vendor.legal_name,
                "contact_reference": vendor.contact_reference,
            },
            "lines": [
                {
                    "id": str(line.id),
                    "line_number": line.line_number,
                    "inventory_item_id": str(line.inventory_item_id)
                    if line.inventory_item_id
                    else None,
                    "description": line.description,
                    "quantity": str(line.quantity),
                    "unit": line.unit,
                    "unit_cost": str(line.unit_cost),
                    "extended_cost": str(line.extended_cost),
                    "expected_date": line.expected_date.isoformat()
                    if line.expected_date
                    else None,
                }
                for line in lines
            ],
            "approved_by_user_id": str(order.approved_by_user_id),
            "issued_by_user_id": str(issuer),
            "issued_at": issued_at.isoformat(),
        }

    @staticmethod
    def _event(
        session: AsyncSession,
        context: AuthorizationContext,
        event_type: EventType,
        entity_type: str,
        entity_id: UUID,
        branch_id: UUID | None,
        payload: dict[str, object],
    ) -> None:
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                company_id=context.company.id,
                branch_id=branch_id,
                user_id=context.user.id,
                payload=payload,
            ),
        )


purchasing_service = PurchasingService()
