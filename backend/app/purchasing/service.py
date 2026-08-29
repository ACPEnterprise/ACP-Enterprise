import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.inventory.models import InventoryItem, InventoryQuantity
from app.platform.permissions.authorization import AuthorizationContext

from .errors import PurchasingConflict, PurchasingNotFound, PurchasingValidation
from .models import (
    BranchPurchasingPolicy,
    BranchPurchasingPolicyRevision,
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
    ReplenishmentDecisionEvidence,
)
from .repository import PurchasingRepository, purchasing_repository
from .schemas import (
    BranchPurchasingPolicyItem,
    BranchPurchasingPolicyRevisionItem,
    BranchPurchasingPolicyWrite,
    CreatePurchaseReturnCommand,
    DecidePurchaseOrderChangeCommand,
    DiscrepancyItem,
    PurchaseOrderChangeItem,
    PurchaseOrderCreate,
    PurchaseOrderDispositionCommand,
    PurchaseOrderDispositionItem,
    PurchaseOrderItem,
    PurchaseOrderLineItem,
    PurchaseOrderLineUpdate,
    PurchaseOrderLineWrite,
    PurchaseOrderRevisionItem,
    PurchaseOrderUpdate,
    PurchaseReturnItem,
    PurchaseReturnTransitionCommand,
    PurchasingWorkspace,
    ReceiptItem,
    ReceiptLineItem,
    RecordReceiptCommand,
    ReplenishmentDecisionCommand,
    ReplenishmentDecisionItem,
    ReplenishmentRecommendation,
    ReplenishmentTarget,
    ReplenishmentWorkbench,
    ReplenishmentWorkbenchRequest,
    RequestPurchaseOrderChangeCommand,
    ResolveDiscrepancyCommand,
    TransitionCommand,
    VendorCreate,
    VendorItem,
    VendorPerformanceEvidence,
    VendorPerformanceEvidenceReport,
    VendorPerformanceSummary,
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

    async def branch_policies(
        self, session: AsyncSession, *, context: AuthorizationContext
    ) -> tuple[BranchPurchasingPolicyItem, ...]:
        policies = await self.repository.branch_policies(
            session, context.company.id, tuple(context.authorized_branch_ids)
        )
        return tuple(
            [await self._branch_policy_item(session, item) for item in policies]
        )

    async def configure_branch_policy(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        payload: BranchPurchasingPolicyWrite,
    ) -> BranchPurchasingPolicyItem:
        self.branch(context, payload.branch_id)
        data = payload.model_dump(mode="json", exclude={"idempotency_key"})
        payload_digest = digest(data)
        async with session.begin():
            if session.get_bind().dialect.name == "postgresql":
                lock_identities = sorted(
                    (
                        f"branch-policy:{context.company.id}:{payload.branch_id}:{payload.inventory_item_id}",
                        f"purchasing-command:{context.company.id}:{payload.idempotency_key}",
                    )
                )
                for identity in lock_identities:
                    await session.execute(
                        text(
                            "SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"
                        ),
                        {"identity": identity},
                    )
            replay = await self.repository.receipt(
                session, context.company.id, payload.idempotency_key
            )
            if replay is not None:
                if (
                    replay.operation != "configure_branch_policy"
                    or replay.result_type != "branch_purchasing_policy"
                    or replay.payload_digest != payload_digest
                ):
                    raise PurchasingConflict(
                        "Idempotency key was already used with different policy evidence"
                    )
                policy = await session.get(BranchPurchasingPolicy, replay.result_id)
                if policy is None or policy.company_id != context.company.id:
                    raise PurchasingConflict("Policy replay evidence is unavailable")
                return await self._branch_policy_item(session, policy)

            await self._inventory_item(
                session, context.company.id, payload.inventory_item_id
            )
            policy = await self.repository.branch_policy(
                session,
                context.company.id,
                payload.branch_id,
                payload.inventory_item_id,
                lock=True,
            )
            now = datetime.now(timezone.utc)
            if policy is None:
                if payload.expected_version is not None:
                    raise PurchasingConflict("Branch policy does not yet exist")
                policy = BranchPurchasingPolicy(
                    company_id=context.company.id,
                    branch_id=payload.branch_id,
                    inventory_item_id=payload.inventory_item_id,
                    target_available_quantity=payload.target_available_quantity,
                    status=payload.status,
                    provenance_reference=payload.provenance_reference,
                    version=1,
                    created_by_user_id=context.user.id,
                    updated_by_user_id=context.user.id,
                    created_at=now,
                    updated_at=now,
                )
                session.add(policy)
                await session.flush()
            else:
                if (
                    payload.expected_version is None
                    or policy.version != payload.expected_version
                ):
                    raise PurchasingConflict(
                        "Branch purchasing policy version is stale"
                    )
                policy.target_available_quantity = payload.target_available_quantity
                policy.status = payload.status
                policy.provenance_reference = payload.provenance_reference
                policy.version += 1
                policy.updated_by_user_id = context.user.id
                policy.updated_at = now

            evidence = {
                "schema_version": 1,
                "company_id": str(context.company.id),
                "branch_id": str(payload.branch_id),
                "policy_id": str(policy.id),
                "inventory_item_id": str(payload.inventory_item_id),
                "target_available_quantity": str(payload.target_available_quantity),
                "status": payload.status,
                "provenance_reference": payload.provenance_reference,
                "version": policy.version,
                "reason": payload.reason,
                "actor_user_id": str(context.user.id),
                "occurred_at": now.isoformat(),
            }
            revision = BranchPurchasingPolicyRevision(
                company_id=context.company.id,
                policy_id=policy.id,
                version=policy.version,
                target_available_quantity=payload.target_available_quantity,
                status=payload.status,
                provenance_reference=payload.provenance_reference,
                reason=payload.reason,
                idempotency_key=payload.idempotency_key,
                payload_digest=payload_digest,
                evidence_digest=digest(evidence),
                actor_user_id=context.user.id,
                occurred_at=now,
            )
            session.add(revision)
            self._receipt(
                session,
                context,
                "configure_branch_policy",
                payload.idempotency_key,
                data,
                "branch_purchasing_policy",
                policy.id,
            )
            self._event(
                session,
                context,
                EventType.PURCHASING_BRANCH_POLICY_CONFIGURED,
                "branch_purchasing_policy",
                policy.id,
                policy.branch_id,
                {
                    "policy_id": str(policy.id),
                    "inventory_item_id": str(policy.inventory_item_id),
                    "version": policy.version,
                    "status": policy.status,
                    "evidence_digest": revision.evidence_digest,
                },
            )
        return await self._branch_policy_item(session, policy)

    async def _branch_policy_item(
        self, session: AsyncSession, policy: BranchPurchasingPolicy
    ) -> BranchPurchasingPolicyItem:
        revisions = await self.repository.branch_policy_revisions(
            session, policy.company_id, policy.id
        )
        return BranchPurchasingPolicyItem.model_validate(policy).model_copy(
            update={
                "revisions": tuple(
                    BranchPurchasingPolicyRevisionItem.model_validate(item)
                    for item in revisions
                )
            }
        )

    async def replenishment_workbench(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        payload: ReplenishmentWorkbenchRequest,
    ) -> ReplenishmentWorkbench:
        identities = [
            (item.branch_id, item.inventory_item_id) for item in payload.targets
        ]
        if len(identities) != len(set(identities)):
            raise PurchasingValidation("Replenishment targets must be unique")
        recommendations: list[ReplenishmentRecommendation] = []
        for target in sorted(
            payload.targets,
            key=lambda item: (str(item.branch_id), str(item.inventory_item_id)),
        ):
            self.branch(context, target.branch_id)
            item = await session.scalar(
                select(InventoryItem).where(
                    InventoryItem.company_id == context.company.id,
                    InventoryItem.id == target.inventory_item_id,
                )
            )
            if item is None or item.status != "active":
                raise PurchasingNotFound("Active Inventory Item was not found")
            quantities = tuple(
                (
                    await session.scalars(
                        select(InventoryQuantity).where(
                            InventoryQuantity.company_id == context.company.id,
                            InventoryQuantity.branch_id == target.branch_id,
                            InventoryQuantity.item_id == target.inventory_item_id,
                        )
                    )
                ).all()
            )
            if not quantities:
                raise PurchasingValidation(
                    "Authoritative Inventory quantity evidence is required"
                )
            on_hand = sum((row.on_hand for row in quantities), Decimal(0))
            reserved = sum((row.reserved for row in quantities), Decimal(0))
            available = on_hand - reserved
            open_order = Decimal(0)
            provenance = [
                f"inventory_item:{item.id}:v{item.version}",
                *sorted(
                    f"inventory_quantity:{row.id}:v{row.version}:{row.updated_at.isoformat()}"
                    for row in quantities
                ),
            ]
            orders = await self.repository.purchase_orders(
                session, context.company.id, (target.branch_id,)
            )
            for order in orders:
                if order.status != "issued":
                    continue
                disposition = await self.repository.disposition(
                    session, order.company_id, order.id
                )
                if disposition is not None:
                    continue
                accepted = await self.repository.accepted_totals(
                    session, order.company_id, order.id
                )
                for line in await self.repository.lines(
                    session, order.company_id, order.id
                ):
                    if line.inventory_item_id != item.id or line.is_cancelled:
                        continue
                    remainder = max(
                        line.quantity - accepted.get(line.id, Decimal(0)), Decimal(0)
                    )
                    open_order += remainder
                    provenance.append(
                        f"purchase_order:{order.id}:v{order.version}:r{order.effective_revision}:line:{line.id}:v{line.version}"
                    )
            recommended = max(
                target.target_available_quantity - available - open_order, Decimal(0)
            )
            fact = {
                "company_id": str(context.company.id),
                "branch_id": str(target.branch_id),
                "inventory_item_id": str(item.id),
                "as_of": payload.as_of.isoformat(),
                "target": str(target.target_available_quantity),
                "on_hand": str(on_hand),
                "reserved": str(reserved),
                "available": str(available),
                "open_order": str(open_order),
                "recommended": str(recommended),
                "provenance": sorted(provenance),
            }
            recommendations.append(
                ReplenishmentRecommendation(
                    branch_id=target.branch_id,
                    inventory_item_id=item.id,
                    item_code=item.code,
                    item_name=item.name,
                    stocking_unit=item.stocking_unit,
                    target_available_quantity=target.target_available_quantity,
                    on_hand_quantity=on_hand,
                    reserved_quantity=reserved,
                    available_quantity=available,
                    open_purchase_order_quantity=open_order,
                    recommended_order_quantity=recommended,
                    recommendation_state=(
                        "recommend_order" if recommended > 0 else "no_action"
                    ),
                    provenance=tuple(sorted(provenance)),
                    evidence_digest=digest(fact),
                )
            )
        report = {
            "schema_version": 1,
            "company_id": str(context.company.id),
            "as_of": payload.as_of.isoformat(),
            "recommendations": [
                item.model_dump(mode="json") for item in recommendations
            ],
        }
        return ReplenishmentWorkbench(
            company_id=context.company.id,
            as_of=payload.as_of,
            recommendations=tuple(recommendations),
            evidence_digest=digest(report),
        )

    async def decide_replenishment(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        payload: ReplenishmentDecisionCommand,
    ) -> ReplenishmentDecisionItem:
        self.branch(context, payload.branch_id)
        data = payload.model_dump(mode="json")
        payload_digest = digest(data)
        async with session.begin():
            replay = await session.scalar(
                select(ReplenishmentDecisionEvidence).where(
                    ReplenishmentDecisionEvidence.company_id == context.company.id,
                    ReplenishmentDecisionEvidence.idempotency_key
                    == payload.idempotency_key,
                )
            )
            if replay:
                if replay.payload_digest != payload_digest:
                    raise PurchasingConflict(
                        "Replenishment decision idempotency identity conflicts"
                    )
                return ReplenishmentDecisionItem.model_validate(replay)
            workbench = await self.replenishment_workbench(
                session,
                context=context,
                payload=ReplenishmentWorkbenchRequest(
                    as_of=payload.recommendation_as_of,
                    targets=(
                        ReplenishmentTarget(
                            branch_id=payload.branch_id,
                            inventory_item_id=payload.inventory_item_id,
                            target_available_quantity=payload.target_available_quantity,
                        ),
                    ),
                ),
            )
            recommendation = workbench.recommendations[0]
            if recommendation.evidence_digest != payload.recommendation_digest:
                raise PurchasingConflict("STALE_REPLENISHMENT_RECOMMENDATION")
            vendor = None
            order = None
            approved_quantity = payload.approved_quantity
            if payload.decision == "approved":
                vendor_id = payload.vendor_id
                po_number = payload.po_number
                currency = payload.currency
                unit_cost = payload.unit_cost
                if (
                    vendor_id is None
                    or po_number is None
                    or currency is None
                    or unit_cost is None
                    or approved_quantity is None
                ):
                    raise PurchasingValidation(
                        "Approved replenishment requires explicit Vendor, PO identity, currency, quantity, and unit cost"
                    )
                if approved_quantity > recommendation.recommended_order_quantity:
                    raise PurchasingValidation(
                        "Approved quantity cannot exceed the recommendation"
                    )
                vendor = await self.repository.vendor(
                    session, context.company.id, vendor_id
                )
                if vendor is None or vendor.status != "active":
                    raise PurchasingValidation("Active operational Vendor is required")
                item = await session.scalar(
                    select(InventoryItem).where(
                        InventoryItem.company_id == context.company.id,
                        InventoryItem.id == payload.inventory_item_id,
                        InventoryItem.status == "active",
                    )
                )
                if item is None:
                    raise PurchasingValidation("Active Inventory item is required")
                order = PurchaseOrder(
                    company_id=context.company.id,
                    branch_id=payload.branch_id,
                    vendor_id=vendor.id,
                    po_number=po_number.strip().upper(),
                    currency=currency,
                    prepared_by_user_id=context.user.id,
                )
                session.add(order)
                await session.flush()
                session.add(
                    PurchaseOrderLine(
                        company_id=context.company.id,
                        purchase_order_id=order.id,
                        line_number=1,
                        inventory_item_id=item.id,
                        description=item.name,
                        quantity=approved_quantity,
                        unit=item.stocking_unit,
                        unit_cost=unit_cost,
                        extended_cost=approved_quantity * unit_cost,
                        created_by_user_id=context.user.id,
                    )
                )
                order.version += 1
            snapshot = recommendation.model_dump(mode="json")
            approval_digest = digest(
                {
                    "recommendation": snapshot,
                    "decision": payload.decision,
                    "quantity": str(approved_quantity) if approved_quantity else None,
                    "vendor_id": str(vendor.id) if vendor else None,
                    "purchase_order_id": str(order.id) if order else None,
                    "actor": str(context.user.id),
                    "reason": payload.reason,
                }
            )
            record = ReplenishmentDecisionEvidence(
                company_id=context.company.id,
                branch_id=payload.branch_id,
                inventory_item_id=payload.inventory_item_id,
                recommendation_digest=payload.recommendation_digest,
                recommendation_snapshot=snapshot,
                approval_evidence_digest=approval_digest,
                decision=payload.decision,
                reason=payload.reason,
                approved_quantity=approved_quantity
                if payload.decision == "approved"
                else None,
                vendor_id=vendor.id if vendor else None,
                purchase_order_id=order.id if order else None,
                actor_user_id=context.user.id,
                idempotency_key=payload.idempotency_key,
                payload_digest=payload_digest,
            )
            session.add(record)
            await session.flush()
            self._event(
                session,
                context,
                EventType.PURCHASING_REPLENISHMENT_APPROVED
                if payload.decision == "approved"
                else EventType.PURCHASING_REPLENISHMENT_REJECTED,
                "replenishment_decision",
                record.id,
                record.branch_id,
                {
                    "decision_id": str(record.id),
                    "recommendation_digest": record.recommendation_digest,
                    "decision": record.decision,
                },
            )
            if order is not None:
                self._event(
                    session,
                    context,
                    EventType.PURCHASING_REPLENISHMENT_LINKED,
                    "replenishment_decision",
                    record.id,
                    record.branch_id,
                    {"decision_id": str(record.id), "purchase_order_id": str(order.id)},
                )
            return ReplenishmentDecisionItem.model_validate(record)

    async def vendor_performance_evidence(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        vendor_id: UUID,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
    ) -> VendorPerformanceEvidenceReport:
        if from_at and to_at and from_at >= to_at:
            raise PurchasingValidation("Evidence interval must have positive duration")
        vendor = await self.repository.vendor(session, context.company.id, vendor_id)
        if vendor is None:
            raise PurchasingNotFound("Vendor was not found")
        orders = await self.repository.purchase_orders_for_vendor(
            session,
            context.company.id,
            vendor_id,
            tuple(context.authorized_branch_ids),
        )
        evidence: list[VendorPerformanceEvidence] = []

        def add(
            *,
            evidence_type: str,
            availability: str,
            value: object | None,
            unit: str | None,
            order: PurchaseOrder,
            source_type: str,
            source_id: UUID,
            effective_at: datetime,
            line_id: UUID | None = None,
            receipt_id: UUID | None = None,
            discrepancy_id: UUID | None = None,
            return_id: UUID | None = None,
            provenance: tuple[str, ...],
        ) -> None:
            if (from_at and effective_at < from_at) or (
                to_at and effective_at >= to_at
            ):
                return
            fact = {
                "schema_version": 1,
                "evidence_type": evidence_type,
                "availability": availability,
                "value": None if value is None else str(value),
                "unit": unit,
                "company_id": str(order.company_id),
                "branch_id": str(order.branch_id),
                "vendor_id": str(order.vendor_id),
                "purchase_order_id": str(order.id),
                "purchase_order_line_id": str(line_id) if line_id else None,
                "receipt_id": str(receipt_id) if receipt_id else None,
                "discrepancy_id": str(discrepancy_id) if discrepancy_id else None,
                "return_id": str(return_id) if return_id else None,
                "source_type": source_type,
                "source_id": str(source_id),
                "effective_at": effective_at.isoformat(),
                "provenance": provenance,
            }
            fact_digest = digest(fact)
            evidence.append(
                VendorPerformanceEvidence(
                    schema_version=1,
                    evidence_id=fact_digest,
                    evidence_type=evidence_type,
                    availability=availability,
                    value=None if value is None else str(value),
                    unit=unit,
                    company_id=order.company_id,
                    branch_id=order.branch_id,
                    vendor_id=order.vendor_id,
                    purchase_order_id=order.id,
                    purchase_order_line_id=line_id,
                    receipt_id=receipt_id,
                    discrepancy_id=discrepancy_id,
                    return_id=return_id,
                    source_type=source_type,
                    source_id=source_id,
                    effective_at=effective_at,
                    provenance=provenance,
                    digest=fact_digest,
                )
            )

        for order in orders:
            if order.vendor_id != vendor.id or order.company_id != context.company.id:
                raise PurchasingConflict("Vendor evidence identity is contradictory")
            issuance = await self.repository.evidence(
                session, order.company_id, order.id
            )
            if issuance is None:
                continue
            issued_at = issuance.issued_at
            add(
                evidence_type="purchase_order.issued",
                availability="available",
                value=order.po_number,
                unit="purchase_order",
                order=order,
                source_type="purchase_order_issuance_evidence",
                source_id=issuance.id,
                effective_at=issued_at,
                provenance=(issuance.digest,),
            )
            snapshot_lines = issuance.snapshot.get("lines", [])
            if not isinstance(snapshot_lines, list):
                raise PurchasingConflict(
                    "Purchase Order issuance evidence is malformed"
                )
            po_expected = issuance.snapshot.get("expected_date")
            for raw_line in snapshot_lines:
                if not isinstance(raw_line, dict):
                    raise PurchasingConflict(
                        "Purchase Order line evidence is malformed"
                    )
                line_id = UUID(str(raw_line["id"]))
                provenance = (issuance.digest, f"line:{line_id}")
                add(
                    evidence_type="order.quantity",
                    availability="available",
                    value=raw_line["quantity"],
                    unit=str(raw_line["unit"]),
                    order=order,
                    source_type="purchase_order_issuance_line",
                    source_id=line_id,
                    effective_at=issued_at,
                    line_id=line_id,
                    provenance=provenance,
                )
                add(
                    evidence_type="order.unit_cost",
                    availability="available",
                    value=raw_line["unit_cost"],
                    unit=f"{order.currency}_per_{raw_line['unit']}",
                    order=order,
                    source_type="purchase_order_issuance_line",
                    source_id=line_id,
                    effective_at=issued_at,
                    line_id=line_id,
                    provenance=provenance,
                )
                expected = raw_line.get("expected_date") or po_expected
                add(
                    evidence_type="fulfillment.promised_date",
                    availability="available" if expected else "unavailable",
                    value=expected,
                    unit="date" if expected else None,
                    order=order,
                    source_type="purchase_order_issuance_line",
                    source_id=line_id,
                    effective_at=issued_at,
                    line_id=line_id,
                    provenance=provenance,
                )

            receipts = await self.repository.receiving_events(
                session, order.company_id, order.id
            )
            first_receipt_at = receipts[0].received_at if receipts else None
            for receipt in receipts:
                if (
                    receipt.vendor_id != order.vendor_id
                    or receipt.branch_id != order.branch_id
                ):
                    raise PurchasingConflict(
                        "Receipt Vendor or Branch evidence conflicts"
                    )
                receipt_lines = await self.repository.receipt_lines(
                    session, order.company_id, receipt.id
                )
                for line in receipt_lines:
                    receipt_provenance = (
                        issuance.digest,
                        receipt.payload_digest,
                        f"receipt_line:{line.id}",
                    )
                    add(
                        evidence_type="receipt.accepted_quantity",
                        availability="available",
                        value=line.accepted_quantity,
                        unit=line.unit_snapshot,
                        order=order,
                        source_type="purchase_order_receipt_line",
                        source_id=line.id,
                        effective_at=receipt.received_at,
                        line_id=line.purchase_order_line_id,
                        receipt_id=receipt.id,
                        provenance=receipt_provenance,
                    )
                    add(
                        evidence_type="receipt.rejected_quantity",
                        availability="available",
                        value=line.rejected_quantity,
                        unit=line.unit_snapshot,
                        order=order,
                        source_type="purchase_order_receipt_line",
                        source_id=line.id,
                        effective_at=receipt.received_at,
                        line_id=line.purchase_order_line_id,
                        receipt_id=receipt.id,
                        provenance=receipt_provenance,
                    )
                    add(
                        evidence_type="fulfillment.outstanding_quantity",
                        availability="available",
                        value=line.outstanding_quantity,
                        unit=line.unit_snapshot,
                        order=order,
                        source_type="purchase_order_receipt_line",
                        source_id=line.id,
                        effective_at=receipt.received_at,
                        line_id=line.purchase_order_line_id,
                        receipt_id=receipt.id,
                        provenance=receipt_provenance,
                    )
                    add(
                        evidence_type="fulfillment.receipt_state",
                        availability="available",
                        value=(
                            "fully_received"
                            if line.outstanding_quantity == 0
                            else "partially_received"
                        ),
                        unit="line_state",
                        order=order,
                        source_type="purchase_order_receipt_line",
                        source_id=line.id,
                        effective_at=receipt.received_at,
                        line_id=line.purchase_order_line_id,
                        receipt_id=receipt.id,
                        provenance=receipt_provenance,
                    )
                    expected = next(
                        (
                            item.get("expected_date") or po_expected
                            for item in snapshot_lines
                            if isinstance(item, dict)
                            and str(item.get("id")) == str(line.purchase_order_line_id)
                        ),
                        None,
                    )
                    promised_delta = None
                    if expected:
                        promised_delta = (
                            receipt.effective_date - date.fromisoformat(str(expected))
                        ).days
                    add(
                        evidence_type="lead_time.promised_to_receipt",
                        availability="available" if expected else "unavailable",
                        value=promised_delta,
                        unit="days" if expected else None,
                        order=order,
                        source_type="purchase_order_receipt_line",
                        source_id=line.id,
                        effective_at=receipt.received_at,
                        line_id=line.purchase_order_line_id,
                        receipt_id=receipt.id,
                        provenance=receipt_provenance,
                    )
                add(
                    evidence_type="lead_time.order_to_receipt",
                    availability="available",
                    value=int((receipt.received_at - issued_at).total_seconds()),
                    unit="seconds",
                    order=order,
                    source_type="purchase_order_receipt",
                    source_id=receipt.id,
                    effective_at=receipt.received_at,
                    receipt_id=receipt.id,
                    provenance=(issuance.digest, receipt.payload_digest),
                )
            if first_receipt_at is None:
                add(
                    evidence_type="lead_time.order_to_first_receipt",
                    availability="unavailable",
                    value=None,
                    unit=None,
                    order=order,
                    source_type="purchase_order_issuance_evidence",
                    source_id=issuance.id,
                    effective_at=issued_at,
                    provenance=(issuance.digest,),
                )
            else:
                first = receipts[0]
                add(
                    evidence_type="lead_time.order_to_first_receipt",
                    availability="available",
                    value=int((first_receipt_at - issued_at).total_seconds()),
                    unit="seconds",
                    order=order,
                    source_type="purchase_order_receipt",
                    source_id=first.id,
                    effective_at=first_receipt_at,
                    receipt_id=first.id,
                    provenance=(issuance.digest, first.payload_digest),
                )

            for discrepancy in await self.repository.discrepancies(
                session, order.company_id, order.id
            ):
                add(
                    evidence_type=f"discrepancy.{discrepancy.category}",
                    availability="available",
                    value=discrepancy.status,
                    unit="observed_fact_not_fault",
                    order=order,
                    source_type="purchase_order_discrepancy",
                    source_id=discrepancy.id,
                    effective_at=discrepancy.opened_at,
                    line_id=discrepancy.purchase_order_line_id,
                    receipt_id=discrepancy.receipt_id,
                    discrepancy_id=discrepancy.id,
                    provenance=(
                        f"expected:{discrepancy.expected_fact}",
                        f"actual:{discrepancy.actual_fact}",
                        f"version:{discrepancy.version}",
                    ),
                )
            for purchase_return in await self.repository.purchase_returns(
                session, order.company_id, order.id
            ):
                if purchase_return.vendor_id != order.vendor_id:
                    raise PurchasingConflict(
                        "Purchase Return Vendor evidence conflicts"
                    )
                add(
                    evidence_type="return.lifecycle",
                    availability="available",
                    value=purchase_return.status,
                    unit="operational_fact_not_fault",
                    order=order,
                    source_type="purchase_return",
                    source_id=purchase_return.id,
                    effective_at=purchase_return.updated_at,
                    line_id=purchase_return.purchase_order_line_id,
                    receipt_id=purchase_return.receipt_id,
                    return_id=purchase_return.id,
                    provenance=(
                        f"reason:{purchase_return.reason}",
                        f"authorization:{purchase_return.authorization_status}",
                        f"version:{purchase_return.version}",
                    ),
                )
            disposition = await self.repository.disposition(
                session, order.company_id, order.id
            )
            if disposition:
                add(
                    evidence_type="purchase_order.disposition",
                    availability="available",
                    value=disposition.disposition,
                    unit="control_evidence",
                    order=order,
                    source_type="purchase_order_disposition_evidence",
                    source_id=disposition.id,
                    effective_at=disposition.occurred_at,
                    provenance=(disposition.evidence_digest,),
                )

        evidence.sort(key=lambda item: (item.effective_at, item.evidence_id))
        availability_counts = {
            state: sum(item.availability == state for item in evidence)
            for state in ("available", "unavailable", "not_applicable", "conflicting")
        }
        summary = VendorPerformanceSummary(
            purchase_orders_observed=sum(
                item.evidence_type == "purchase_order.issued" for item in evidence
            ),
            receipts_observed=len(
                {
                    item.receipt_id
                    for item in evidence
                    if item.receipt_id is not None
                    and item.evidence_type == "lead_time.order_to_receipt"
                }
            ),
            discrepancies_observed=sum(
                item.evidence_type.startswith("discrepancy.") for item in evidence
            ),
            returns_observed=sum(
                item.evidence_type == "return.lifecycle" for item in evidence
            ),
            ordered_quantity_observed=sum(
                (
                    Decimal(item.value)
                    for item in evidence
                    if item.evidence_type == "order.quantity" and item.value is not None
                ),
                Decimal(0),
            ),
            accepted_quantity_observed=sum(
                (
                    Decimal(item.value)
                    for item in evidence
                    if item.evidence_type == "receipt.accepted_quantity"
                    and item.value is not None
                ),
                Decimal(0),
            ),
            rejected_quantity_observed=sum(
                (
                    Decimal(item.value)
                    for item in evidence
                    if item.evidence_type == "receipt.rejected_quantity"
                    and item.value is not None
                ),
                Decimal(0),
            ),
            lead_time_observations=sum(
                item.evidence_type.startswith("lead_time.")
                and item.availability == "available"
                for item in evidence
            ),
            availability_counts=availability_counts,
        )
        report_payload = {
            "schema_version": 1,
            "company_id": str(context.company.id),
            "vendor_id": str(vendor.id),
            "from_at": from_at.isoformat() if from_at else None,
            "to_at": to_at.isoformat() if to_at else None,
            "evidence_digests": [item.digest for item in evidence],
            "summary": summary.model_dump(mode="json"),
        }
        return VendorPerformanceEvidenceReport(
            company_id=context.company.id,
            vendor_id=vendor.id,
            from_at=from_at,
            to_at=to_at,
            evidence=tuple(evidence),
            summary=summary,
            evidence_digest=digest(report_payload),
        )

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
                raise PurchasingValidation(
                    "Use the explicit Purchase Order cancellation disposition"
                )
            elif target == "close":
                raise PurchasingValidation(
                    "Use the explicit Purchase Order completion disposition"
                )
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

    async def record_receipt(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        po_id: UUID,
        payload: RecordReceiptCommand,
    ) -> PurchaseOrderReceipt:
        data = {"po_id": str(po_id), **payload.model_dump(mode="json")}
        categories = {
            "quantity_short",
            "quantity_over",
            "wrong_item",
            "damaged_item",
            "rejected_item",
            "missing_line",
        }
        async with session.begin():
            replay = await self._replay(
                session,
                context,
                "po.receipt.record",
                payload.idempotency_key,
                data,
                "purchase_order_receipt",
            )
            if replay:
                record = await self.repository.receiving_event(
                    session, context.company.id, replay
                )
                if record is None:
                    raise PurchasingConflict("Receipt replay target is missing")
                return record
            order = await self._order(session, context, po_id, lock=True)
            replay = await self._replay(
                session,
                context,
                "po.receipt.record",
                payload.idempotency_key,
                data,
                "purchase_order_receipt",
            )
            if replay:
                record = await self.repository.receiving_event(
                    session, context.company.id, replay
                )
                if record is None:
                    raise PurchasingConflict("Receipt replay target is missing")
                return record
            if order.status != "issued":
                raise PurchasingValidation(
                    "Only an issued Purchase Order may be received"
                )
            if order.version != payload.expected_po_version:
                raise PurchasingConflict("Purchase Order version is stale")
            command_ids = [item.purchase_order_line_id for item in payload.lines]
            if len(command_ids) != len(set(command_ids)):
                raise PurchasingValidation(
                    "A PO line may appear only once per receiving event"
                )
            lines = {
                line.id: line
                for line in await self.repository.lines(
                    session, context.company.id, order.id
                )
            }
            totals = await self.repository.accepted_totals(
                session, context.company.id, order.id
            )
            receipt = PurchaseOrderReceipt(
                company_id=order.company_id,
                branch_id=order.branch_id,
                purchase_order_id=order.id,
                vendor_id=order.vendor_id,
                receiving_event_identity=payload.receiving_event_identity.strip(),
                status="recorded",
                receiver_user_id=context.user.id,
                received_at=payload.received_at,
                effective_date=payload.effective_date,
                source_reference=payload.source_reference,
                payload_digest=digest(data),
            )
            session.add(receipt)
            await session.flush()
            opened: list[PurchaseOrderDiscrepancy] = []
            for outcome in payload.lines:
                line = lines.get(outcome.purchase_order_line_id)
                if line is None:
                    raise PurchasingValidation(
                        "Receipt line does not belong to this Purchase Order"
                    )
                category = outcome.discrepancy_category
                if category is not None and category not in categories:
                    raise PurchasingValidation("Unsupported discrepancy category")
                prior = totals.get(line.id, Decimal(0))
                cumulative = prior + outcome.accepted_quantity
                if cumulative > line.quantity:
                    raise PurchasingValidation(
                        "Accepted quantity exceeds ordered quantity; record discrepancy without accepting overage"
                    )
                outstanding = line.quantity - cumulative
                receipt_line = PurchaseOrderReceiptLine(
                    company_id=order.company_id,
                    receipt_id=receipt.id,
                    purchase_order_line_id=line.id,
                    ordered_quantity_snapshot=line.quantity,
                    accepted_quantity=outcome.accepted_quantity,
                    rejected_quantity=outcome.rejected_quantity,
                    cumulative_accepted_quantity=cumulative,
                    outstanding_quantity=outstanding,
                    unit_snapshot=line.unit,
                    discrepancy_category=category,
                    observed_condition=outcome.observed_condition,
                )
                session.add(receipt_line)
                await session.flush()
                totals[line.id] = cumulative
                if category:
                    observed = (outcome.observed_condition or "").strip()
                    if not observed:
                        raise PurchasingValidation(
                            "Discrepancy observed condition is required"
                        )
                    discrepancy = PurchaseOrderDiscrepancy(
                        company_id=order.company_id,
                        branch_id=order.branch_id,
                        purchase_order_id=order.id,
                        purchase_order_line_id=line.id,
                        receipt_id=receipt.id,
                        receipt_line_id=receipt_line.id,
                        category=category,
                        expected_fact=f"ordered={line.quantity} {line.unit}; prior_accepted={prior}",
                        actual_fact=(
                            f"accepted={outcome.accepted_quantity}; rejected={outcome.rejected_quantity}"
                        ),
                        observed_condition=observed,
                        opened_by_user_id=context.user.id,
                        opened_at=now(),
                    )
                    session.add(discrepancy)
                    opened.append(discrepancy)
            if opened:
                receipt.status = "discrepancy_outstanding"
            order.version += 1
            order.updated_at = now()
            self._receipt(
                session,
                context,
                "po.receipt.record",
                payload.idempotency_key,
                data,
                "purchase_order_receipt",
                receipt.id,
            )
            self._event(
                session,
                context,
                EventType.PURCHASING_PURCHASE_ORDER_RECEIPT_RECORDED,
                "purchase_order_receipt",
                receipt.id,
                order.branch_id,
                {
                    "purchase_order_id": str(order.id),
                    "receipt_id": str(receipt.id),
                    "receiving_event_identity": receipt.receiving_event_identity,
                    "discrepancy_count": len(opened),
                    "purchase_order_version": order.version,
                },
            )
            state = self._receiving_state(lines.values(), totals, bool(opened))
            if state == "fully_received":
                event_type = EventType.PURCHASING_PURCHASE_ORDER_FULLY_RECEIVED
            else:
                event_type = EventType.PURCHASING_PURCHASE_ORDER_PARTIALLY_RECEIVED
            self._event(
                session,
                context,
                event_type,
                "purchase_order",
                order.id,
                order.branch_id,
                {
                    "purchase_order_id": str(order.id),
                    "receiving_status": state,
                    "version": order.version,
                },
            )
            for discrepancy in opened:
                await session.flush()
                self._event(
                    session,
                    context,
                    EventType.PURCHASING_PURCHASE_ORDER_DISCREPANCY_OPENED,
                    "purchase_order_discrepancy",
                    discrepancy.id,
                    order.branch_id,
                    {
                        "purchase_order_id": str(order.id),
                        "receipt_id": str(receipt.id),
                        "category": discrepancy.category,
                        "status": discrepancy.status,
                    },
                )
        return receipt

    async def resolve_discrepancy(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        po_id: UUID,
        discrepancy_id: UUID,
        payload: ResolveDiscrepancyCommand,
    ) -> PurchaseOrderDiscrepancy:
        data = {
            "po_id": str(po_id),
            "discrepancy_id": str(discrepancy_id),
            **payload.model_dump(mode="json"),
        }
        async with session.begin():
            replay = await self._replay(
                session,
                context,
                "po.discrepancy.resolve",
                payload.idempotency_key,
                data,
                "purchase_order_discrepancy",
            )
            if replay:
                record = await self.repository.discrepancy(
                    session, context.company.id, replay
                )
                if record is None:
                    raise PurchasingConflict("Discrepancy replay target is missing")
                return record
            order = await self._order(session, context, po_id, lock=True)
            if order.version != payload.expected_po_version:
                raise PurchasingConflict("Purchase Order version is stale")
            record = await self.repository.discrepancy(
                session, context.company.id, discrepancy_id, lock=True
            )
            if record is None or record.purchase_order_id != order.id:
                raise PurchasingNotFound("Purchase Order discrepancy was not found")
            if record.status != "open":
                raise PurchasingValidation("Only an open discrepancy may be resolved")
            if record.version != payload.expected_discrepancy_version:
                raise PurchasingConflict("Discrepancy version is stale")
            record.status = payload.resolution
            record.resolution_note = payload.note.strip()
            record.resolved_by_user_id = context.user.id
            record.resolved_at = now()
            record.version += 1
            order.version += 1
            order.updated_at = now()
            self._receipt(
                session,
                context,
                "po.discrepancy.resolve",
                payload.idempotency_key,
                data,
                "purchase_order_discrepancy",
                record.id,
            )
            self._event(
                session,
                context,
                EventType.PURCHASING_PURCHASE_ORDER_DISCREPANCY_RESOLVED,
                "purchase_order_discrepancy",
                record.id,
                order.branch_id,
                {
                    "purchase_order_id": str(order.id),
                    "discrepancy_id": str(record.id),
                    "status": record.status,
                    "version": record.version,
                },
            )
        return record

    async def create_purchase_return(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        po_id: UUID,
        payload: CreatePurchaseReturnCommand,
    ) -> PurchaseReturn:
        data = {"po_id": str(po_id), **payload.model_dump(mode="json")}
        reasons = {
            "damaged_after_receipt",
            "defective",
            "wrong_item",
            "excess_not_needed",
            "vendor_requested",
            "other",
        }
        async with session.begin():
            replay = await self._replay(
                session,
                context,
                "po.return.create",
                payload.idempotency_key,
                data,
                "purchase_return",
            )
            if replay:
                record = await self.repository.purchase_return(
                    session, context.company.id, replay
                )
                if record is None:
                    raise PurchasingConflict("Purchase Return replay target is missing")
                return record
            order = await self._order(session, context, po_id, lock=True)
            replay = await self._replay(
                session,
                context,
                "po.return.create",
                payload.idempotency_key,
                data,
                "purchase_return",
            )
            if replay:
                record = await self.repository.purchase_return(
                    session, context.company.id, replay
                )
                if record is None:
                    raise PurchasingConflict("Purchase Return replay target is missing")
                return record
            if order.version != payload.expected_po_version:
                raise PurchasingConflict("Purchase Order version is stale")
            if payload.reason not in reasons:
                raise PurchasingValidation("Unsupported Purchase Return reason")
            if payload.reason == "other" and not (payload.reason_note or "").strip():
                raise PurchasingValidation("Other return reason requires description")
            receipt = await self.repository.receiving_event(
                session, context.company.id, payload.receipt_id
            )
            receipt_line = await session.get(
                PurchaseOrderReceiptLine, payload.receipt_line_id
            )
            if receipt is None or receipt.purchase_order_id != order.id:
                raise PurchasingValidation(
                    "Return receipt does not belong to this Purchase Order"
                )
            if (
                receipt_line is None
                or receipt_line.company_id != context.company.id
                or receipt_line.receipt_id != receipt.id
            ):
                raise PurchasingValidation("Return receipt line is invalid")
            committed = await self.repository.committed_return_quantity(
                session, context.company.id, receipt_line.id
            )
            if payload.quantity > receipt_line.accepted_quantity - committed:
                raise PurchasingValidation(
                    "Return quantity exceeds remaining accepted receipt quantity"
                )
            po_line = await self.repository.line(
                session,
                context.company.id,
                order.id,
                receipt_line.purchase_order_line_id,
            )
            if po_line is None:
                raise PurchasingConflict("Authoritative Purchase Order line is missing")
            timestamp = now()
            record = PurchaseReturn(
                company_id=order.company_id,
                branch_id=order.branch_id,
                purchase_order_id=order.id,
                vendor_id=order.vendor_id,
                receipt_id=receipt.id,
                receipt_line_id=receipt_line.id,
                purchase_order_line_id=po_line.id,
                return_identity=payload.return_identity.strip(),
                item_identity_snapshot=str(po_line.inventory_item_id)
                if po_line.inventory_item_id
                else po_line.description,
                accepted_quantity_snapshot=receipt_line.accepted_quantity,
                quantity=payload.quantity,
                reason=payload.reason,
                reason_note=payload.reason_note,
                authorization_status="not_requested"
                if payload.authorization_required
                else "not_required",
                requested_by_user_id=context.user.id,
                requested_at=timestamp,
                effective_date=payload.effective_date,
                updated_by_user_id=context.user.id,
                updated_at=timestamp,
                source_reference=payload.source_reference,
            )
            session.add(record)
            await session.flush()
            order.version += 1
            order.updated_at = timestamp
            self._receipt(
                session,
                context,
                "po.return.create",
                payload.idempotency_key,
                data,
                "purchase_return",
                record.id,
            )
            self._event(
                session,
                context,
                EventType.PURCHASING_PURCHASE_RETURN_CREATED,
                "purchase_return",
                record.id,
                order.branch_id,
                {
                    "purchase_order_id": str(order.id),
                    "purchase_return_id": str(record.id),
                    "receipt_id": str(receipt.id),
                    "receipt_line_id": str(receipt_line.id),
                    "quantity": str(record.quantity),
                    "status": record.status,
                },
            )
        return record

    async def transition_purchase_return(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        po_id: UUID,
        return_id: UUID,
        action: str,
        payload: PurchaseReturnTransitionCommand,
    ) -> PurchaseReturn:
        data = {
            "po_id": str(po_id),
            "return_id": str(return_id),
            "action": action,
            **payload.model_dump(mode="json"),
        }
        operation = f"po.return.{action}"
        async with session.begin():
            replay = await self._replay(
                session,
                context,
                operation,
                payload.idempotency_key,
                data,
                "purchase_return",
            )
            if replay:
                record = await self.repository.purchase_return(
                    session, context.company.id, replay
                )
                if record is None:
                    raise PurchasingConflict("Purchase Return replay target is missing")
                return record
            order = await self._order(session, context, po_id, lock=True)
            if order.version != payload.expected_po_version:
                raise PurchasingConflict("Purchase Order version is stale")
            record = await self.repository.purchase_return(
                session, context.company.id, return_id, lock=True
            )
            if record is None or record.purchase_order_id != order.id:
                raise PurchasingNotFound("Purchase Return was not found")
            if record.version != payload.expected_return_version:
                raise PurchasingConflict("Purchase Return version is stale")
            event_type: EventType
            if (
                action == "request_authorization"
                and record.status == "requested"
                and record.authorization_status == "not_requested"
            ):
                record.authorization_status = "requested"
                event_type = (
                    EventType.PURCHASING_PURCHASE_RETURN_AUTHORIZATION_REQUESTED
                )
            elif action == "authorize" and record.authorization_status == "requested":
                authorization_reference = (
                    payload.vendor_authorization_reference or ""
                ).strip()
                if not authorization_reference:
                    raise PurchasingValidation(
                        "Vendor authorization reference is required"
                    )
                record.status, record.authorization_status = "authorized", "received"
                record.vendor_authorization_reference = authorization_reference
                record.authorization_at = payload.occurred_at
                event_type = EventType.PURCHASING_PURCHASE_RETURN_AUTHORIZED
            elif action == "deny" and record.authorization_status == "requested":
                record.status, record.authorization_status = "denied", "denied"
                record.authorization_at = payload.occurred_at
                event_type = EventType.PURCHASING_PURCHASE_RETURN_DENIED
            elif (
                action == "mark_ready"
                and record.status in {"requested", "authorized"}
                and record.authorization_status in {"received", "not_required"}
            ):
                record.status = "return_ready"
                event_type = EventType.PURCHASING_PURCHASE_RETURN_READY
            elif action == "mark_returned" and record.status == "return_ready":
                record.status, record.returned_at = "returned", payload.occurred_at
                event_type = EventType.PURCHASING_PURCHASE_RETURN_RETURNED
            elif action == "vendor_received" and record.status == "returned":
                record.status, record.vendor_received_at = (
                    "received_by_vendor",
                    payload.occurred_at,
                )
                event_type = EventType.PURCHASING_PURCHASE_RETURN_VENDOR_RECEIVED
            elif action == "close" and record.status in {
                "returned",
                "received_by_vendor",
            }:
                record.status, record.closed_at = "closed", payload.occurred_at
                event_type = EventType.PURCHASING_PURCHASE_RETURN_CLOSED
            elif action == "cancel" and record.status in {
                "requested",
                "authorized",
                "denied",
                "return_ready",
            }:
                record.status, record.canceled_at = "canceled", payload.occurred_at
                event_type = EventType.PURCHASING_PURCHASE_RETURN_CANCELED
            else:
                raise PurchasingValidation("Purchase Return transition is not allowed")
            record.vendor_instructions = payload.note
            record.updated_by_user_id, record.updated_at = context.user.id, now()
            record.version += 1
            order.version += 1
            order.updated_at = record.updated_at
            self._receipt(
                session,
                context,
                operation,
                payload.idempotency_key,
                data,
                "purchase_return",
                record.id,
            )
            self._event(
                session,
                context,
                event_type,
                "purchase_return",
                record.id,
                order.branch_id,
                {
                    "purchase_order_id": str(order.id),
                    "purchase_return_id": str(record.id),
                    "status": record.status,
                    "authorization_status": record.authorization_status,
                    "version": record.version,
                },
            )
        return record

    async def terminal_disposition(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        po_id: UUID,
        action: str,
        payload: PurchaseOrderDispositionCommand,
    ) -> PurchaseOrderDispositionEvidence:
        data = {
            "po_id": str(po_id),
            "action": action,
            **payload.model_dump(mode="json"),
        }
        operation = f"po.disposition.{action}"
        async with session.begin():
            replay = await self._replay(
                session,
                context,
                operation,
                payload.idempotency_key,
                data,
                "purchase_order_disposition",
            )
            if replay:
                record = await self.repository.disposition(
                    session, context.company.id, po_id
                )
                if record is None or record.id != replay:
                    raise PurchasingConflict("Disposition replay target is missing")
                return record
            if not payload.confirm_terminal_action:
                raise PurchasingValidation(
                    "Explicit terminal-action confirmation is required"
                )
            order = await self._order(session, context, po_id, lock=True)
            if order.version != payload.expected_po_version:
                raise PurchasingConflict("Purchase Order version is stale")
            if order.effective_revision != payload.expected_effective_revision:
                raise PurchasingConflict("Purchase Order effective revision is stale")
            if order.status in {"closed", "cancelled"}:
                raise PurchasingConflict(
                    "Purchase Order already has a terminal disposition"
                )
            if await self.repository.disposition(session, order.company_id, order.id):
                raise PurchasingConflict(
                    "Purchase Order disposition evidence already exists"
                )
            changes = await self.repository.change_orders(
                session, order.company_id, order.id
            )
            if any(item.status == "requested" for item in changes):
                raise PurchasingValidation(
                    "Pending Purchase Order changes block disposition"
                )
            discrepancies = await self.repository.discrepancies(
                session, order.company_id, order.id
            )
            if any(item.status == "open" for item in discrepancies):
                raise PurchasingValidation(
                    "Unresolved receiving discrepancies block disposition"
                )
            returns = await self.repository.purchase_returns(
                session, order.company_id, order.id
            )
            active_return_states = {
                "requested",
                "authorized",
                "return_ready",
                "returned",
                "received_by_vendor",
            }
            if any(item.status in active_return_states for item in returns):
                raise PurchasingValidation("Active Purchase Returns block disposition")
            lines = await self.repository.lines(session, order.company_id, order.id)
            accepted = await self.repository.accepted_totals(
                session, order.company_id, order.id
            )
            quantity_evidence: list[dict[str, object]] = []
            total_accepted = Decimal(0)
            total_outstanding = Decimal(0)
            total_previously_canceled = Decimal(0)
            for line in lines:
                received = accepted.get(line.id, Decimal(0))
                unfulfilled = max(line.quantity - received, Decimal(0))
                previously_canceled = unfulfilled if line.is_cancelled else Decimal(0)
                outstanding = Decimal(0) if line.is_cancelled else unfulfilled
                total_accepted += received
                total_outstanding += outstanding
                total_previously_canceled += previously_canceled
                quantity_evidence.append(
                    {
                        "purchase_order_line_id": str(line.id),
                        "line_number": line.line_number,
                        "effective_ordered_quantity": str(line.quantity),
                        "accepted_received_quantity": str(received),
                        "previously_canceled": line.is_cancelled,
                        "prior_outstanding_quantity": str(max(outstanding, Decimal(0))),
                        "canceled_remainder_quantity": str(previously_canceled),
                    }
                )
            timestamp = now()
            if action == "complete":
                if order.status != "issued":
                    raise PurchasingValidation(
                        "Only an issued Purchase Order may be completed"
                    )
                if total_outstanding != 0 or total_previously_canceled != 0:
                    raise PurchasingValidation(
                        "Purchase Order is not fully satisfied by authoritative receiving facts"
                    )
                disposition = "fully_satisfied"
                terminal_status = "closed"
                event_type = EventType.PURCHASING_PURCHASE_ORDER_COMPLETED
            elif action == "cancel":
                if order.status not in {"draft", "submitted", "approved", "issued"}:
                    raise PurchasingValidation(
                        "Purchase Order cannot be canceled from current state"
                    )
                if (
                    order.status == "issued"
                    and total_outstanding == 0
                    and total_previously_canceled == 0
                ):
                    raise PurchasingValidation(
                        "A fully received Purchase Order cannot be canceled"
                    )
                if total_accepted == 0:
                    disposition = "canceled_before_receipt"
                else:
                    disposition = "remainder_canceled"
                for line_evidence in quantity_evidence:
                    prior_canceled = Decimal(
                        str(line_evidence["canceled_remainder_quantity"])
                    )
                    open_remainder = Decimal(
                        str(line_evidence["prior_outstanding_quantity"])
                    )
                    line_evidence["canceled_remainder_quantity"] = str(
                        prior_canceled + open_remainder
                    )
                terminal_status = "cancelled"
                event_type = (
                    EventType.PURCHASING_PURCHASE_ORDER_REMAINDER_CANCELED
                    if disposition == "remainder_canceled"
                    else EventType.PURCHASING_PURCHASE_ORDER_CANCELLED
                )
            else:
                raise PurchasingValidation("Unsupported terminal disposition")
            evidence_payload = {
                "schema_version": 1,
                "company_id": str(order.company_id),
                "branch_id": str(order.branch_id),
                "purchase_order_id": str(order.id),
                "purchase_order_version": order.version,
                "effective_revision": order.effective_revision,
                "prior_status": order.status,
                "disposition": disposition,
                "reason": payload.reason.strip(),
                "quantity_evidence": quantity_evidence,
                "actor_user_id": str(context.user.id),
                "occurred_at": timestamp.isoformat(),
            }
            record = PurchaseOrderDispositionEvidence(
                company_id=order.company_id,
                branch_id=order.branch_id,
                purchase_order_id=order.id,
                purchase_order_version=order.version,
                effective_revision=order.effective_revision,
                prior_status=order.status,
                disposition=disposition,
                reason=payload.reason.strip(),
                quantity_evidence=quantity_evidence,
                evidence_digest=digest(evidence_payload),
                actor_user_id=context.user.id,
                occurred_at=timestamp,
            )
            session.add(record)
            await session.flush()
            order.status = terminal_status
            order.closed_by_user_id = context.user.id
            order.closed_at = timestamp
            order.lifecycle_reason = payload.reason.strip()
            order.version += 1
            order.updated_at = timestamp
            self._receipt(
                session,
                context,
                operation,
                payload.idempotency_key,
                data,
                "purchase_order_disposition",
                record.id,
            )
            self._event(
                session,
                context,
                event_type,
                "purchase_order",
                order.id,
                order.branch_id,
                {
                    "purchase_order_id": str(order.id),
                    "purchase_order_version": order.version,
                    "effective_revision": order.effective_revision,
                    "disposition": disposition,
                    "evidence_digest": record.evidence_digest,
                },
            )
        return record

    async def request_change(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        po_id: UUID,
        payload: RequestPurchaseOrderChangeCommand,
    ) -> PurchaseOrderChangeOrder:
        data = {"po_id": str(po_id), **payload.model_dump(mode="json")}
        async with session.begin():
            replay = await self._replay(
                session,
                context,
                "po.change.request",
                payload.idempotency_key,
                data,
                "purchase_order_change",
            )
            if replay:
                record = await self.repository.change_order(
                    session, context.company.id, replay
                )
                if record is None:
                    raise PurchasingConflict("Change replay target is missing")
                return record
            order = await self._order(session, context, po_id, lock=True)
            if order.status not in {"issued", "closed"}:
                raise PurchasingValidation(
                    "Only an authoritative issued Purchase Order may be revised"
                )
            if (
                order.version != payload.expected_po_version
                or order.effective_revision != payload.base_revision
            ):
                raise PurchasingConflict("Purchase Order change base is stale")
            lines = await self.repository.lines(session, order.company_id, order.id)
            line_ids = {line.id for line in lines}
            for change in payload.changes:
                if (
                    change.operation != "add_line"
                    and change.operation != "set_expected_date"
                    and change.line_id not in line_ids
                ):
                    raise PurchasingValidation(
                        "Change references an invalid Purchase Order line"
                    )
                if change.operation == "set_quantity" and change.quantity is None:
                    raise PurchasingValidation("Quantity change requires quantity")
                if change.operation == "set_unit_cost" and change.unit_cost is None:
                    raise PurchasingValidation("Price change requires unit cost")
                if change.operation == "add_line" and (
                    change.quantity is None
                    or change.unit is None
                    or change.unit_cost is None
                    or (
                        change.inventory_item_id is None
                        and not (change.description or "").strip()
                    )
                ):
                    raise PurchasingValidation(
                        "Added line requires complete identity, quantity, unit, and cost"
                    )
            changes = payload.model_dump(mode="json")["changes"]
            record = PurchaseOrderChangeOrder(
                company_id=order.company_id,
                branch_id=order.branch_id,
                purchase_order_id=order.id,
                change_identity=payload.change_identity,
                base_revision=payload.base_revision,
                proposed_changes=changes,
                reason=payload.reason,
                requested_by_user_id=context.user.id,
                evidence_digest=digest(data),
            )
            session.add(record)
            await session.flush()
            self._receipt(
                session,
                context,
                "po.change.request",
                payload.idempotency_key,
                data,
                "purchase_order_change",
                record.id,
            )
            self._event(
                session,
                context,
                EventType.PURCHASING_PURCHASE_ORDER_CHANGE_REQUESTED,
                "purchase_order_change",
                record.id,
                order.branch_id,
                {
                    "purchase_order_id": str(order.id),
                    "base_revision": record.base_revision,
                    "evidence_digest": record.evidence_digest,
                },
            )
        return record

    async def decide_change(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        po_id: UUID,
        change_id: UUID,
        action: str,
        payload: DecidePurchaseOrderChangeCommand,
    ) -> PurchaseOrderChangeOrder:
        data = {
            "po_id": str(po_id),
            "change_id": str(change_id),
            "action": action,
            **payload.model_dump(mode="json"),
        }
        async with session.begin():
            replay = await self._replay(
                session,
                context,
                f"po.change.{action}",
                payload.idempotency_key,
                data,
                "purchase_order_change",
            )
            if replay:
                record = await self.repository.change_order(
                    session, context.company.id, replay
                )
                if record is None:
                    raise PurchasingConflict("Change replay target is missing")
                return record
            order = await self._order(session, context, po_id, lock=True)
            record = await self.repository.change_order(
                session, context.company.id, change_id, lock=True
            )
            if record is None or record.purchase_order_id != order.id:
                raise PurchasingNotFound("Purchase Order change was not found")
            if record.status != "requested":
                raise PurchasingConflict("Purchase Order change is already decided")
            if record.requested_by_user_id == context.user.id:
                raise PurchasingValidation(
                    "Requester may not approve or reject their own Purchase Order change"
                )
            if (
                order.version != payload.expected_po_version
                or order.effective_revision != payload.expected_base_revision
                or record.base_revision != order.effective_revision
            ):
                raise PurchasingConflict("Purchase Order change base is stale")
            if action == "reject":
                record.status = "rejected"
                record.decided_by_user_id = context.user.id
                record.decided_at = now()
                event_type = EventType.PURCHASING_PURCHASE_ORDER_CHANGE_REJECTED
            elif action == "approve":
                existing_revisions = await self.repository.revisions(
                    session, order.company_id, order.id
                )
                if not existing_revisions:
                    issuance = await self.repository.evidence(
                        session, order.company_id, order.id
                    )
                    if issuance is None:
                        raise PurchasingValidation(
                            "Immutable issuance evidence is required before revision"
                        )
                    session.add(
                        PurchaseOrderRevision(
                            company_id=order.company_id,
                            branch_id=order.branch_id,
                            purchase_order_id=order.id,
                            revision_number=1,
                            predecessor_revision=None,
                            change_order_id=None,
                            effective_snapshot=issuance.snapshot,
                            evidence_digest=issuance.digest,
                            effective_by_user_id=issuance.issued_by_user_id,
                            effective_at=issuance.issued_at,
                        )
                    )
                lines = {
                    line.id: line
                    for line in await self.repository.lines(
                        session, order.company_id, order.id
                    )
                }
                received = await self.repository.accepted_totals(
                    session, order.company_id, order.id
                )
                for change in record.proposed_changes:
                    op, raw_id = change["operation"], change.get("line_id")
                    line = lines.get(UUID(str(raw_id))) if raw_id else None
                    if op == "set_quantity" and line:
                        quantity = Decimal(str(change["quantity"]))
                        accepted = received.get(line.id, Decimal(0))
                        if quantity < accepted:
                            raise PurchasingValidation(
                                "Ordered quantity cannot fall below accepted receiving evidence"
                            )
                        line.quantity = quantity
                        line.extended_cost = quantity * line.unit_cost
                        line.version += 1
                    elif op == "set_unit_cost" and line:
                        if received.get(line.id, Decimal(0)) > 0:
                            raise PurchasingValidation(
                                "POST_RECEIPT_PRICE_CHANGE_POLICY_REQUIRED: "
                                "unit cost cannot change after accepted receiving "
                                "without a separately approved valuation or prospective policy"
                            )
                        line.unit_cost = Decimal(str(change["unit_cost"]))
                        line.extended_cost = line.quantity * line.unit_cost
                        line.version += 1
                    elif op == "cancel_line" and line:
                        if received.get(line.id, Decimal(0)) > 0:
                            raise PurchasingValidation(
                                "A received line cannot be canceled"
                            )
                        line.is_cancelled = True
                        line.version += 1
                    elif op == "set_expected_date":
                        order.expected_date = (
                            date.fromisoformat(str(change["expected_date"]))
                            if change.get("expected_date")
                            else None
                        )
                    elif op == "add_line":
                        item_id = (
                            UUID(str(change["inventory_item_id"]))
                            if change.get("inventory_item_id")
                            else None
                        )
                        await self._inventory_item(session, order.company_id, item_id)
                        quantity, unit_cost = (
                            Decimal(str(change["quantity"])),
                            Decimal(str(change["unit_cost"])),
                        )
                        new_line = PurchaseOrderLine(
                            company_id=order.company_id,
                            purchase_order_id=order.id,
                            line_number=await self.repository.next_line_number(
                                session, order.company_id, order.id
                            ),
                            inventory_item_id=item_id,
                            description=change.get("description") or "",
                            quantity=quantity,
                            unit=change["unit"],
                            unit_cost=unit_cost,
                            extended_cost=quantity * unit_cost,
                            expected_date=change.get("expected_date"),
                            created_by_user_id=context.user.id,
                        )
                        session.add(new_line)
                new_revision = order.effective_revision + 1
                snapshot = await self._effective_snapshot(session, order)
                revision = PurchaseOrderRevision(
                    company_id=order.company_id,
                    branch_id=order.branch_id,
                    purchase_order_id=order.id,
                    revision_number=new_revision,
                    predecessor_revision=order.effective_revision,
                    change_order_id=record.id,
                    effective_snapshot=snapshot,
                    evidence_digest=digest(snapshot),
                    effective_by_user_id=context.user.id,
                )
                session.add(revision)
                record.status = "approved"
                record.decided_by_user_id = context.user.id
                record.decided_at = now()
                record.effective_revision = new_revision
                order.effective_revision = new_revision
                order.version += 1
                order.updated_at = now()
                self._event(
                    session,
                    context,
                    EventType.PURCHASING_PURCHASE_ORDER_REVISED,
                    "purchase_order",
                    order.id,
                    order.branch_id,
                    {
                        "purchase_order_id": str(order.id),
                        "revision": new_revision,
                        "predecessor_revision": new_revision - 1,
                        "change_order_id": str(record.id),
                    },
                )
                event_type = EventType.PURCHASING_PURCHASE_ORDER_CHANGE_APPROVED
            else:
                raise PurchasingValidation("Unsupported Purchase Order change decision")
            self._receipt(
                session,
                context,
                f"po.change.{action}",
                payload.idempotency_key,
                data,
                "purchase_order_change",
                record.id,
            )
            self._event(
                session,
                context,
                event_type,
                "purchase_order_change",
                record.id,
                order.branch_id,
                {
                    "purchase_order_id": str(order.id),
                    "status": record.status,
                    "effective_revision": record.effective_revision,
                },
            )
        return record

    async def _effective_snapshot(
        self, session: AsyncSession, order: PurchaseOrder
    ) -> dict[str, object]:
        lines = await self.repository.lines(session, order.company_id, order.id)
        return {
            "schema_version": 1,
            "purchase_order_id": str(order.id),
            "revision": order.effective_revision + 1,
            "vendor_id": str(order.vendor_id),
            "currency": order.currency,
            "expected_date": str(order.expected_date) if order.expected_date else None,
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
                    "is_cancelled": line.is_cancelled,
                }
                for line in lines
            ],
        }

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
        receipts = await self.repository.receiving_events(
            session, order.company_id, order.id
        )
        discrepancies = await self.repository.discrepancies(
            session, order.company_id, order.id
        )
        purchase_returns = await self.repository.purchase_returns(
            session, order.company_id, order.id
        )
        change_orders = await self.repository.change_orders(
            session, order.company_id, order.id
        )
        revisions = await self.repository.revisions(session, order.company_id, order.id)
        disposition = await self.repository.disposition(
            session, order.company_id, order.id
        )
        totals = await self.repository.accepted_totals(
            session, order.company_id, order.id
        )
        open_discrepancy = any(item.status == "open" for item in discrepancies)
        receipt_items = []
        for receipt in receipts:
            receipt_items.append(
                ReceiptItem.model_validate(receipt).model_copy(
                    update={
                        "lines": tuple(
                            ReceiptLineItem.model_validate(item)
                            for item in await self.repository.receipt_lines(
                                session, order.company_id, receipt.id
                            )
                        )
                    }
                )
            )
        return_items = []
        for item in purchase_returns:
            committed = await self.repository.committed_return_quantity(
                session, order.company_id, item.receipt_line_id
            )
            return_items.append(
                PurchaseReturnItem.model_validate(item).model_copy(
                    update={
                        "remaining_returnable_quantity": max(
                            item.accepted_quantity_snapshot - committed, Decimal(0)
                        )
                    }
                )
            )
        return PurchaseOrderItem.model_validate(order).model_copy(
            update={
                "lines": tuple(
                    PurchaseOrderLineItem.model_validate(line).model_copy(
                        update={
                            "cumulative_accepted_quantity": totals.get(
                                line.id, Decimal(0)
                            ),
                            "outstanding_quantity": (
                                Decimal(0)
                                if disposition is not None or line.is_cancelled
                                else line.quantity - totals.get(line.id, Decimal(0))
                            ),
                        }
                    )
                    for line in lines
                ),
                "issuance_digest": evidence.digest if evidence else None,
                "receiving_status": self._receiving_state(
                    lines, totals, open_discrepancy
                ),
                "receipts": tuple(receipt_items),
                "discrepancies": tuple(
                    DiscrepancyItem.model_validate(item) for item in discrepancies
                ),
                "returns": tuple(return_items),
                "change_orders": tuple(
                    PurchaseOrderChangeItem.model_validate(item)
                    for item in change_orders
                ),
                "revisions": tuple(
                    PurchaseOrderRevisionItem.model_validate(item) for item in revisions
                ),
                "disposition": PurchaseOrderDispositionItem.model_validate(disposition)
                if disposition
                else None,
            }
        )

    @staticmethod
    def _receiving_state(
        lines: Any, totals: dict[UUID, Decimal], discrepancy: bool
    ) -> str:
        line_list = tuple(lines)
        accepted = sum(
            (totals.get(line.id, Decimal(0)) for line in line_list), Decimal(0)
        )
        if discrepancy:
            return "discrepancy_outstanding"
        if accepted == 0:
            return "not_received"
        if line_list and all(
            totals.get(line.id, Decimal(0)) == line.quantity for line in line_list
        ):
            return "fully_received"
        return "partially_received"

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
