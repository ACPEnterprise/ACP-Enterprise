# ruff: noqa: F401, F811 -- imported pytest fixture is consumed by name

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError

from app.dispatch.models import DispatchAssignment
from app.field_service.artifacts import FieldArtifactService
from app.field_service.models import FieldArtifactEvidence
from app.field_service.schemas import (
    FieldArtifactFinalizeInput,
    FieldArtifactIntentInput,
)
from app.field_service.service import FieldService
from app.jobs.models import Job
from tests.dispatch.test_dispatch_service import dispatch_fixture


@pytest.mark.asyncio
async def test_field_artifact_replay_and_database_immutability(dispatch_fixture) -> None:
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
            assignment_reason="Artifact qualification",
            assigned_by_user_id=context.user.id,
            window_start_at=appointment.arrival_window_start_at,
            window_end_at=appointment.arrival_window_end_at,
            effective_at=now,
            version=1,
        )
        session.add(assignment)

    service = FieldArtifactService(FieldService())
    intent_input = FieldArtifactIntentInput(
        artifact_class="photo",
        media_type="image/jpeg",
        expected_size=128,
        expected_digest="a" * 64,
        idempotency_key="field-artifact-persistence-1",
        expected_assignment_version=1,
    )
    async with factory() as session:
        intent = await service.create_intent(
            session, context=context, job_id=job.id, payload=intent_input
        )
    async with factory() as session:
        replay = await service.create_intent(
            session, context=context, job_id=job.id, payload=intent_input
        )
    assert replay.intent_id == intent.intent_id

    final_input = FieldArtifactFinalizeInput(
        content_digest="a" * 64,
        size=128,
        media_type="image/jpeg",
        opaque_storage_reference="synthetic:field-object-1",
    )
    async with factory() as session:
        artifact = await service.finalize(
            session,
            context=context,
            job_id=job.id,
            intent_id=intent.intent_id,
            payload=final_input,
        )
    async with factory() as session:
        replayed = await service.finalize(
            session,
            context=context,
            job_id=job.id,
            intent_id=intent.intent_id,
            payload=final_input,
        )
    assert replayed.artifact_id == artifact.artifact_id

    async with factory() as session:
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(
                    update(FieldArtifactEvidence)
                    .where(FieldArtifactEvidence.id == artifact.artifact_id)
                    .values(size=129)
                )
                await session.flush()
    async with factory() as session:
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(
                    delete(FieldArtifactEvidence).where(
                        FieldArtifactEvidence.id == artifact.artifact_id
                    )
                )
                await session.flush()
