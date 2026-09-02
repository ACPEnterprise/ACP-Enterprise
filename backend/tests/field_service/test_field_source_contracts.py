from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.field_service.notifications import (
    SafeEmployeeNotification,
    UnconfiguredPushProvider,
)
from app.field_service.router import router
from app.field_service.schemas import (
    FieldArtifactIntentInput,
    FieldContact,
    FieldInvoice,
)
from app.field_service.sources import FieldSourceService


def test_field_source_routes_are_assignment_scoped() -> None:
    paths = {route.path for route in router.routes}
    assert "/api/v1/technician/jobs/{job_id}/sources" in paths
    assert "/api/v1/technician/jobs/{job_id}/price-book" in paths
    assert "/api/v1/technician/history/completed" in paths
    assert "/api/v1/technician/jobs/{job_id}/artifacts/intents" in paths
    assert "/api/v1/technician/readiness" in paths
    assert not any("customers/search" in path or "assets/search" in path for path in paths)


def test_field_contact_rejects_protected_or_unbounded_payload() -> None:
    with pytest.raises(ValidationError):
        FieldContact(
            contact_id=uuid4(),
            display_name="Synthetic Customer",
            phone="+15555550123",
            email="synthetic@example.test",
            can_approve_work=True,
            internal_notes="must never reach the field",  # type: ignore[call-arg]
        )


def test_artifact_intent_rejects_mime_and_size_attacks() -> None:
    common = {
        "artifact_class": "photo",
        "expected_digest": "a" * 64,
        "idempotency_key": "field-photo-1",
        "expected_assignment_version": 1,
    }
    with pytest.raises(ValidationError):
        FieldArtifactIntentInput(
            **common, media_type="text/html", expected_size=100  # type: ignore[arg-type]
        )
    with pytest.raises(ValidationError):
        FieldArtifactIntentInput(
            **common, media_type="image/jpeg", expected_size=25_000_001
        )


def test_readiness_truthfully_preserves_policy_and_provider_gates() -> None:
    invoice = FieldInvoice(
        invoice_id=uuid4(),
        invoice_number="INV-000001",
        status="issued",
        version=1,
        open_amount=Decimal("100.00"),
        currency="USD",
    )
    gates = {
        gate.capability: gate.state
        for gate in FieldSourceService._gates(
            equipment=(), fleet=(), estimates=(), invoice=invoice
        )
    }
    assert gates["attachments"] == "PROVIDER_REQUIRED"
    assert gates["customer_authorization"] == "POLICY_REQUIRED"
    assert gates["communications"] == "PROVIDER_REQUIRED"
    assert gates["notifications"] == "SOURCE_REQUIRED"
    assert gates["payment"] == "READY"


def test_field_contract_has_no_payment_instrument_or_internal_cost_surface() -> None:
    names = " ".join(FieldInvoice.model_fields).lower()
    assert "payment_method" not in names
    assert "provider" not in names
    assert "internal_cost" not in names
    assert "merchant" not in names


@pytest.mark.asyncio
async def test_push_seam_is_safe_and_truthfully_unconfigured() -> None:
    notification = SafeEmployeeNotification(
        notification_id=uuid4(),
        employee_id=uuid4(),
        notification_class="assignment_changed",
        title="Assignment updated",
        safe_summary="Open ACP Employee to review your schedule.",
        deep_link_reference="field-job:opaque-reference",
    )
    assert (
        await UnconfiguredPushProvider().deliver(notification)
    ).outcome == "provider_required"
    with pytest.raises(ValueError):
        SafeEmployeeNotification(
            notification_id=uuid4(),
            employee_id=uuid4(),
            notification_class="operational_notice",
            title="Customer balance",
            safe_summary="Review payment details",
            deep_link_reference=None,
        ).validate_lock_screen()
