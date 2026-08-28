# ruff: noqa: F401, F811 -- imported pytest fixture is consumed by name

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.dispatch.models import DispatchAssignment
from app.events.models import BusinessEvent
from app.field_service.errors import FieldServiceConflict, FieldServiceValidation
from app.field_service.models import (
    FieldCompletionEvidence,
    FieldCompletionRequirementSnapshot,
)
from app.field_service.schemas import ApprovalInput, NonBillableInput, NoteInput
from app.field_service.service import FieldService
from app.jobs.commands import CompleteJob
from app.jobs.models import Job
from app.jobs.service import job_service
from tests.dispatch.test_dispatch_service import dispatch_fixture


def test_business_day_bounds_use_configured_timezone_and_fail_closed() -> None:
    start, end = FieldService._service_day_bounds(date(2026, 8, 27), "America/New_York")
    assert start.isoformat() == "2026-08-27T04:00:00+00:00"
    assert end.isoformat() == "2026-08-28T03:59:59.999999+00:00"
    with pytest.raises(FieldServiceValidation, match="timezone is invalid"):
        FieldService._service_day_bounds(date(2026, 8, 27), "Invalid/Timezone")


@pytest.mark.asyncio
async def test_field_evidence_snapshot_replay_events_and_non_billable_completion(
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
            concurrency_version=3,
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
            assignment_reason="Field conformance test",
            assigned_by_user_id=context.user.id,
            window_start_at=appointment.arrival_window_start_at,
            window_end_at=appointment.arrival_window_end_at,
            effective_at=now,
            version=2,
        )
        session.add(assignment)
        await session.flush()

    service = FieldService()
    note = NoteInput(
        content="Installed and tested fixture.",
        idempotency_key="field-note-conformance-1",
        expected_job_version=3,
        expected_assignment_version=2,
    )
    async with factory() as session:
        first = await service.note(
            session, context=context, job_id=job.id, payload=note
        )
    async with factory() as session:
        replay = await service.note(
            session, context=context, job_id=job.id, payload=note
        )
    assert (
        first.requirement_snapshot_version == replay.requirement_snapshot_version == 1
    )

    async with factory() as session:
        state = await service.approval(
            session,
            context=context,
            job_id=job.id,
            payload=ApprovalInput(
                disposition="approved",
                customer_name="Pat Customer",
                idempotency_key="field-approval-conformance-1",
                expected_job_version=3,
                expected_assignment_version=2,
            ),
        )
        assert "commercial_authorization" in state.missing_requirements
    async with factory() as session:
        state = await service.non_billable(
            session,
            context=context,
            job_id=job.id,
            payload=NonBillableInput(
                reason="Warranty callback with no customer charge",
                idempotency_key="field-nonbillable-conformance-1",
                expected_job_version=3,
                expected_assignment_version=2,
            ),
        )
        assert state.commercial_authorization == "non_billable"
        assert state.completion_ready

    async with factory() as session:
        completed = await job_service.complete_job(
            session,
            context=context,
            command=CompleteJob(job_id=job.id, expected_version=3),
        )
        assert completed.status == "completed"
    async with factory() as session:
        snapshot = await session.scalar(
            select(FieldCompletionRequirementSnapshot).where(
                FieldCompletionRequirementSnapshot.job_id == job.id
            )
        )
        codes = set(
            (
                await session.scalars(
                    select(FieldCompletionEvidence.requirement_code).where(
                        FieldCompletionEvidence.job_id == job.id
                    )
                )
            ).all()
        )
        events = tuple(
            (
                await session.scalars(
                    select(BusinessEvent).where(BusinessEvent.entity_id == job.id)
                )
            ).all()
        )
    assert snapshot is not None
    assert snapshot.requirements == list(FieldService.COMPLETION_REQUIREMENTS)
    assert codes == set(FieldService.COMPLETION_REQUIREMENTS)
    completion_correlations = {
        event.event_type: event.correlation_id
        for event in events
        if event.event_type
        in {"field.completion_requirements_satisfied", "job.completed"}
    }
    assert (
        completion_correlations["field.completion_requirements_satisfied"]
        == completion_correlations["job.completed"]
    )

    async with factory() as session:
        with pytest.raises(FieldServiceConflict):
            await service.note(
                session,
                context=context,
                job_id=job.id,
                payload=note.model_copy(update={"content": "Contradictory content"}),
            )


@pytest.mark.asyncio
async def test_stale_field_versions_fail_closed(dispatch_fixture) -> None:
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
            concurrency_version=4,
            activated_at=now,
            started_at=now,
            created_by_user_id=context.user.id,
            updated_by_user_id=context.user.id,
        )
        session.add(job)
        await session.flush()
        session.add(
            DispatchAssignment(
                company_id=context.company.id,
                branch_id=context.active_branch.id,
                appointment_id=appointment.id,
                job_id=job.id,
                primary_employee_id=technician.id,
                status="acknowledged",
                assignment_reason="Stale field command test",
                assigned_by_user_id=context.user.id,
                window_start_at=appointment.arrival_window_start_at,
                window_end_at=appointment.arrival_window_end_at,
                effective_at=now,
                version=2,
            )
        )
    async with factory() as session:
        with pytest.raises(FieldServiceConflict, match="Job version is stale"):
            await FieldService().note(
                session,
                context=context,
                job_id=job.id,
                payload=NoteInput(
                    content="Should not persist",
                    idempotency_key="field-stale-conformance-1",
                    expected_job_version=3,
                    expected_assignment_version=2,
                ),
            )
