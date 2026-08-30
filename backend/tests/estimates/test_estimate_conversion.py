from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError

from app.estimates.contracts import (
    ConvertEstimateToJobSpec,
    EstimateDecisionSpec,
    EstimateTransitionSpec,
)
from app.estimates.errors import (
    EstimateConflictError,
    EstimateNotFoundError,
    EstimateValidationError,
)
from app.estimates.models import EstimateJobConversion, EstimateRevision
from app.estimates.service import EstimateService
from app.events.models import BusinessEvent
from app.jobs.models import Job
from tests.estimates.test_estimate_foundation import make_spec

pytest_plugins = ("tests.estimates.test_estimate_foundation",)


def transition(record, branch, actor) -> EstimateTransitionSpec:
    return EstimateTransitionSpec(
        company_id=record.company_id,
        branch_id=branch.id,
        estimate_id=record.id,
        expected_version=record.version,
        actor_user_id=actor.id,
        occurred_at=datetime.now(timezone.utc),
    )


async def approved_estimate(
    factory, company, branch, actor, customer, location, snapshot
):
    service = EstimateService()
    async with factory() as session:
        record = await service.create(
            session,
            spec=make_spec(company, branch, actor, customer, location, snapshot),
        )
    async with factory() as session:
        record = await service.send(session, spec=transition(record, branch, actor))
    async with factory() as session:
        return await service.approve(
            session,
            spec=EstimateDecisionSpec(
                company_id=record.company_id,
                branch_id=branch.id,
                estimate_id=record.id,
                expected_version=record.version,
                actor_user_id=actor.id,
                occurred_at=datetime.now(timezone.utc),
                customer_name="Pat Customer",
            ),
        )


def conversion_spec(record, branch, actor, *, key="estimate-to-job-1"):
    return ConvertEstimateToJobSpec(
        company_id=record.company_id,
        branch_id=branch.id,
        estimate_id=record.id,
        expected_version=record.version,
        actor_user_id=actor.id,
        idempotency_key=key,
        customer_reported_problem="Approved estimate scope",
    )


@pytest.mark.asyncio
async def test_approved_estimate_converts_once_with_snapshot_lineage(estimate_fixture):
    factory, company, branch, actor, customer, location, snapshot = estimate_fixture
    record = await approved_estimate(
        factory, company, branch, actor, customer, location, snapshot
    )
    original_revision = record.current_revision
    async with factory() as session:
        conversion = await EstimateService().convert_to_job(
            session, spec=conversion_spec(record, branch, actor)
        )
    assert conversion.estimate_revision_id == original_revision.id
    assert conversion.job_number == "JOB-000001"
    assert len(conversion.snapshot_lineage_digest) == 64
    async with factory() as session:
        job = await session.get(Job, conversion.job_id)
        assert job is not None
        assert (job.status, job.customer_id, job.service_location_id) == (
            "draft",
            customer.id,
            location.id,
        )
        persisted_revision = await session.get(EstimateRevision, original_revision.id)
        assert persisted_revision is not None
        assert persisted_revision.proposal_title == original_revision.proposal_title
        event = await session.scalar(
            select(BusinessEvent).where(
                BusinessEvent.entity_id == record.id,
                BusinessEvent.event_type == "estimate.converted",
            )
        )
        assert event is not None
        assert event.payload["job_id"] == str(job.id)


@pytest.mark.asyncio
async def test_conversion_retry_is_idempotent_and_different_key_fails(estimate_fixture):
    factory, company, branch, actor, customer, location, snapshot = estimate_fixture
    record = await approved_estimate(
        factory, company, branch, actor, customer, location, snapshot
    )
    spec = conversion_spec(record, branch, actor)
    async with factory() as session:
        first = await EstimateService().convert_to_job(session, spec=spec)
    async with factory() as session:
        replay = await EstimateService().convert_to_job(session, spec=spec)
    assert replay == first
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count(Job.id)).where(Job.company_id == company.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count(EstimateJobConversion.id)).where(
                    EstimateJobConversion.company_id == company.id
                )
            )
            == 1
        )
    async with factory() as session:
        with pytest.raises(EstimateConflictError, match="already been converted"):
            await EstimateService().convert_to_job(
                session, spec=replace(spec, idempotency_key="different")
            )


@pytest.mark.asyncio
async def test_conversion_replay_normalizes_key_and_emits_one_authority(
    estimate_fixture,
):
    factory, company, branch, actor, customer, location, snapshot = estimate_fixture
    record = await approved_estimate(
        factory, company, branch, actor, customer, location, snapshot
    )
    spec = conversion_spec(
        record, branch, actor, key=f"  estimate-concurrent-{uuid4()}  "
    )

    async with factory() as session:
        first = await EstimateService().convert_to_job(session, spec=spec)
    async with factory() as session:
        replay = await EstimateService().convert_to_job(session, spec=spec)
    assert first == replay
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count(Job.id)).where(Job.company_id == company.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count(EstimateJobConversion.id)).where(
                    EstimateJobConversion.company_id == company.id,
                    EstimateJobConversion.idempotency_key
                    == spec.idempotency_key.strip(),
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count(BusinessEvent.id)).where(
                    BusinessEvent.entity_id == record.id,
                    BusinessEvent.event_type == "estimate.converted",
                )
            )
            == 1
        )


@pytest.mark.asyncio
async def test_conversion_requires_approved_estimate(estimate_fixture):
    factory, company, branch, actor, customer, location, snapshot = estimate_fixture
    service = EstimateService()
    async with factory() as session:
        draft = await service.create(
            session,
            spec=make_spec(company, branch, actor, customer, location, snapshot),
        )
    spec = conversion_spec(draft, branch, actor)
    async with factory() as session:
        with pytest.raises(EstimateValidationError, match="Only an approved"):
            await service.convert_to_job(session, spec=spec)


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_dimension", ["version", "branch", "company"])
async def test_conversion_enforces_version_and_scope(
    estimate_fixture, invalid_dimension
):
    factory, company, branch, actor, customer, location, snapshot = estimate_fixture
    service = EstimateService()
    approved = await approved_estimate(
        factory, company, branch, actor, customer, location, snapshot
    )
    spec = conversion_spec(approved, branch, actor)
    if invalid_dimension == "version":
        spec = replace(spec, expected_version=1)
        error = EstimateConflictError
        message = "version is stale"
    elif invalid_dimension == "branch":
        spec = replace(spec, branch_id=uuid4())
        error = EstimateNotFoundError
        message = "authorized Branch"
    else:
        spec = replace(spec, company_id=uuid4())
        error = EstimateNotFoundError
        message = "not found"
    async with factory() as session:
        with pytest.raises(error, match=message):
            await service.convert_to_job(session, spec=spec)


@pytest.mark.asyncio
async def test_conversion_evidence_is_database_immutable(estimate_fixture):
    factory, company, branch, actor, customer, location, snapshot = estimate_fixture
    record = await approved_estimate(
        factory, company, branch, actor, customer, location, snapshot
    )
    async with factory() as session:
        conversion = await EstimateService().convert_to_job(
            session, spec=conversion_spec(record, branch, actor)
        )
    async with factory() as session:
        with pytest.raises(DBAPIError, match="immutable"):
            await session.execute(
                update(EstimateJobConversion)
                .where(EstimateJobConversion.id == conversion.id)
                .values(idempotency_key="changed")
            )
        await session.rollback()
