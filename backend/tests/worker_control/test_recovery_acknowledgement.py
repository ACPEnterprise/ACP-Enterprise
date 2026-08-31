from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import ForeignKeyConstraint

from app.engineering_execution.controlled.models import ControlledExecutionOfferModel
from app.worker_control.models import WorkerRecoveryAcknowledgement
from app.worker_control.recovery_acknowledgement import (
    RecoveryAcknowledgementError,
    RecoveryAcknowledgementRequest,
    RecoveryAcknowledgementService,
    recovery_acknowledgement_failure,
)


def test_recovery_acknowledgement_is_bound_to_exact_offer_lineage() -> None:
    constraint = next(
        value
        for value in WorkerRecoveryAcknowledgement.__table__.constraints
        if isinstance(value, ForeignKeyConstraint)
        and value.name == "fk_worker_recovery_ack_offer_lineage"
    )
    expected = (
        "company_id",
        "offer_id",
        "command_id",
        "execution_id",
        "lease_id",
        "worker_id",
    )

    assert tuple(column.name for column in constraint.columns) == expected
    assert tuple(element.target_fullname for element in constraint.elements) == (
        "engineering_controlled_execution_offers.company_id",
        "engineering_controlled_execution_offers.id",
        "engineering_controlled_execution_offers.command_id",
        "engineering_controlled_execution_offers.execution_id",
        "engineering_controlled_execution_offers.lease_id",
        "engineering_controlled_execution_offers.worker_id",
    )
    assert any(
        value.name == "uq_controlled_offers_recovery_binding"
        for value in ControlledExecutionOfferModel.__table__.constraints
    )


def test_recovery_api_failure_is_classified_and_non_reflective() -> None:
    canary = "worker-credential=recovery-canary provider-journal=/private/path"
    failure = recovery_acknowledgement_failure()

    assert failure.status_code == 409
    assert failure.detail["code"] == "reconciliation_required"
    assert failure.detail["recovery"] == "RECONCILIATION_REQUIRED"
    assert canary not in str(failure.detail)


def _request() -> RecoveryAcknowledgementRequest:
    return RecoveryAcknowledgementRequest(
        worker_id=uuid4(),
        command_id=uuid4(),
        execution_id=uuid4(),
        offer_id=uuid4(),
        lease_id=uuid4(),
        journal_digest="a" * 64,
        reconciliation_reason="expired_lease_unresolved_provider_outcome",
        acknowledgement_reason="Owner acknowledged preserved historical ambiguity.",
    )


def _context():
    return SimpleNamespace(
        company=SimpleNamespace(id=uuid4()),
        user=SimpleNamespace(id=uuid4()),
        authorization_version=3,
        credential_version=2,
    )


def _session(values):
    session = MagicMock()
    session.scalar = AsyncMock(side_effect=values)
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session


def _lineage(request, *, lease_status="expired", released=True, result=None):
    worker = SimpleNamespace(id=request.worker_id)
    execution = SimpleNamespace(
        id=request.execution_id,
        command_id=request.command_id,
        evidence_summary={
            "reconciliation_required": True,
            "reconciliation_reason": request.reconciliation_reason,
        },
    )
    offer = SimpleNamespace(id=request.offer_id)
    lease = SimpleNamespace(
        id=request.lease_id,
        status=lease_status,
        released_at=object() if released else None,
    )
    return [None, worker, execution, offer, lease, None, result]


@pytest.mark.asyncio
async def test_wrong_company_worker_or_execution_lineage_fails_closed() -> None:
    request = _request()
    for missing_index in (1, 2, 3, 4):
        values = _lineage(request)
        values[missing_index] = None
        session = _session(values)
        with pytest.raises(RecoveryAcknowledgementError, match="lineage"):
            await RecoveryAcknowledgementService().acknowledge(
                session, context=_context(), request=request
            )
        session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_or_unreleased_lease_fails_closed() -> None:
    request = _request()
    for status, released in (("active", False), ("expired", False)):
        session = _session(_lineage(request, lease_status=status, released=released))
        with pytest.raises(RecoveryAcknowledgementError, match="active or unreleased"):
            await RecoveryAcknowledgementService().acknowledge(
                session, context=_context(), request=request
            )
        session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_deliverable_result_fails_closed() -> None:
    request = _request()
    session = _session(_lineage(request, result=uuid4()))
    with pytest.raises(RecoveryAcknowledgementError, match="deliverable"):
        await RecoveryAcknowledgementService().acknowledge(
            session, context=_context(), request=request
        )
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_released_lease_creates_durable_unresolved_acknowledgement() -> None:
    request = _request()
    session = _session(_lineage(request))
    record = await RecoveryAcknowledgementService().acknowledge(
        session, context=_context(), request=request
    )
    assert record.execution_id == request.execution_id
    assert record.historical_execution_unresolved is True
    assert record.active_block_released is False
    assert len(record.audit_digest) == 64
    session.flush.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_identical_replay_is_idempotent_and_conflict_rejected() -> None:
    request = _request()
    existing = SimpleNamespace(
        command_id=request.command_id,
        execution_id=request.execution_id,
        offer_id=request.offer_id,
        lease_id=request.lease_id,
        reconciliation_reason=request.reconciliation_reason,
        acknowledgement_reason=request.acknowledgement_reason,
        acknowledgement_version=request.acknowledgement_version,
    )
    session = _session([existing])
    assert (
        await RecoveryAcknowledgementService().acknowledge(
            session, context=_context(), request=request
        )
        is existing
    )
    session.commit.assert_not_awaited()

    conflicting = request.model_copy(update={"lease_id": uuid4()})
    session = _session([existing])
    with pytest.raises(RecoveryAcknowledgementError, match="conflicts"):
        await RecoveryAcknowledgementService().acknowledge(
            session, context=_context(), request=conflicting
        )


@pytest.mark.asyncio
async def test_local_application_is_idempotent_and_digest_conflict_fails_closed() -> None:
    acknowledgement_id = uuid4()
    company_id = uuid4()
    worker_id = uuid4()
    record = SimpleNamespace(
        id=acknowledgement_id,
        execution_id=uuid4(),
        applied_at=None,
        local_archive_digest=None,
        active_block_released=False,
    )
    session = _session([record])
    applied = await RecoveryAcknowledgementService().applied(
        session,
        company_id=company_id,
        worker_id=worker_id,
        acknowledgement_id=acknowledgement_id,
        local_archive_digest="c" * 64,
    )
    assert applied.active_block_released is True
    assert applied.local_archive_digest == "c" * 64
    session.commit.assert_awaited_once()

    session = _session([record])
    assert (
        await RecoveryAcknowledgementService().applied(
            session,
            company_id=company_id,
            worker_id=worker_id,
            acknowledgement_id=acknowledgement_id,
            local_archive_digest="c" * 64,
        )
        is record
    )
    session.commit.assert_not_awaited()

    session = _session([record])
    with pytest.raises(RecoveryAcknowledgementError, match="digest conflicts"):
        await RecoveryAcknowledgementService().applied(
            session,
            company_id=company_id,
            worker_id=worker_id,
            acknowledgement_id=acknowledgement_id,
            local_archive_digest="d" * 64,
        )
