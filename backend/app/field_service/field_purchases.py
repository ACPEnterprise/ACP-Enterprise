import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.inventory.contracts import (
    AllocateReservation,
    CreateReservation,
    PostMaterialIssue,
    PostStockMovement,
)
from app.inventory.models import InventoryItem, StockLocation
from app.inventory.repository import InventoryRepository
from app.platform.permissions.authorization import AuthorizationContext
from app.purchasing.models import OperationalVendor

from .errors import FieldServiceConflict, FieldServiceNotFound, FieldServiceValidation
from .field_purchase_schemas import (
    FieldPurchaseCreate,
    FieldPurchaseDispositionInput,
    FieldPurchaseDispositionOut,
    FieldPurchaseExtractionInput,
    FieldPurchaseLineOut,
    FieldPurchaseOut,
    FieldPurchaseReviewSummary,
    VendorMappingCreate,
)
from .models import (
    FieldArtifactEvidence,
    FieldPurchase,
    FieldPurchaseDisposition,
    FieldPurchaseExtraction,
    FieldPurchaseLine,
    FieldPurchaseVendorMapping,
)
from .service import FieldService


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _value(payload: object | None) -> object | None:
    return getattr(payload, "value", None)


class FieldPurchaseService:
    """Assignment-scoped receipt evidence with review before material authority."""

    def __init__(
        self,
        field: FieldService,
        inventory: InventoryRepository | None = None,
    ) -> None:
        self.field = field
        self.inventory = inventory or InventoryRepository()

    async def create(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job_id: UUID,
        payload: FieldPurchaseCreate,
    ) -> FieldPurchaseOut:
        assignment = await self.field._assigned_job(session, context, job_id)
        if assignment.version != payload.expected_assignment_version:
            raise FieldServiceConflict("Field assignment changed. Refresh and retry.")
        employee = await self.field._employee(session, context)
        artifact = await session.scalar(
            select(FieldArtifactEvidence).where(
                FieldArtifactEvidence.company_id == context.company.id,
                FieldArtifactEvidence.branch_id == assignment.branch_id,
                FieldArtifactEvidence.job_id == job_id,
                FieldArtifactEvidence.assignment_id == assignment.id,
                FieldArtifactEvidence.id == payload.receipt_artifact_id,
                FieldArtifactEvidence.artifact_class.in_(("photo", "field_document")),
            )
        )
        if artifact is None:
            raise FieldServiceNotFound(
                "Receipt evidence was not found for this assignment."
            )
        if payload.inventory_location_id is not None:
            await self._location(
                session, context, assignment.branch_id, payload.inventory_location_id
            )
        facts = {
            "company_id": str(context.company.id),
            "branch_id": str(assignment.branch_id),
            "job_id": str(job_id),
            "assignment_id": str(assignment.id),
            "employee_id": str(employee.id),
            "receipt_artifact_id": str(artifact.id),
            "inventory_location_id": str(payload.inventory_location_id)
            if payload.inventory_location_id
            else None,
        }
        request_digest = _digest(facts)
        existing = await session.scalar(
            select(FieldPurchase).where(
                FieldPurchase.company_id == context.company.id,
                FieldPurchase.idempotency_key == payload.idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_digest != request_digest:
                raise FieldServiceConflict(
                    "Field-purchase command was reused for different evidence."
                )
            return await self._out(session, existing)
        duplicate = await session.scalar(
            select(FieldPurchase).where(
                FieldPurchase.company_id == context.company.id,
                (
                    (FieldPurchase.receipt_artifact_id == artifact.id)
                    | (FieldPurchase.receipt_digest == artifact.content_digest)
                ),
            )
        )
        if duplicate is not None:
            if duplicate.job_id != job_id:
                raise FieldServiceConflict(
                    "Identical receipt evidence is already bound to another Job."
                )
            return await self._out(session, duplicate)
        record = FieldPurchase(
            company_id=context.company.id,
            branch_id=assignment.branch_id,
            job_id=job_id,
            assignment_id=assignment.id,
            employee_id=employee.id,
            receipt_artifact_id=artifact.id,
            inventory_location_id=payload.inventory_location_id,
            receipt_digest=artifact.content_digest,
            request_digest=request_digest,
            idempotency_key=payload.idempotency_key,
            created_by_user_id=context.user.id,
        )
        session.add(record)
        self._event(
            session,
            context,
            EventType.FIELD_PURCHASE_RECORDED,
            record.id,
            assignment.branch_id,
            {"job_id": str(job_id), "receipt_digest": artifact.content_digest},
        )
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            replay = await session.scalar(
                select(FieldPurchase).where(
                    FieldPurchase.company_id == context.company.id,
                    FieldPurchase.receipt_digest == artifact.content_digest,
                )
            )
            if replay is None:
                raise
            if replay.job_id != job_id:
                raise FieldServiceConflict(
                    "Identical receipt evidence is already bound to another Job."
                )
            return await self._out(session, replay)
        return await self._out(session, record)

    async def record_extraction(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job_id: UUID,
        purchase_id: UUID,
        payload: FieldPurchaseExtractionInput,
    ) -> FieldPurchaseOut:
        purchase = await self._purchase(
            session, context, job_id, purchase_id, lock=True
        )
        replay = await session.scalar(
            select(FieldPurchaseExtraction).where(
                FieldPurchaseExtraction.company_id == context.company.id,
                FieldPurchaseExtraction.extraction_digest == payload.extraction_digest,
            )
        )
        if replay is not None:
            if replay.field_purchase_id != purchase.id:
                raise FieldServiceConflict(
                    "Extraction digest belongs to different receipt evidence."
                )
            return await self._out(session, purchase)
        if purchase.version != payload.expected_version:
            raise FieldServiceConflict("Field purchase changed. Refresh and retry.")
        if payload.vendor_id is not None:
            vendor = await session.scalar(
                select(OperationalVendor.id).where(
                    OperationalVendor.company_id == context.company.id,
                    OperationalVendor.id == payload.vendor_id,
                    OperationalVendor.status == "active",
                )
            )
            if vendor is None:
                raise FieldServiceValidation("Vendor is not active in this Company.")
        latest_version = await session.scalar(
            select(func.max(FieldPurchaseExtraction.version)).where(
                FieldPurchaseExtraction.company_id == context.company.id,
                FieldPurchaseExtraction.field_purchase_id == purchase.id,
            )
        )
        version = (latest_version or 0) + 1
        evidence = payload.model_dump(
            mode="json", exclude={"lines", "expected_version"}
        )
        extraction = FieldPurchaseExtraction(
            company_id=context.company.id,
            field_purchase_id=purchase.id,
            version=version,
            method=payload.method,
            provider_reference=payload.provider_reference,
            extraction_digest=payload.extraction_digest,
            vendor_id=payload.vendor_id,
            vendor_text=str(_value(payload.vendor))
            if _value(payload.vendor) is not None
            else None,
            transaction_reference=str(_value(payload.transaction_reference))
            if _value(payload.transaction_reference) is not None
            else None,
            purchased_at=_value(payload.purchased_at)
            if isinstance(_value(payload.purchased_at), datetime)
            else None,
            subtotal=self._decimal(_value(payload.subtotal)),
            tax=self._decimal(_value(payload.tax)),
            total=self._decimal(_value(payload.total)),
            currency=str(_value(payload.currency)).upper()
            if _value(payload.currency)
            else None,
            structured_evidence=evidence,
            recorded_by_user_id=context.user.id,
        )
        session.add(extraction)
        await session.flush()
        mappings: dict[str, UUID] = {}
        if payload.vendor_id is not None:
            rows = (
                await session.scalars(
                    select(FieldPurchaseVendorMapping).where(
                        FieldPurchaseVendorMapping.company_id == context.company.id,
                        FieldPurchaseVendorMapping.vendor_id == payload.vendor_id,
                        FieldPurchaseVendorMapping.active.is_(True),
                    )
                )
            ).all()
            mappings = {row.vendor_code: row.inventory_item_id for row in rows}
        for source in payload.lines:
            item_id = mappings.get(source.vendor_code) if source.vendor_code else None
            certain = bool(source.confidence) and all(
                value == Decimal(1) for value in source.confidence.values()
            )
            session.add(
                FieldPurchaseLine(
                    company_id=context.company.id,
                    field_purchase_id=purchase.id,
                    extraction_id=extraction.id,
                    line_number=source.line_number,
                    description=source.description,
                    vendor_code=source.vendor_code,
                    quantity=source.quantity,
                    unit=source.unit,
                    unit_price=source.unit_price,
                    extended_amount=source.extended_amount,
                    inventory_item_id=item_id,
                    match_state=(
                        "exact"
                        if item_id and certain
                        else "review_required"
                        if item_id
                        else "unmatched"
                    ),
                    confidence_evidence={
                        key: str(value) for key, value in source.confidence.items()
                    },
                )
            )
        purchase.state = (
            "ready_for_disposition"
            if payload.lines
            and all(
                line.vendor_code
                and line.vendor_code in mappings
                and line.confidence
                and all(value == Decimal(1) for value in line.confidence.values())
                for line in payload.lines
            )
            else "review_required"
        )
        purchase.version += 1
        purchase.updated_at = datetime.now(timezone.utc)
        self._event(
            session,
            context,
            EventType.FIELD_PURCHASE_EXTRACTION_RECORDED,
            purchase.id,
            purchase.branch_id,
            {
                "job_id": str(job_id),
                "extraction_digest": payload.extraction_digest,
                "method": payload.method,
            },
        )
        await session.commit()
        return await self._out(session, purchase)

    async def dispose(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job_id: UUID,
        purchase_id: UUID,
        payload: FieldPurchaseDispositionInput,
    ) -> FieldPurchaseOut:
        purchase = await self._purchase(
            session, context, job_id, purchase_id, lock=True
        )
        request_digest = _digest(payload.model_dump(mode="json"))
        if purchase.disposition_idempotency_key == payload.idempotency_key:
            if purchase.disposition_request_digest != request_digest:
                raise FieldServiceConflict(
                    "Disposition command was reused with different evidence."
                )
            return await self._out(session, purchase)
        if purchase.disposition_idempotency_key is not None:
            raise FieldServiceConflict(
                "Field purchase disposition was already submitted."
            )
        if purchase.version != payload.expected_version:
            raise FieldServiceConflict("Field purchase changed. Refresh and retry.")
        latest_extraction_id = await session.scalar(
            select(FieldPurchaseExtraction.id)
            .where(
                FieldPurchaseExtraction.company_id == context.company.id,
                FieldPurchaseExtraction.field_purchase_id == purchase.id,
            )
            .order_by(FieldPurchaseExtraction.version.desc())
            .limit(1)
        )
        lines = {
            line.id: line
            for line in (
                await session.scalars(
                    select(FieldPurchaseLine).where(
                        FieldPurchaseLine.company_id == context.company.id,
                        FieldPurchaseLine.field_purchase_id == purchase.id,
                        FieldPurchaseLine.extraction_id == latest_extraction_id,
                    )
                )
            ).all()
        }
        requested: dict[UUID, Decimal] = {}
        for decision in payload.dispositions:
            line = lines.get(decision.line_id)
            if line is None:
                raise FieldServiceValidation(
                    "Disposition line is outside this receipt."
                )
            requested[line.id] = requested.get(line.id, Decimal(0)) + decision.quantity
            if requested[line.id] > line.quantity:
                raise FieldServiceValidation(
                    "Disposition quantity exceeds purchased quantity."
                )
            if (
                decision.disposition in {"used_on_this_job", "keep_on_truck"}
                and line.inventory_item_id is None
            ):
                raise FieldServiceValidation(
                    "An exact Inventory item match is required."
                )
        if any(
            requested.get(line.id, Decimal(0)) != line.quantity
            for line in lines.values()
        ):
            raise FieldServiceValidation(
                "Every latest receipt line requires a complete disposition."
            )
        for decision in payload.dispositions:
            line = lines[decision.line_id]
            location_id = (
                decision.inventory_location_id or purchase.inventory_location_id
            )
            state = "confirmed"
            if decision.disposition == "keep_on_truck":
                if location_id is None:
                    state = "pending_review"
                else:
                    await self._location(
                        session,
                        context,
                        purchase.branch_id,
                        location_id,
                        vehicle_only=True,
                    )
            replay = await session.scalar(
                select(FieldPurchaseDisposition).where(
                    FieldPurchaseDisposition.company_id == context.company.id,
                    FieldPurchaseDisposition.idempotency_key
                    == decision.idempotency_key,
                )
            )
            if replay is not None:
                if (
                    replay.line_id != line.id
                    or replay.quantity != decision.quantity
                    or replay.disposition != decision.disposition
                ):
                    raise FieldServiceConflict(
                        "Disposition command was reused for a different decision."
                    )
                continue
            disposition = FieldPurchaseDisposition(
                company_id=context.company.id,
                field_purchase_id=purchase.id,
                line_id=line.id,
                disposition=decision.disposition,
                quantity=decision.quantity,
                inventory_location_id=location_id,
                state=state,
                reason=decision.reason,
                idempotency_key=decision.idempotency_key,
                confirmed_by_user_id=context.user.id,
            )
            session.add(disposition)
            await session.flush()
            if state == "confirmed" and decision.disposition in {
                "used_on_this_job",
                "keep_on_truck",
            }:
                if location_id is None:
                    disposition.state = "pending_review"
                else:
                    await self._compose_inventory(
                        session,
                        context=context,
                        purchase=purchase,
                        line=line,
                        disposition=disposition,
                        location_id=location_id,
                    )
                    disposition.state = "composed"
        purchase.state = "submitted"
        purchase.disposition_idempotency_key = payload.idempotency_key
        purchase.disposition_request_digest = request_digest
        purchase.version += 1
        purchase.updated_at = datetime.now(timezone.utc)
        self._event(
            session,
            context,
            EventType.FIELD_PURCHASE_DISPOSITION_CONFIRMED,
            purchase.id,
            purchase.branch_id,
            {"job_id": str(job_id), "decision_count": len(payload.dispositions)},
        )
        await session.commit()
        return await self._out(session, purchase)

    async def _compose_inventory(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        purchase: FieldPurchase,
        line: FieldPurchaseLine,
        disposition: FieldPurchaseDisposition,
        location_id: UUID,
    ) -> None:
        """Compose confirmed receipt evidence into canonical Inventory authority."""
        if line.inventory_item_id is None:
            raise FieldServiceValidation("An exact Inventory item match is required.")
        await self._location(
            session,
            context,
            purchase.branch_id,
            location_id,
            vehicle_only=disposition.disposition == "keep_on_truck",
        )
        occurred_at = datetime.now(timezone.utc)
        await self.inventory.post_movement(
            session,
            spec=PostStockMovement(
                company_id=context.company.id,
                branch_id=purchase.branch_id,
                item_id=line.inventory_item_id,
                movement_type="purchase_receipt",
                quantity=disposition.quantity,
                occurred_at=occurred_at,
                actor_user_id=context.user.id,
                idempotency_key=f"field-purchase:{disposition.id}:receipt",
                destination_location_id=location_id,
                provenance_type="field_purchase_disposition",
                provenance_id=disposition.id,
            ),
        )
        if disposition.disposition != "used_on_this_job":
            return
        reservation = await self.inventory.create_reservation(
            session,
            spec=CreateReservation(
                company_id=context.company.id,
                branch_id=purchase.branch_id,
                item_id=line.inventory_item_id,
                location_id=location_id,
                quantity=disposition.quantity,
                demand_type="job",
                demand_id=purchase.job_id,
                actor_user_id=context.user.id,
                idempotency_key=f"field-purchase:{disposition.id}:reservation",
            ),
        )
        allocation = await self.inventory.allocate_reservation(
            session,
            spec=AllocateReservation(
                company_id=context.company.id,
                branch_id=purchase.branch_id,
                reservation_id=reservation.id,
                item_id=line.inventory_item_id,
                location_id=location_id,
                actor_user_id=context.user.id,
                authorized_branch_ids=tuple(context.authorized_branch_ids),
                expected_version=reservation.version,
                idempotency_key=f"field-purchase:{disposition.id}:allocation",
            ),
        )
        await self.inventory.post_material_issue(
            session,
            spec=PostMaterialIssue(
                company_id=context.company.id,
                branch_id=purchase.branch_id,
                reservation_id=reservation.id,
                allocation_id=allocation.id,
                item_id=line.inventory_item_id,
                location_id=location_id,
                occurred_at=occurred_at,
                actor_user_id=context.user.id,
                authorized_branch_ids=tuple(context.authorized_branch_ids),
                expected_reservation_version=reservation.version + 1,
                idempotency_key=f"field-purchase:{disposition.id}:issue",
                external_reference_type="field_purchase_disposition",
                external_reference_id=disposition.id,
            ),
        )

    async def certify_mapping(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        payload: VendorMappingCreate,
    ) -> FieldPurchaseVendorMapping:
        vendor = await session.scalar(
            select(OperationalVendor.id).where(
                OperationalVendor.company_id == context.company.id,
                OperationalVendor.id == payload.vendor_id,
            )
        )
        item = await session.scalar(
            select(InventoryItem.id).where(
                InventoryItem.company_id == context.company.id,
                InventoryItem.id == payload.inventory_item_id,
            )
        )
        if vendor is None or item is None:
            raise FieldServiceValidation(
                "Vendor and Inventory item must belong to this Company."
            )
        active = await session.scalar(
            select(FieldPurchaseVendorMapping)
            .where(
                FieldPurchaseVendorMapping.company_id == context.company.id,
                FieldPurchaseVendorMapping.vendor_id == payload.vendor_id,
                FieldPurchaseVendorMapping.vendor_code == payload.vendor_code.strip(),
                FieldPurchaseVendorMapping.active.is_(True),
            )
            .with_for_update()
        )
        if active is not None and active.inventory_item_id == payload.inventory_item_id:
            return active
        if active is not None and active.id != payload.expected_prior_mapping_id:
            raise FieldServiceConflict(
                "Existing exact mapping must be explicitly superseded."
            )
        if active is not None:
            active.active = False
        mapping = FieldPurchaseVendorMapping(
            company_id=context.company.id,
            vendor_id=payload.vendor_id,
            vendor_code=payload.vendor_code.strip(),
            inventory_item_id=payload.inventory_item_id,
            version=(active.version + 1) if active else 1,
            supersedes_id=active.id if active else None,
            evidence_digest=payload.evidence_digest,
            certified_by_user_id=context.user.id,
        )
        session.add(mapping)
        self._event(
            session,
            context,
            EventType.FIELD_PURCHASE_VENDOR_MAPPING_CERTIFIED,
            mapping.id,
            None,
            {
                "vendor_id": str(payload.vendor_id),
                "inventory_item_id": str(payload.inventory_item_id),
                "mapping_version": mapping.version,
            },
        )
        await session.commit()
        return mapping

    async def review_queue(
        self, session: AsyncSession, *, context: AuthorizationContext
    ) -> tuple[FieldPurchaseReviewSummary, ...]:
        purchases = (
            await session.scalars(
                select(FieldPurchase)
                .where(
                    FieldPurchase.company_id == context.company.id,
                    FieldPurchase.branch_id.in_(context.authorized_branch_ids),
                    FieldPurchase.state.in_(
                        (
                            "receipt_attached",
                            "extraction_pending",
                            "review_required",
                            "submitted",
                        )
                    ),
                )
                .order_by(FieldPurchase.created_at)
            )
        ).all()
        results = []
        for purchase in purchases:
            latest_extraction_id = await session.scalar(
                select(FieldPurchaseExtraction.id)
                .where(FieldPurchaseExtraction.field_purchase_id == purchase.id)
                .order_by(FieldPurchaseExtraction.version.desc())
                .limit(1)
            )
            lines = (
                (
                    await session.scalars(
                        select(FieldPurchaseLine).where(
                            FieldPurchaseLine.field_purchase_id == purchase.id,
                            FieldPurchaseLine.extraction_id == latest_extraction_id,
                        )
                    )
                ).all()
                if latest_extraction_id is not None
                else []
            )
            dispositions = (
                await session.scalars(
                    select(FieldPurchaseDisposition).where(
                        FieldPurchaseDisposition.field_purchase_id == purchase.id
                    )
                )
            ).all()
            blockers = []
            if not lines:
                blockers.append("EXTRACTION_INCOMPLETE")
            if any(line.match_state != "exact" for line in lines):
                blockers.append("UNMATCHED_MATERIAL_LINE")
            if any(row.state == "pending_review" for row in dispositions):
                blockers.append("INVENTORY_LOCATION_REQUIRED")
            results.append(
                FieldPurchaseReviewSummary(
                    id=purchase.id,
                    job_id=purchase.job_id,
                    state=purchase.state,
                    unmatched_lines=sum(line.match_state != "exact" for line in lines),
                    pending_dispositions=sum(
                        row.state == "pending_review" for row in dispositions
                    ),
                    receipt_total_reconciles=None,
                    blocker_codes=tuple(blockers),
                    created_at=purchase.created_at,
                )
            )
        return tuple(results)

    async def _purchase(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        job_id: UUID,
        purchase_id: UUID,
        *,
        lock: bool = False,
    ) -> FieldPurchase:
        await self.field._assigned_job(session, context, job_id)
        query = select(FieldPurchase).where(
            FieldPurchase.company_id == context.company.id,
            FieldPurchase.branch_id.in_(context.authorized_branch_ids),
            FieldPurchase.job_id == job_id,
            FieldPurchase.id == purchase_id,
        )
        if lock:
            query = query.with_for_update()
        purchase = await session.scalar(query)
        if purchase is None:
            raise FieldServiceNotFound("Field purchase was not found.")
        return purchase

    @staticmethod
    async def _location(
        session: AsyncSession,
        context: AuthorizationContext,
        branch_id: UUID,
        location_id: UUID,
        vehicle_only: bool = False,
    ) -> StockLocation:
        location = await session.scalar(
            select(StockLocation).where(
                StockLocation.company_id == context.company.id,
                StockLocation.branch_id == branch_id,
                StockLocation.id == location_id,
                StockLocation.status == "active",
            )
        )
        if location is None or (vehicle_only and location.location_type != "vehicle"):
            raise FieldServiceValidation(
                "Authorized truck Inventory location is required."
                if vehicle_only
                else "Inventory location is not available."
            )
        return location

    @staticmethod
    def _decimal(value: object | None) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except Exception as error:
            raise FieldServiceValidation("Extracted amount is not numeric.") from error

    @staticmethod
    def _event(
        session: AsyncSession,
        context: AuthorizationContext,
        event_type: EventType,
        entity_id: UUID,
        branch_id: UUID | None,
        payload: dict[str, object],
    ) -> None:
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="field_purchase",
                entity_id=entity_id,
                company_id=context.company.id,
                branch_id=branch_id,
                user_id=context.user.id,
                correlation_id=uuid4(),
                payload=payload,
            ),
        )

    @staticmethod
    async def _out(session: AsyncSession, purchase: FieldPurchase) -> FieldPurchaseOut:
        extraction = await session.scalar(
            select(FieldPurchaseExtraction)
            .where(FieldPurchaseExtraction.field_purchase_id == purchase.id)
            .order_by(FieldPurchaseExtraction.version.desc())
            .limit(1)
        )
        lines = (
            (
                await session.scalars(
                    select(FieldPurchaseLine)
                    .where(
                        FieldPurchaseLine.field_purchase_id == purchase.id,
                        FieldPurchaseLine.extraction_id == extraction.id,
                    )
                    .order_by(FieldPurchaseLine.line_number)
                )
            ).all()
            if extraction is not None
            else []
        )
        dispositions = (
            await session.scalars(
                select(FieldPurchaseDisposition)
                .where(FieldPurchaseDisposition.field_purchase_id == purchase.id)
                .order_by(FieldPurchaseDisposition.created_at)
            )
        ).all()
        return FieldPurchaseOut(
            id=purchase.id,
            job_id=purchase.job_id,
            employee_id=purchase.employee_id,
            receipt_artifact_id=purchase.receipt_artifact_id,
            receipt_digest=purchase.receipt_digest,
            state=purchase.state,
            version=purchase.version,
            extraction_method=extraction.method if extraction else None,
            extraction_digest=extraction.extraction_digest if extraction else None,
            lines=tuple(FieldPurchaseLineOut.model_validate(row) for row in lines),
            dispositions=tuple(
                FieldPurchaseDispositionOut.model_validate(row) for row in dispositions
            ),
            created_at=purchase.created_at,
        )


field_purchase_service = FieldPurchaseService(FieldService())
