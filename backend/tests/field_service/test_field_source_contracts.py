from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
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
    FieldJobInstructions,
)
from app.field_service.sources import FieldSourceService


def test_field_source_routes_are_assignment_scoped() -> None:
    paths = {route.path for route in router.routes}
    assert "/api/v1/technician/jobs/{job_id}/sources" in paths
    assert "/api/v1/technician/jobs/{job_id}/instructions" in paths
    assert "/api/v1/technician/jobs/{job_id}/price-book" in paths
    assert "/api/v1/technician/history" in paths
    assert "/api/v1/technician/jobs/{job_id}/equipment" in paths
    assert "/api/v1/technician/jobs/{job_id}/estimate" in paths
    assert "/api/v1/technician/jobs/{job_id}/artifacts/intents" in paths
    assert "/api/v1/technician/readiness" in paths
    assert not any("customers/search" in path or "assets/search" in path for path in paths)


def test_job_instructions_contract_allowlists_only_customer_service_need() -> None:
    fields = set(FieldJobInstructions.model_fields)
    assert fields == {
        "job_id",
        "assignment_id",
        "assignment_version",
        "job_version",
        "customer_reported_problem",
        "source_as_of",
        "omitted_unclassified_fields",
    }
    assert not fields.intersection(
        {
            "internal_description",
            "customer_notes",
            "property_notes",
            "gate_code",
            "gate_access_instructions",
            "invoice",
            "payment",
        }
    )


@pytest.mark.asyncio
async def test_job_instructions_use_assignment_scope_and_omit_unclassified_text() -> None:
    job_id = uuid4()
    branch_id = uuid4()
    assignment = SimpleNamespace(id=uuid4(), branch_id=branch_id, version=7)
    job = SimpleNamespace(
        id=job_id,
        concurrency_version=4,
        customer_reported_problem="Synthetic customer reports no cooling.",
        internal_description="Office-only synthetic note.",
        updated_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
    )
    field = SimpleNamespace(_assigned_job=AsyncMock(return_value=assignment))
    service = FieldSourceService(field)  # type: ignore[arg-type]
    session = SimpleNamespace(scalar=AsyncMock(return_value=job))
    context = SimpleNamespace(
        company=SimpleNamespace(id=uuid4()), authorized_branch_ids=(branch_id,)
    )

    result = await service.job_instructions(
        session, context=context, job_id=job_id  # type: ignore[arg-type]
    )

    field._assigned_job.assert_awaited_once_with(session, context, job_id)
    assert result.customer_reported_problem == "Synthetic customer reports no cooling."
    assert "Office-only synthetic note." not in result.model_dump_json()
    assert "job_internal_description" in result.omitted_unclassified_fields
    assert "location_gate_code" in result.omitted_unclassified_fields


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
