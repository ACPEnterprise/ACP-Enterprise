from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock
from uuid import uuid4

import pytest
from app.engineering_control.scheduler.approved_queue import load_approved_factory_queue
from app.engineering_control.scheduler.runner import HeadlessRunner


class Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_runner_is_singleton_and_does_nothing_without_lock() -> None:
    session = SimpleNamespace(scalar=AsyncMock(return_value=False))
    application = SimpleNamespace()
    result = await HeadlessRunner(application).run_once(
        session,
        admin_context=object(),
        worker_context=object(),
        expected_authority_sha="a" * 40,
        now=datetime.now(timezone.utc),
    )
    assert result == ()


@pytest.mark.asyncio
async def test_runner_applies_ready_items_and_never_preview_gated_work() -> None:
    scalar = AsyncMock(side_effect=[True, True])
    session = SimpleNamespace(
        scalar=scalar,
        execute=AsyncMock(return_value=Result([])),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    application = SimpleNamespace(
        reconcile_stale_executions=AsyncMock(return_value=0),
        apply_proposal=AsyncMock(return_value=object()),
    )
    admin = SimpleNamespace(company=SimpleNamespace(id=uuid4()))
    worker = object()

    applied = await HeadlessRunner(application).run_once(
        session,
        admin_context=admin,
        worker_context=worker,
        expected_authority_sha=load_approved_factory_queue().authoritative_repository_sha,
        now=datetime.now(timezone.utc),
    )

    assert "MIGRATION.HCP.SOURCE4.PREVIEW.ADMISSION.1" not in applied
    assert set(applied) == {
        "MOBILE.PHYSICAL.ACCEPTANCE.HANDOFF.1",
        "REVENUE.CYCLE.OFFICE.WORKFLOW.HARDENING.1",
        "ECO.OPERATIONAL.MEASUREMENT.MIGRATION.RECONCILIATION.1",
        "COMMUNICATIONS.OPERATIONAL.MEASUREMENT.1",
    }
    application.reconcile_stale_executions.assert_awaited_once_with(
        session, worker_context=worker, now=ANY
    )


def test_state_parser_supports_idempotent_completion_refill() -> None:
    queue = "ACP.72H.2026-09-03"
    states = HeadlessRunner._states(
        queue,
        [
            (
                f"{queue}:COMMUNICATIONS.OPERATIONAL.MEASUREMENT.1:{'a' * 40}",
                SimpleNamespace(value="completed"),
            )
        ],
    )
    assert states == {"COMMUNICATIONS.OPERATIONAL.MEASUREMENT.1": "completed"}
