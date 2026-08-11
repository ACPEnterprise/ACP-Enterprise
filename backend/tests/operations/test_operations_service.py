from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.jobs.types import JobPriority
from app.main import app
from app.operations.schemas import ServiceRequestCreate
from app.operations.service import OperationsService
from app.scheduling.service import CreateAppointmentCommand


def service_request() -> ServiceRequestCreate:
    start = datetime.now(timezone.utc) + timedelta(days=1)
    return ServiceRequestCreate(
        request_id=uuid4(),
        branch_id=uuid4(),
        customer_id=uuid4(),
        service_location_id=uuid4(),
        arrival_window_start_at=start,
        arrival_window_end_at=start + timedelta(hours=2),
        expected_duration_minutes=90,
        capacity_units=Decimal("1.00"),
        job_type_code="repair",
        priority=JobPriority.HIGH,
        customer_reported_problem="No cooling",
    )


@pytest.mark.asyncio
async def test_service_request_composes_scheduling_then_jobs_with_stable_identity() -> (
    None
):
    data = service_request()
    appointment = SimpleNamespace(id=uuid4())
    job = SimpleNamespace(id=uuid4())
    scheduling = SimpleNamespace(create_appointment=AsyncMock(return_value=appointment))
    jobs = SimpleNamespace(create_job_from_appointment=AsyncMock(return_value=job))
    service = OperationsService(scheduling=scheduling, jobs=jobs)
    command = CreateAppointmentCommand(
        idempotency_key=data.request_id,
        branch_id=data.branch_id,
        customer_id=data.customer_id,
        service_location_id=data.service_location_id,
        arrival_window_start_at=data.arrival_window_start_at,
        arrival_window_end_at=data.arrival_window_end_at,
        expected_duration_minutes=data.expected_duration_minutes,
        capacity_units=data.capacity_units,
    )

    result = await service.accept_service_request(
        SimpleNamespace(),
        context=SimpleNamespace(),
        request_id=data.request_id,
        appointment=command,
        job_type_code=data.job_type_code,
        priority=data.priority,
        customer_reported_problem=data.customer_reported_problem,
        internal_description=data.internal_description,
    )

    assert result.request_id == data.request_id
    assert result.appointment is appointment
    assert result.job is job
    job_command = jobs.create_job_from_appointment.await_args.kwargs["command"]
    assert job_command.appointment_id == appointment.id
    assert job_command.service_request_id == data.request_id


@pytest.mark.asyncio
async def test_service_request_rejects_mismatched_orchestration_identity() -> None:
    data = service_request()
    service = OperationsService(
        scheduling=SimpleNamespace(create_appointment=AsyncMock()),
        jobs=SimpleNamespace(create_job_from_appointment=AsyncMock()),
    )
    command = CreateAppointmentCommand(
        idempotency_key=uuid4(),
        branch_id=data.branch_id,
        customer_id=data.customer_id,
        service_location_id=data.service_location_id,
        arrival_window_start_at=data.arrival_window_start_at,
        arrival_window_end_at=data.arrival_window_end_at,
        expected_duration_minutes=data.expected_duration_minutes,
    )

    with pytest.raises(ValueError, match="identity"):
        await service.accept_service_request(
            SimpleNamespace(),
            context=SimpleNamespace(),
            request_id=data.request_id,
            appointment=command,
            job_type_code=None,
            priority=JobPriority.NORMAL,
            customer_reported_problem=None,
            internal_description=None,
        )


def test_service_request_contract_rejects_unknown_fields() -> None:
    data = service_request()
    with pytest.raises(ValueError):
        ServiceRequestCreate(**data.model_dump(), company_id=uuid4())


def test_service_request_route_is_registered_in_application_contract() -> None:
    operation = app.openapi()["paths"]["/api/v1/operations/service-requests"]["post"]
    assert operation["summary"] == "Accept a launch service request"
    assert operation["responses"]["201"]
