import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts_payable.models import (
    BillLine,
    BillRevision,
    VendorBill,
    VendorCredit,
    VendorSourceMapping,
)
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.permissions.authorization import AuthorizationContext
from app.purchasing.models import (
    PurchaseOrder,
    PurchaseOrderDiscrepancy,
    PurchaseOrderLine,
    PurchaseOrderReceipt,
    PurchaseOrderReceiptLine,
    PurchaseReturn,
)

from .errors import (
    ProcurementMatchingConflict,
    ProcurementMatchingNotFound,
    ProcurementMatchingValidation,
)
from .models import ProcurementMatch, ProcurementMatchException, ProcurementMatchLine
from .schemas import (
    EvaluateMatchCommand,
    MatchExceptionItem,
    MatchItem,
    MatchLineItem,
    ResolveMatchExceptionCommand,
    VendorPerformanceItem,
    VendorPerformanceReport,
)


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class ProcurementMatchingService:
    async def evaluate(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        payload: EvaluateMatchCommand,
    ) -> MatchItem:
        async with session.begin():
            if session.get_bind().dialect.name == "postgresql":
                await session.execute(
                    text(
                        "SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"
                    ),
                    {
                        "identity": f"procurement-match:{context.company.id}:{payload.vendor_bill_id}"
                    },
                )
            replay = await session.scalar(
                select(ProcurementMatch).where(
                    ProcurementMatch.company_id == context.company.id,
                    ProcurementMatch.idempotency_key == payload.idempotency_key,
                )
            )
            if replay is not None:
                if (
                    replay.purchase_order_id != payload.purchase_order_id
                    or replay.vendor_bill_id != payload.vendor_bill_id
                ):
                    raise ProcurementMatchingConflict(
                        "Idempotency key conflicts with different matching evidence"
                    )
                return await self._item(session, replay)
            existing_bill_match = await session.scalar(
                select(ProcurementMatch)
                .where(
                    ProcurementMatch.company_id == context.company.id,
                    ProcurementMatch.vendor_bill_id == payload.vendor_bill_id,
                    ProcurementMatch.superseded_at.is_(None),
                )
                .with_for_update()
            )
            if (
                existing_bill_match is not None
                and existing_bill_match.purchase_order_id
                != payload.purchase_order_id
            ):
                raise ProcurementMatchingConflict(
                    "Vendor Bill already has contradictory matching authority"
                )
            order = await session.scalar(
                select(PurchaseOrder)
                .where(
                    PurchaseOrder.company_id == context.company.id,
                    PurchaseOrder.id == payload.purchase_order_id,
                )
                .with_for_update()
            )
            bill = await session.scalar(
                select(VendorBill)
                .where(
                    VendorBill.company_id == context.company.id,
                    VendorBill.id == payload.vendor_bill_id,
                )
                .with_for_update()
            )
            if (
                order is None
                or bill is None
                or not context.can_access_branch(order.branch_id)
                or not context.can_access_branch(bill.branch_id)
            ):
                raise ProcurementMatchingNotFound("PO or Vendor Bill was not found")
            if order.branch_id != bill.branch_id:
                raise ProcurementMatchingValidation(
                    "Purchase Order and Vendor Bill Branch conflict"
                )
            if (
                order.version != payload.expected_purchase_order_version
                or bill.version != payload.expected_bill_version
            ):
                raise ProcurementMatchingConflict("PO or Vendor Bill evidence is stale")
            if bill.status not in {"draft", "submitted"}:
                raise ProcurementMatchingValidation(
                    "Only an unapproved Vendor Bill may be matched"
                )
            revision = await session.scalar(
                select(BillRevision).where(
                    BillRevision.company_id == context.company.id,
                    BillRevision.bill_id == bill.id,
                    BillRevision.revision == bill.current_revision,
                )
            )
            if revision is None:
                raise ProcurementMatchingConflict(
                    "Vendor Bill revision evidence is missing"
                )
            bill_lines = tuple(
                (
                    await session.scalars(
                        select(BillLine)
                        .where(
                            BillLine.company_id == context.company.id,
                            BillLine.revision_id == revision.id,
                        )
                        .order_by(BillLine.position)
                    )
                ).all()
            )
            po_lines = {
                row.id: row
                for row in (
                    await session.scalars(
                        select(PurchaseOrderLine).where(
                            PurchaseOrderLine.company_id == context.company.id,
                            PurchaseOrderLine.purchase_order_id == order.id,
                        )
                    )
                ).all()
            }
            receipt_rows = tuple(
                (
                    await session.scalars(
                        select(PurchaseOrderReceiptLine)
                        .join(
                            PurchaseOrderReceipt,
                            PurchaseOrderReceipt.id
                            == PurchaseOrderReceiptLine.receipt_id,
                        )
                        .where(
                            PurchaseOrderReceiptLine.company_id == context.company.id,
                            PurchaseOrderReceipt.purchase_order_id == order.id,
                        )
                    )
                ).all()
            )
            returns = tuple(
                (
                    await session.scalars(
                        select(PurchaseReturn).where(
                            PurchaseReturn.company_id == context.company.id,
                            PurchaseReturn.purchase_order_id == order.id,
                            PurchaseReturn.status.in_(
                                ("returned", "received_by_vendor", "closed")
                            ),
                        )
                    )
                ).all()
            )
            return_ids = tuple(str(row.id) for row in returns)
            credits = (
                tuple(
                    (
                        await session.scalars(
                            select(VendorCredit).where(
                                VendorCredit.company_id == context.company.id,
                                VendorCredit.vendor_id == bill.vendor_id,
                                VendorCredit.source_system == "purchasing_return",
                                VendorCredit.source_identity.in_(return_ids),
                            )
                        )
                    ).all()
                )
                if return_ids
                else ()
            )
            source_digest = self._source_evidence_digest(
                order=order,
                bill=bill,
                bill_revision=revision,
                bill_lines=bill_lines,
                po_lines=tuple(po_lines.values()),
                receipt_rows=receipt_rows,
                returns=returns,
                credits=credits,
            )
            evaluation_sequence = 1
            supersedes_match_id: UUID | None = None
            if existing_bill_match is not None:
                if existing_bill_match.source_evidence_digest == source_digest:
                    return await self._item(session, existing_bill_match)
                existing_bill_match.superseded_at = datetime.now(timezone.utc)
                evaluation_sequence = existing_bill_match.evaluation_sequence + 1
                supersedes_match_id = existing_bill_match.id
            mapping = await session.scalar(
                select(VendorSourceMapping).where(
                    VendorSourceMapping.company_id == context.company.id,
                    VendorSourceMapping.vendor_id == bill.vendor_id,
                    VendorSourceMapping.source_system == "purchasing",
                    VendorSourceMapping.source_company_id == str(context.company.id),
                    VendorSourceMapping.source_vendor_id == str(order.vendor_id),
                )
            )
            initial_state: str | None = None
            if mapping is None:
                initial_state = "vendor_conflict"
            elif order.currency != bill.currency:
                initial_state = "currency_conflict"
            match = ProcurementMatch(
                company_id=context.company.id,
                branch_id=order.branch_id,
                purchase_order_id=order.id,
                vendor_bill_id=bill.id,
                operational_vendor_id=order.vendor_id,
                accounting_vendor_id=bill.vendor_id,
                state=initial_state or "matched",
                admission_state="blocked" if initial_state else "eligible",
                purchase_order_version=order.version,
                bill_version=bill.version,
                source_evidence_digest=source_digest,
                evaluation_sequence=evaluation_sequence,
                supersedes_match_id=supersedes_match_id,
                evidence_digest="0" * 64,
                idempotency_key=payload.idempotency_key,
                evaluated_by_user_id=context.user.id,
            )
            session.add(match)
            await session.flush()
            exceptions: list[ProcurementMatchException] = []
            if initial_state:
                exceptions.append(
                    self._exception(
                        match,
                        initial_state,
                        "same mapped Vendor and currency",
                        f"operational_vendor={order.vendor_id}; ap_vendor={bill.vendor_id}; po_currency={order.currency}; bill_currency={bill.currency}",
                    )
                )
            matched_po_lines: set[UUID] = set()
            states: list[str] = []
            evidence: list[object] = []
            for bill_line in bill_lines:
                try:
                    po_line_id = UUID(bill_line.purchasing_reference or "")
                except ValueError:
                    exceptions.append(
                        self._exception(
                            match,
                            "item_conflict",
                            "PO line UUID purchasing_reference",
                            str(bill_line.purchasing_reference),
                        )
                    )
                    states.append("item_conflict")
                    continue
                po_line = po_lines.get(po_line_id)
                if po_line is None:
                    exceptions.append(
                        self._exception(
                            match,
                            "item_conflict",
                            "Bill line references a line on this PO",
                            str(po_line_id),
                        )
                    )
                    states.append("item_conflict")
                    continue
                matched_po_lines.add(po_line.id)
                accepted = sum(
                    (
                        row.accepted_quantity
                        for row in receipt_rows
                        if row.purchase_order_line_id == po_line.id
                    ),
                    Decimal(0),
                )
                returned = sum(
                    (
                        row.quantity
                        for row in returns
                        if row.purchase_order_line_id == po_line.id
                    ),
                    Decimal(0),
                )
                net = accepted - returned
                billed_unit = (bill_line.net_amount / bill_line.quantity).quantize(
                    Decimal("0.0001")
                )
                quantity_variance = bill_line.quantity - net
                price_variance = billed_unit - po_line.unit_cost
                line_return_ids = {
                    str(row.id)
                    for row in returns
                    if row.purchase_order_line_id == po_line.id
                }
                linked_credits = tuple(
                    credit
                    for credit in credits
                    if credit.source_identity in line_return_ids
                )
                if accepted == 0:
                    state = "unreceived_billing"
                elif returned > 0 and bill_line.quantity > net:
                    state = (
                        "requires_review" if linked_credits else "return_pending_credit"
                    )
                elif bill_line.quantity > net:
                    state = "overbilled"
                elif quantity_variance != 0:
                    state = "quantity_variance"
                elif price_variance != 0:
                    state = "price_variance"
                elif accepted < po_line.quantity:
                    state = "partially_matched"
                else:
                    state = "matched"
                line_evidence = {
                    "po_line_id": str(po_line.id),
                    "bill_line_id": str(bill_line.id),
                    "ordered": str(po_line.quantity),
                    "received": str(accepted),
                    "returned": str(returned),
                    "net_accepted": str(net),
                    "billed": str(bill_line.quantity),
                    "po_unit_cost": str(po_line.unit_cost),
                    "billed_unit_cost": str(billed_unit),
                    "currency": bill.currency,
                    "receipt_ids": sorted(
                        str(row.id)
                        for row in receipt_rows
                        if row.purchase_order_line_id == po_line.id
                    ),
                    "vendor_credit_evidence": sorted(
                        (
                            str(credit.id),
                            credit.source_identity,
                            str(credit.amount),
                            credit.currency,
                            credit.source_digest,
                        )
                        for credit in linked_credits
                    ),
                }
                row = ProcurementMatchLine(
                    company_id=context.company.id,
                    match_id=match.id,
                    purchase_order_line_id=po_line.id,
                    receipt_line_id=self._receipt_reference(bill_line, receipt_rows),
                    bill_line_id=bill_line.id,
                    inventory_item_id=po_line.inventory_item_id,
                    ordered_quantity=po_line.quantity,
                    received_quantity=accepted,
                    returned_quantity=returned,
                    net_accepted_quantity=net,
                    billed_quantity=bill_line.quantity,
                    po_unit_cost=po_line.unit_cost,
                    billed_unit_cost=billed_unit,
                    billed_net_amount=bill_line.net_amount,
                    billed_tax_amount=bill_line.tax_amount,
                    quantity_variance=quantity_variance,
                    price_variance=price_variance,
                    state=state,
                    evidence_digest=digest(line_evidence),
                )
                session.add(row)
                await session.flush()
                evidence.append(line_evidence)
                states.append(state)
                if state != "matched":
                    exceptions.append(
                        self._exception(
                            match,
                            self._exception_category(state),
                            f"received={net}; unit_cost={po_line.unit_cost}",
                            f"billed={bill_line.quantity}; unit_cost={billed_unit}",
                            row.id,
                        )
                    )
            for po_line in po_lines.values():
                accepted = sum(
                    (
                        row.accepted_quantity
                        for row in receipt_rows
                        if row.purchase_order_line_id == po_line.id
                    ),
                    Decimal(0),
                )
                if accepted > 0 and po_line.id not in matched_po_lines:
                    exceptions.append(
                        self._exception(
                            match,
                            "missing_bill",
                            "accepted receipt has Vendor Bill line",
                            f"unbilled_received={accepted}; po_line={po_line.id}",
                        )
                    )
                    states.append("unbilled_receipt")
            session.add_all(exceptions)
            match.state = self._aggregate_state(initial_state, states)
            match.admission_state = (
                "eligible" if match.state == "matched" else "review_required"
            )
            match.evidence_digest = digest(
                {
                    "definition_version": 1,
                    "po": str(order.id),
                    "po_version": order.version,
                    "bill": str(bill.id),
                    "bill_version": bill.version,
                    "source_evidence_digest": source_digest,
                    "evaluation_sequence": evaluation_sequence,
                    "supersedes_match_id": (
                        str(supersedes_match_id) if supersedes_match_id else None
                    ),
                    "vendor_mapping": str(mapping.id) if mapping else None,
                    "evidence": evidence,
                    "exceptions": [
                        (row.category, row.expected_evidence, row.actual_evidence)
                        for row in exceptions
                    ],
                }
            )
            self._event(
                session,
                context,
                EventType.PROCUREMENT_MATCH_EVALUATED,
                match,
                {
                    "state": match.state,
                    "admission_state": match.admission_state,
                    "evidence_digest": match.evidence_digest,
                    "exception_count": len(exceptions),
                },
            )
            result = await self._item(session, match)
        return result

    async def resolve(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        match_id: UUID,
        exception_id: UUID,
        payload: ResolveMatchExceptionCommand,
    ) -> MatchItem:
        async with session.begin():
            resolution_digest = digest(
                {
                    "match_id": str(match_id),
                    "exception_id": str(exception_id),
                    "resolution": payload.resolution,
                    "note": payload.note,
                }
            )
            replay = await session.scalar(
                select(ProcurementMatchException).where(
                    ProcurementMatchException.company_id == context.company.id,
                    ProcurementMatchException.resolution_idempotency_key
                    == payload.idempotency_key,
                )
            )
            if replay is not None:
                if (
                    replay.match_id != match_id
                    or replay.id != exception_id
                    or replay.resolution_payload_digest != resolution_digest
                ):
                    raise ProcurementMatchingConflict(
                        "Resolution idempotency key conflicts with different evidence"
                    )
                replay_match = await session.get(ProcurementMatch, replay.match_id)
                if replay_match is None:
                    raise ProcurementMatchingConflict(
                        "Resolution authority is internally inconsistent"
                    )
                return await self._item(session, replay_match)
            match = await session.scalar(
                select(ProcurementMatch)
                .where(
                    ProcurementMatch.company_id == context.company.id,
                    ProcurementMatch.id == match_id,
                )
                .with_for_update()
            )
            exception = await session.scalar(
                select(ProcurementMatchException)
                .where(
                    ProcurementMatchException.company_id == context.company.id,
                    ProcurementMatchException.id == exception_id,
                    ProcurementMatchException.match_id == match_id,
                )
                .with_for_update()
            )
            if (
                match is None
                or exception is None
                or not context.can_access_branch(match.branch_id)
            ):
                raise ProcurementMatchingNotFound("Match exception was not found")
            if match.superseded_at is not None:
                raise ProcurementMatchingConflict(
                    "Match evidence was superseded by newer source authority"
                )
            if (
                match.version != payload.expected_match_version
                or exception.version != payload.expected_exception_version
            ):
                raise ProcurementMatchingConflict("Match exception evidence is stale")
            if exception.status == "resolved":
                if (
                    exception.resolution == payload.resolution
                    and exception.resolution_note == payload.note
                ):
                    return await self._item(session, match)
                raise ProcurementMatchingConflict(
                    "Resolved exception cannot be rewritten"
                )
            if (
                payload.resolution == "accept_variance"
                and match.evaluated_by_user_id == context.user.id
            ):
                raise ProcurementMatchingValidation(
                    "Match evaluator cannot approve the same variance"
                )
            exception.status = "resolved"
            exception.resolution = payload.resolution
            exception.resolution_note = payload.note
            exception.resolution_idempotency_key = payload.idempotency_key
            exception.resolution_payload_digest = resolution_digest
            exception.resolved_by_user_id = context.user.id
            exception.resolved_at = datetime.now(timezone.utc)
            exception.version += 1
            match.version += 1
            remaining = await session.scalar(
                select(ProcurementMatchException.id).where(
                    ProcurementMatchException.company_id == context.company.id,
                    ProcurementMatchException.match_id == match.id,
                    ProcurementMatchException.id != exception.id,
                    ProcurementMatchException.status != "resolved",
                )
            )
            if remaining is None and payload.resolution == "accept_variance":
                match.admission_state = "eligible"
            elif payload.resolution in {
                "hold_bill",
                "reject_bill",
                "wait_for_receipt",
                "wait_for_bill",
                "request_vendor_credit",
                "return_goods",
                "manual_review_required",
            }:
                match.admission_state = "blocked"
            self._event(
                session,
                context,
                EventType.PROCUREMENT_MATCH_EXCEPTION_RESOLVED,
                match,
                {
                    "exception_id": str(exception.id),
                    "resolution": payload.resolution,
                    "admission_state": match.admission_state,
                },
            )
            result = await self._item(session, match)
        return result

    async def get(
        self, session: AsyncSession, *, context: AuthorizationContext, match_id: UUID
    ) -> MatchItem:
        row = await session.scalar(
            select(ProcurementMatch).where(
                ProcurementMatch.company_id == context.company.id,
                ProcurementMatch.id == match_id,
            )
        )
        if row is None or not context.can_access_branch(row.branch_id):
            raise ProcurementMatchingNotFound("Procurement match was not found")
        return await self._item(session, row)

    async def vendor_performance(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        evaluated_at: datetime,
        branch_id: UUID | None,
    ) -> VendorPerformanceReport:
        if evaluated_at.tzinfo is None:
            raise ProcurementMatchingValidation(
                "Evaluation time must include timezone authority"
            )
        if branch_id is not None and not context.can_access_branch(branch_id):
            raise ProcurementMatchingNotFound(
                "Branch performance evidence was not found"
            )
        allowed_branches = (
            (branch_id,)
            if branch_id is not None
            else tuple(context.authorized_branch_ids)
        )
        orders = tuple(
            (
                await session.scalars(
                    select(PurchaseOrder)
                    .where(
                        PurchaseOrder.company_id == context.company.id,
                        PurchaseOrder.branch_id.in_(allowed_branches),
                        PurchaseOrder.status.in_(("issued", "closed", "cancelled")),
                        PurchaseOrder.created_at <= evaluated_at,
                    )
                    .order_by(PurchaseOrder.vendor_id, PurchaseOrder.id)
                )
            ).all()
        )
        order_ids = tuple(row.id for row in orders)
        if not order_ids:
            return VendorPerformanceReport(
                definition_version=1,
                company_id=context.company.id,
                branch_id=branch_id,
                evaluated_at=evaluated_at,
                items=(),
                evidence_digest=digest({"definition_version": 1, "orders": []}),
            )
        lines = tuple(
            (
                await session.scalars(
                    select(PurchaseOrderLine).where(
                        PurchaseOrderLine.company_id == context.company.id,
                        PurchaseOrderLine.purchase_order_id.in_(order_ids),
                    )
                )
            ).all()
        )
        receipts = tuple(
            (
                await session.scalars(
                    select(PurchaseOrderReceipt).where(
                        PurchaseOrderReceipt.company_id == context.company.id,
                        PurchaseOrderReceipt.purchase_order_id.in_(order_ids),
                        PurchaseOrderReceipt.received_at <= evaluated_at,
                    )
                )
            ).all()
        )
        receipt_ids = tuple(row.id for row in receipts)
        receipt_lines = (
            tuple(
                (
                    await session.scalars(
                        select(PurchaseOrderReceiptLine).where(
                            PurchaseOrderReceiptLine.company_id == context.company.id,
                            PurchaseOrderReceiptLine.receipt_id.in_(receipt_ids),
                        )
                    )
                ).all()
            )
            if receipt_ids
            else ()
        )
        returns = tuple(
            (
                await session.scalars(
                    select(PurchaseReturn).where(
                        PurchaseReturn.company_id == context.company.id,
                        PurchaseReturn.purchase_order_id.in_(order_ids),
                        PurchaseReturn.status.in_(
                            ("returned", "received_by_vendor", "closed")
                        ),
                    )
                )
            ).all()
        )
        discrepancies = tuple(
            (
                await session.scalars(
                    select(PurchaseOrderDiscrepancy).where(
                        PurchaseOrderDiscrepancy.company_id == context.company.id,
                        PurchaseOrderDiscrepancy.purchase_order_id.in_(order_ids),
                        PurchaseOrderDiscrepancy.opened_at <= evaluated_at,
                    )
                )
            ).all()
        )
        matches = tuple(
            (
                await session.scalars(
                    select(ProcurementMatch).where(
                        ProcurementMatch.company_id == context.company.id,
                        ProcurementMatch.purchase_order_id.in_(order_ids),
                        ProcurementMatch.evaluated_at <= evaluated_at,
                        or_(
                            ProcurementMatch.superseded_at.is_(None),
                            ProcurementMatch.superseded_at > evaluated_at,
                        ),
                    )
                )
            ).all()
        )
        match_ids = tuple(row.id for row in matches)
        match_lines = (
            tuple(
                (
                    await session.scalars(
                        select(ProcurementMatchLine).where(
                            ProcurementMatchLine.company_id == context.company.id,
                            ProcurementMatchLine.match_id.in_(match_ids),
                        )
                    )
                ).all()
            )
            if match_ids
            else ()
        )
        report_items: list[VendorPerformanceItem] = []
        for vendor_id in sorted({row.vendor_id for row in orders}, key=str):
            vendor_orders = tuple(row for row in orders if row.vendor_id == vendor_id)
            vendor_order_ids = {row.id for row in vendor_orders}
            vendor_lines = tuple(
                row for row in lines if row.purchase_order_id in vendor_order_ids
            )
            line_ids = {row.id for row in vendor_lines}
            vendor_receipts = tuple(
                row for row in receipts if row.purchase_order_id in vendor_order_ids
            )
            vendor_receipt_ids = {row.id for row in vendor_receipts}
            vendor_receipt_lines = tuple(
                row for row in receipt_lines if row.receipt_id in vendor_receipt_ids
            )
            vendor_returns = tuple(
                row for row in returns if row.purchase_order_id in vendor_order_ids
            )
            ordered = sum((row.quantity for row in vendor_lines), Decimal(0))
            accepted = sum(
                (row.accepted_quantity for row in vendor_receipt_lines), Decimal(0)
            )
            returned = sum((row.quantity for row in vendor_returns), Decimal(0))
            net = accepted - returned
            lead_times = [
                (
                    min(
                        receipt.received_at
                        for receipt in vendor_receipts
                        if receipt.purchase_order_id == order.id
                    )
                    - order.issued_at
                ).total_seconds()
                / 86400
                for order in vendor_orders
                if order.issued_at is not None
                and any(
                    receipt.purchase_order_id == order.id for receipt in vendor_receipts
                )
            ]
            evidence = {
                "definition_version": 1,
                "vendor_id": str(vendor_id),
                "order_ids": sorted(str(row.id) for row in vendor_orders),
                "line_ids": sorted(str(row.id) for row in vendor_lines),
                "receipt_digests": sorted(
                    row.payload_digest for row in vendor_receipts
                ),
                "return_ids": sorted(str(row.id) for row in vendor_returns),
                "match_digests": sorted(
                    row.evidence_digest
                    for row in matches
                    if row.purchase_order_id in vendor_order_ids
                ),
            }
            report_items.append(
                VendorPerformanceItem(
                    vendor_id=vendor_id,
                    purchase_order_count=len(vendor_orders),
                    ordered_quantity=ordered,
                    accepted_received_quantity=accepted,
                    returned_quantity=returned,
                    net_accepted_quantity=net,
                    fulfillment_ratio=(net / ordered).quantize(Decimal("0.0001"))
                    if ordered
                    else None,
                    return_ratio=(returned / accepted).quantize(Decimal("0.0001"))
                    if accepted
                    else None,
                    completed_lead_time_samples=len(lead_times),
                    average_lead_time_days=(
                        Decimal(str(sum(lead_times) / len(lead_times))).quantize(
                            Decimal("0.01")
                        )
                        if lead_times
                        else None
                    ),
                    discrepancy_count=sum(
                        1
                        for row in discrepancies
                        if row.purchase_order_id in vendor_order_ids
                    ),
                    price_variance_line_count=sum(
                        1
                        for row in match_lines
                        if row.purchase_order_line_id in line_ids
                        and row.price_variance != 0
                    ),
                    evidence_digest=digest(evidence),
                )
            )
        report_evidence = {
            "definition_version": 1,
            "company_id": str(context.company.id),
            "branch_id": str(branch_id) if branch_id else None,
            "evaluated_at": evaluated_at.isoformat(),
            "items": [
                (str(row.vendor_id), row.evidence_digest) for row in report_items
            ],
        }
        return VendorPerformanceReport(
            definition_version=1,
            company_id=context.company.id,
            branch_id=branch_id,
            evaluated_at=evaluated_at,
            items=tuple(report_items),
            evidence_digest=digest(report_evidence),
        )

    @staticmethod
    def _source_evidence_digest(
        *,
        order: PurchaseOrder,
        bill: VendorBill,
        bill_revision: BillRevision,
        bill_lines: tuple[BillLine, ...],
        po_lines: tuple[PurchaseOrderLine, ...],
        receipt_rows: tuple[PurchaseOrderReceiptLine, ...],
        returns: tuple[PurchaseReturn, ...],
        credits: tuple[VendorCredit, ...],
    ) -> str:
        return digest(
            {
                "definition_version": 2,
                "purchase_order": (
                    str(order.id),
                    order.version,
                    str(order.vendor_id),
                    order.branch_id,
                    order.currency,
                ),
                "purchase_order_lines": sorted(
                    (
                        str(row.id),
                        str(row.quantity),
                        str(row.unit_cost),
                        str(row.inventory_item_id) if row.inventory_item_id else None,
                        row.is_cancelled,
                    )
                    for row in po_lines
                ),
                "vendor_bill": (
                    str(bill.id),
                    bill.version,
                    str(bill.vendor_id),
                    bill.branch_id,
                    bill.currency,
                    bill_revision.revision,
                    bill_revision.canonical_digest,
                ),
                "vendor_bill_lines": sorted(
                    (
                        str(row.id),
                        row.purchasing_reference,
                        row.receipt_reference,
                        str(row.quantity),
                        str(row.net_amount),
                        str(row.tax_amount),
                    )
                    for row in bill_lines
                ),
                "receipts": sorted(
                    (
                        str(row.id),
                        str(row.receipt_id),
                        str(row.purchase_order_line_id),
                        str(row.accepted_quantity),
                        str(row.rejected_quantity),
                        str(row.unit_cost_snapshot),
                        row.currency_snapshot,
                    )
                    for row in receipt_rows
                ),
                "returns": sorted(
                    (
                        str(row.id),
                        str(row.purchase_order_line_id),
                        str(row.quantity),
                        row.status,
                        row.updated_at.isoformat(),
                    )
                    for row in returns
                ),
                "vendor_credits": sorted(
                    (
                        str(row.id),
                        row.source_identity,
                        row.source_digest,
                        str(row.amount),
                        row.currency,
                    )
                    for row in credits
                ),
            }
        )

    @staticmethod
    def _receipt_reference(
        line: BillLine, receipts: tuple[PurchaseOrderReceiptLine, ...]
    ) -> UUID | None:
        if not line.receipt_reference:
            return None
        try:
            identity = UUID(line.receipt_reference)
        except ValueError:
            return None
        return identity if any(row.id == identity for row in receipts) else None

    @staticmethod
    def _exception(
        match: ProcurementMatch,
        category: str,
        expected: str,
        actual: str,
        line_id: UUID | None = None,
    ) -> ProcurementMatchException:
        return ProcurementMatchException(
            company_id=match.company_id,
            branch_id=match.branch_id,
            match_id=match.id,
            match_line_id=line_id,
            category=category,
            expected_evidence=expected,
            actual_evidence=actual,
        )

    @staticmethod
    def _exception_category(state: str) -> str:
        return {
            "partially_matched": "quantity_variance",
            "unreceived_billing": "missing_receipt",
            "return_pending_credit": "return_pending_credit",
            "requires_review": "return_pending_credit",
        }.get(state, state)

    @staticmethod
    def _aggregate_state(initial: str | None, states: list[str]) -> str:
        if initial:
            return initial
        precedence = (
            "item_conflict",
            "currency_conflict",
            "vendor_conflict",
            "requires_review",
            "return_pending_credit",
            "overbilled",
            "unreceived_billing",
            "price_variance",
            "quantity_variance",
            "unbilled_receipt",
            "partially_matched",
        )
        return next((state for state in precedence if state in states), "matched")

    async def _item(self, session: AsyncSession, row: ProcurementMatch) -> MatchItem:
        lines = tuple(
            (
                await session.scalars(
                    select(ProcurementMatchLine)
                    .where(
                        ProcurementMatchLine.company_id == row.company_id,
                        ProcurementMatchLine.match_id == row.id,
                    )
                    .order_by(ProcurementMatchLine.id)
                )
            ).all()
        )
        exceptions = tuple(
            (
                await session.scalars(
                    select(ProcurementMatchException)
                    .where(
                        ProcurementMatchException.company_id == row.company_id,
                        ProcurementMatchException.match_id == row.id,
                    )
                    .order_by(
                        ProcurementMatchException.opened_at,
                        ProcurementMatchException.id,
                    )
                )
            ).all()
        )
        return MatchItem.model_validate(row).model_copy(
            update={
                "lines": tuple(MatchLineItem.model_validate(item) for item in lines),
                "exceptions": tuple(
                    MatchExceptionItem.model_validate(item) for item in exceptions
                ),
            }
        )

    @staticmethod
    def _event(
        session: AsyncSession,
        context: AuthorizationContext,
        event_type: EventType,
        match: ProcurementMatch,
        payload: dict[str, object],
    ) -> None:
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                company_id=context.company.id,
                branch_id=match.branch_id,
                event_type=event_type,
                entity_type="procurement_match",
                entity_id=match.id,
                user_id=context.user.id,
                correlation_id=match.id,
                payload={
                    "match_id": str(match.id),
                    "purchase_order_id": str(match.purchase_order_id),
                    "vendor_bill_id": str(match.vendor_bill_id),
                    **payload,
                },
            ),
        )


procurement_matching_service = ProcurementMatchingService()


async def _current_source_digest(
    session: AsyncSession, match: ProcurementMatch, bill: VendorBill
) -> str | None:
    order = await session.scalar(
        select(PurchaseOrder).where(
            PurchaseOrder.company_id == match.company_id,
            PurchaseOrder.id == match.purchase_order_id,
        )
    )
    revision = await session.scalar(
        select(BillRevision).where(
            BillRevision.company_id == match.company_id,
            BillRevision.bill_id == bill.id,
            BillRevision.revision == bill.current_revision,
        )
    )
    if order is None or revision is None:
        return None
    bill_lines = tuple(
        (
            await session.scalars(
                select(BillLine).where(
                    BillLine.company_id == match.company_id,
                    BillLine.revision_id == revision.id,
                )
            )
        ).all()
    )
    po_lines = tuple(
        (
            await session.scalars(
                select(PurchaseOrderLine).where(
                    PurchaseOrderLine.company_id == match.company_id,
                    PurchaseOrderLine.purchase_order_id == order.id,
                )
            )
        ).all()
    )
    receipt_rows = tuple(
        (
            await session.scalars(
                select(PurchaseOrderReceiptLine)
                .join(
                    PurchaseOrderReceipt,
                    PurchaseOrderReceipt.id == PurchaseOrderReceiptLine.receipt_id,
                )
                .where(
                    PurchaseOrderReceiptLine.company_id == match.company_id,
                    PurchaseOrderReceipt.purchase_order_id == order.id,
                )
            )
        ).all()
    )
    returns = tuple(
        (
            await session.scalars(
                select(PurchaseReturn).where(
                    PurchaseReturn.company_id == match.company_id,
                    PurchaseReturn.purchase_order_id == order.id,
                    PurchaseReturn.status.in_(
                        ("returned", "received_by_vendor", "closed")
                    ),
                )
            )
        ).all()
    )
    return_ids = tuple(str(row.id) for row in returns)
    credits = (
        tuple(
            (
                await session.scalars(
                    select(VendorCredit).where(
                        VendorCredit.company_id == match.company_id,
                        VendorCredit.vendor_id == bill.vendor_id,
                        VendorCredit.source_system == "purchasing_return",
                        VendorCredit.source_identity.in_(return_ids),
                    )
                )
            ).all()
        )
        if return_ids
        else ()
    )
    return ProcurementMatchingService._source_evidence_digest(
        order=order,
        bill=bill,
        bill_revision=revision,
        bill_lines=bill_lines,
        po_lines=po_lines,
        receipt_rows=receipt_rows,
        returns=returns,
        credits=credits,
    )


async def is_current_eligible_match(
    session: AsyncSession, match: ProcurementMatch, bill: VendorBill
) -> bool:
    """Fail closed when PO, receipt, or bill authority changed after evaluation."""
    current_digest = await _current_source_digest(session, match, bill)
    return (
        match.admission_state == "eligible"
        and match.superseded_at is None
        and match.bill_version == bill.version
        and current_digest == match.source_evidence_digest
    )
