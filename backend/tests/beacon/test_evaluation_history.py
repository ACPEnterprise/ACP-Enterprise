from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from app.beacon.evaluation import signal_evaluation_service
from app.beacon.history import (
    BeaconEvaluationConflictError,
    EvaluationDisposition,
    beacon_evaluation_history_service,
)
from app.beacon.models import BeaconEvaluationRunModel, BeaconSignalEvaluationModel
from app.core.config import settings
from app.customers.models import Customer  # noqa: F401
from app.platform.company.models import Company
from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.beacon.test_beacon import NOW, snapshot


@pytest_asyncio.fixture
async def history_session():
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    company = Company(
        id=uuid4(),
        name="Beacon history qualification",
        code=f"BEACON{uuid4().hex[:8].upper()}",
        status="active",
        timezone="UTC",
        created_at=NOW,
        updated_at=NOW,
    )
    async with factory() as session:
        session.add(company)
        await session.commit()
        yield session, company.id
        await session.rollback()
    await engine.dispose()


@pytest.mark.asyncio
async def test_evaluation_history_is_idempotent_versioned_and_resolution_safe(
    history_session,
) -> None:
    session, company_id = history_session
    signals = signal_evaluation_service.evaluate_signals(snapshot())
    covered = tuple(signal.definition_id for signal in signals)
    first = await beacon_evaluation_history_service.record_completed_run(
        session,
        company_id=company_id,
        branch_id=None,
        scope_identity="a" * 64,
        evaluated_at=NOW,
        evidence_as_of=NOW,
        evaluator_version="beacon.snapshot.v1",
        covered_definitions=covered,
        provenance={"adapter": "qualification", "version": 1},
        signals=signals,
    )
    await session.commit()
    assert {item.disposition for item in first.records} == {EvaluationDisposition.NEW}

    replay = await beacon_evaluation_history_service.record_completed_run(
        session,
        company_id=company_id,
        branch_id=None,
        scope_identity="a" * 64,
        evaluated_at=NOW,
        evidence_as_of=NOW,
        evaluator_version="beacon.snapshot.v1",
        covered_definitions=covered,
        provenance={"adapter": "qualification", "version": 1},
        signals=signals,
    )
    assert replay.id == first.id
    assert tuple(item.id for item in replay.records) == tuple(
        item.id for item in first.records
    )

    changed_signal = replace(
        signals[0], id=uuid4(), evidence_digest="b" * 64, created_at=NOW
    )
    second = await beacon_evaluation_history_service.record_completed_run(
        session,
        company_id=company_id,
        branch_id=None,
        scope_identity="a" * 64,
        evaluated_at=NOW + timedelta(hours=1),
        evidence_as_of=NOW + timedelta(hours=1),
        evaluator_version="beacon.snapshot.v1",
        covered_definitions=covered,
        provenance={"adapter": "qualification", "version": 1},
        signals=(changed_signal, *signals[1:]),
    )
    await session.commit()
    changed = next(
        item
        for item in second.records
        if item.condition_key == changed_signal.condition_key
    )
    assert changed.disposition is EvaluationDisposition.CHANGED
    assert changed.prior_evaluation_id is not None

    third = await beacon_evaluation_history_service.record_completed_run(
        session,
        company_id=company_id,
        branch_id=None,
        scope_identity="a" * 64,
        evaluated_at=NOW + timedelta(hours=2),
        evidence_as_of=NOW + timedelta(hours=2),
        evaluator_version="beacon.snapshot.v1",
        covered_definitions=covered,
        provenance={"adapter": "qualification", "version": 1},
        signals=(),
    )
    await session.commit()
    assert len(third.records) == len(signals)
    assert all(
        item.disposition is EvaluationDisposition.EXPIRED for item in third.records
    )
    deltas = await beacon_evaluation_history_service.deltas(
        session,
        company_id=company_id,
        branch_id=None,
        since=NOW - timedelta(seconds=1),
        until=NOW + timedelta(hours=3),
    )
    assert {
        EvaluationDisposition.NEW,
        EvaluationDisposition.CHANGED,
        EvaluationDisposition.STILL_ACTIVE,
        EvaluationDisposition.EXPIRED,
    }.issubset({item.disposition for item in deltas})
    assert await beacon_evaluation_history_service.has_completed_run(
        session,
        company_id=company_id,
        branch_id=None,
        since=NOW - timedelta(seconds=1),
        until=NOW + timedelta(hours=3),
    )


@pytest.mark.asyncio
async def test_contradictory_replay_and_direct_mutation_fail_closed(
    history_session,
) -> None:
    session, company_id = history_session
    signals = signal_evaluation_service.evaluate_signals(snapshot())
    covered = tuple(signal.definition_id for signal in signals)
    run = await beacon_evaluation_history_service.record_completed_run(
        session,
        company_id=company_id,
        branch_id=None,
        scope_identity="c" * 64,
        evaluated_at=NOW,
        evidence_as_of=NOW,
        evaluator_version="beacon.snapshot.v1",
        covered_definitions=covered,
        provenance={"adapter": "qualification"},
        signals=signals,
    )
    await session.commit()
    with pytest.raises(BeaconEvaluationConflictError):
        await beacon_evaluation_history_service.record_completed_run(
            session,
            company_id=company_id,
            branch_id=None,
            scope_identity="c" * 64,
            evaluated_at=NOW,
            evidence_as_of=NOW,
            evaluator_version="beacon.snapshot.v1",
            covered_definitions=covered,
            provenance={"adapter": "contradictory"},
            signals=signals,
        )

    with pytest.raises(IntegrityError):
        await session.execute(
            update(BeaconSignalEvaluationModel)
            .where(BeaconSignalEvaluationModel.id == run.records[0].id)
            .values(disposition="resolved")
        )
    await session.rollback()
    with pytest.raises(IntegrityError):
        await session.execute(
            delete(BeaconEvaluationRunModel).where(
                BeaconEvaluationRunModel.id == run.id
            )
        )
    await session.rollback()
