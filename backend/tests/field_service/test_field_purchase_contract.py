# ruff: noqa: F401, F811 -- imported pytest fixture is consumed by name

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from app.dispatch.models import DispatchAssignment
from app.field_service.artifacts import FieldArtifactService
from app.field_service.field_purchase_schemas import (
    ExtractedLine,
    FieldPurchaseCreate,
    FieldPurchaseDispositionInput,
    FieldPurchaseExtractionInput,
    LineDispositionInput,
    VendorMappingCreate,
)
from app.field_service.field_purchases import FieldPurchaseService
from app.field_service.schemas import (
    FieldArtifactFinalizeInput,
    FieldArtifactIntentInput,
)
from app.field_service.service import FieldService
from app.inventory.models import InventoryItem, StockLocation
from app.jobs.models import Job
from app.purchasing.models import OperationalVendor
from pydantic import ValidationError

from tests.dispatch.test_dispatch_service import dispatch_fixture


def test_extraction_preserves_unknowns_and_rejects_duplicate_lines() -> None:
    line = ExtractedLine(
        line_number=1,
        description="Uncertain fitting",
        vendor_code=None,
        quantity=Decimal(2),
        unit=None,
        unit_price=None,
        extended_amount=None,
        confidence={"description": Decimal("0.61")},
    )
    with pytest.raises(ValidationError, match="line numbers must be unique"):
        FieldPurchaseExtractionInput(
            method="synthetic_fixture",
            extraction_digest="a" * 64,
            expected_version=1,
            lines=(line, line),
        )


def test_split_disposition_contract_keeps_purchase_and_consumption_separate() -> None:
    line_id = uuid4()
    payload = FieldPurchaseDispositionInput(
        expected_version=2,
        idempotency_key="receipt-split-submit-1",
        dispositions=(
            LineDispositionInput(
                line_id=line_id,
                disposition="used_on_this_job",
                quantity=Decimal(3),
                idempotency_key="receipt-line-used-1",
            ),
            LineDispositionInput(
                line_id=line_id,
                disposition="keep_on_truck",
                quantity=Decimal(1),
                idempotency_key="receipt-line-truck-1",
            ),
        ),
    )
    assert sum(item.quantity for item in payload.dispositions) == Decimal(4)
    assert {item.disposition for item in payload.dispositions} == {
        "used_on_this_job",
        "keep_on_truck",
    }


def test_extraction_contract_has_no_payment_or_public_url_field() -> None:
    fields = FieldPurchaseExtractionInput.model_fields
    assert "payment_card" not in fields
    assert "receipt_url" not in fields
    assert "structured_evidence" not in fields


def test_field_purchase_contract_is_idempotent_and_exact_mapping_only() -> None:
    runtime = __import__(
        "app.field_service.field_purchases", fromlist=["FieldPurchaseService"]
    )
    source = __import__("inspect").getsource(runtime.FieldPurchaseService)
    assert "idempotency_key" in source
    assert "extraction_digest" in source
    assert "vendor_code" in source
    exact_resolution = source.split("item_id =", 1)[1].splitlines()[0]
    assert "vendor_code" in exact_resolution
    assert "description" not in exact_resolution
    assert "fuzzy" not in source.lower()


@pytest.mark.asyncio
async def test_receipt_replay_exact_mapping_and_split_disposition(
    dispatch_fixture,
) -> None:
    factory, context, appointment, technician, _ = dispatch_fixture
    now = datetime.now(timezone.utc)
    async with factory() as session, session.begin():
        job = Job(
            company_id=context.company.id,
            branch_id=context.active_branch.id,
            job_number=f"JOB-{int(uuid4().hex[:8], 16):010d}",
            customer_id=appointment.customer_id,
            service_location_id=appointment.service_location_id,
            status="in_progress",
            concurrency_version=1,
            activated_at=now,
            started_at=now,
            created_by_user_id=context.user.id,
            updated_by_user_id=context.user.id,
        )
        session.add(job)
        await session.flush()
        assignment = DispatchAssignment(
            company_id=context.company.id,
            branch_id=context.active_branch.id,
            appointment_id=appointment.id,
            job_id=job.id,
            primary_employee_id=technician.id,
            status="acknowledged",
            assignment_reason="Field purchase qualification",
            assigned_by_user_id=context.user.id,
            window_start_at=appointment.arrival_window_start_at,
            window_end_at=appointment.arrival_window_end_at,
            effective_at=now,
            version=1,
        )
        item = InventoryItem(
            company_id=context.company.id,
            code=f"FIT-{uuid4().hex[:6].upper()}",
            name="Known fitting",
            stocking_unit="each",
            status="active",
            created_by_user_id=context.user.id,
            updated_by_user_id=context.user.id,
        )
        vendor = OperationalVendor(
            company_id=context.company.id,
            code=f"VEN-{uuid4().hex[:6].upper()}",
            display_name="Qualified Vendor",
            status="active",
            created_by_user_id=context.user.id,
        )
        truck = StockLocation(
            company_id=context.company.id,
            branch_id=context.active_branch.id,
            code=f"TRUCK-{uuid4().hex[:6].upper()}",
            name="Qualification truck",
            location_type="vehicle",
            status="active",
            created_by_user_id=context.user.id,
            updated_by_user_id=context.user.id,
        )
        session.add_all([assignment, item, vendor, truck])

    artifact_service = FieldArtifactService(FieldService())
    async with factory() as session:
        intent = await artifact_service.create_intent(
            session,
            context=context,
            job_id=job.id,
            payload=FieldArtifactIntentInput(
                artifact_class="photo",
                media_type="image/jpeg",
                expected_size=256,
                expected_digest="b" * 64,
                idempotency_key="field-purchase-photo-1",
                expected_assignment_version=1,
            ),
        )
    async with factory() as session:
        artifact = await artifact_service.finalize(
            session,
            context=context,
            job_id=job.id,
            intent_id=intent.intent_id,
            payload=FieldArtifactFinalizeInput(
                content_digest="b" * 64,
                size=256,
                media_type="image/jpeg",
                opaque_storage_reference="protected:field-purchase:receipt-1",
            ),
        )

    service = FieldPurchaseService(FieldService())
    async with factory() as session:
        mapping = await service.certify_mapping(
            session,
            context=context,
            payload=VendorMappingCreate(
                vendor_id=vendor.id,
                vendor_code="SKU-EXACT-1",
                inventory_item_id=item.id,
                evidence_digest="c" * 64,
            ),
        )
        assert mapping.inventory_item_id == item.id
    create = FieldPurchaseCreate(
        receipt_artifact_id=artifact.artifact_id,
        inventory_location_id=truck.id,
        expected_assignment_version=1,
        idempotency_key="field-purchase-create-1",
    )
    async with factory() as session:
        purchase = await service.create(
            session, context=context, job_id=job.id, payload=create
        )
    async with factory() as session:
        replay = await service.create(
            session, context=context, job_id=job.id, payload=create
        )
        assert replay.id == purchase.id
    async with factory() as session:
        extracted = await service.record_extraction(
            session,
            context=context,
            job_id=job.id,
            purchase_id=purchase.id,
            payload=FieldPurchaseExtractionInput(
                method="synthetic_fixture",
                provider_reference=None,
                vendor_id=vendor.id,
                extraction_digest="d" * 64,
                expected_version=1,
                lines=(
                    ExtractedLine(
                        line_number=1,
                        description="Receipt wording",
                        vendor_code="SKU-EXACT-1",
                        quantity=Decimal(4),
                        unit="each",
                        unit_price=Decimal("2.50"),
                        extended_amount=Decimal("10.00"),
                        confidence={"vendor_code": Decimal(1)},
                    ),
                ),
            ),
        )
        assert extracted.lines[0].match_state == "exact"
        assert extracted.lines[0].inventory_item_id == item.id
    async with factory() as session:
        submitted = await service.dispose(
            session,
            context=context,
            job_id=job.id,
            purchase_id=purchase.id,
            payload=FieldPurchaseDispositionInput(
                expected_version=2,
                idempotency_key="field-purchase-submit-1",
                dispositions=(
                    LineDispositionInput(
                        line_id=extracted.lines[0].id,
                        disposition="used_on_this_job",
                        quantity=Decimal(3),
                        idempotency_key="field-purchase-used-1",
                    ),
                    LineDispositionInput(
                        line_id=extracted.lines[0].id,
                        disposition="keep_on_truck",
                        quantity=Decimal(1),
                        inventory_location_id=truck.id,
                        idempotency_key="field-purchase-truck-1",
                    ),
                ),
            ),
        )
        assert submitted.state == "submitted"
        assert {row.state for row in submitted.dispositions} == {"confirmed"}
