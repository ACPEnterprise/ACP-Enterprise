from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.engineering_control.repository_readiness import (
    RepositoryReadinessService,
    RepositoryReadinessTarget,
    active_readiness_target_eligible,
    readiness_is_current,
    readiness_prepared_at,
    readiness_requires_milestone_update,
    readiness_semantics,
    repository_preparation_required,
)


def target_eligible(**changes: object) -> bool:
    values: dict[str, object] = {
        "milestone_status": "ready",
        "milestone_reconciliation_state": "current",
        "command_id": None,
        "execution_id": None,
        "execution_state": None,
        "execution_finished_at": None,
        "execution_evidence": None,
    }
    values.update(changes)
    return active_readiness_target_eligible(**values)  # type: ignore[arg-type]


def test_actionable_ready_milestone_is_an_active_target() -> None:
    assert target_eligible()
    assert target_eligible(command_id=uuid4())


def test_complete_or_noncurrent_milestone_is_not_an_active_target() -> None:
    assert not target_eligible(milestone_status="completed")
    assert not target_eligible(milestone_reconciliation_state="superseded")


def test_historical_reconciliation_execution_is_not_an_active_target() -> None:
    assert not target_eligible(
        command_id=uuid4(),
        execution_id=uuid4(),
        execution_state="running",
        execution_evidence={"reconciliation_required": True},
    )


def test_projecting_historical_terminal_command_ready_does_not_reopen_it() -> None:
    assert not target_eligible(
        command_id=uuid4(),
        execution_id=uuid4(),
        execution_state="completed",
        execution_finished_at=datetime.now(timezone.utc),
    )


def test_current_running_execution_remains_an_active_target() -> None:
    assert target_eligible(
        milestone_status="running",
        command_id=uuid4(),
        execution_id=uuid4(),
        execution_state="running",
        execution_evidence={},
    )


def test_current_pre_dispatch_execution_remains_an_active_target() -> None:
    assert target_eligible(
        milestone_status="running",
        command_id=uuid4(),
        execution_id=uuid4(),
        execution_state="execution_not_connected",
        execution_finished_at=None,
        execution_evidence={"execution_connected": False},
    )


def test_terminal_pre_dispatch_rejection_is_not_an_active_target() -> None:
    assert not target_eligible(
        milestone_status="running",
        command_id=uuid4(),
        execution_id=uuid4(),
        execution_state="failed",
        execution_finished_at=datetime.now(timezone.utc),
        execution_evidence={"terminal_rejection": True},
    )


def evidence(now: datetime, **changes: object) -> dict[str, object]:
    readiness: dict[str, object] = {
        "ready": True,
        "repository_key": "acp-enterprise",
        "branch": "customer-management-v1",
        "candidate_head": "a" * 40,
        "observed_head": "a" * 40,
        "worker_id": str(uuid4()),
        "provider_software_sha": "a" * 40,
        "prepared_at": now.isoformat(),
    }
    readiness.update(changes)
    return {"provider_repository_readiness": readiness}


def test_matching_fresh_repository_evidence_is_ready() -> None:
    now = datetime.now(timezone.utc)
    value = evidence(now)
    assert readiness_is_current(
        value,
        repository_key="acp-enterprise",
        branch="customer-management-v1",
        candidate_head="a" * 40,
        now=now,
    )


def test_stale_observation_is_not_current_for_dispatch_authority() -> None:
    now = datetime.now(timezone.utc)
    assert not readiness_is_current(
        evidence(now - timedelta(minutes=3)),
        repository_key="acp-enterprise",
        branch="customer-management-v1",
        candidate_head="a" * 40,
        now=now,
    )


def test_mismatched_repository_evidence_fails_closed() -> None:
    now = datetime.now(timezone.utc)
    assert not readiness_is_current(
        evidence(now, observed_head="c" * 40),
        repository_key="acp-enterprise",
        branch="customer-management-v1",
        candidate_head="a" * 40,
        now=now,
    )


def test_mismatched_provider_runtime_fails_closed() -> None:
    now = datetime.now(timezone.utc)
    assert not readiness_is_current(
        evidence(now, provider_software_sha="b" * 40),
        repository_key="acp-enterprise",
        branch="customer-management-v1",
        candidate_head="a" * 40,
        now=now,
    )


def test_read_only_proof_role_requires_repository_preparation() -> None:
    assert repository_preparation_required(
        requested_code_changes=False,
        evidence={"proof_role": "repository_integrity"},
    )
    assert not repository_preparation_required(
        requested_code_changes=False,
        evidence={},
    )


def test_prepared_at_requires_an_aware_timestamp() -> None:
    now = datetime.now(timezone.utc)
    assert readiness_prepared_at({"prepared_at": now.isoformat()}) == now
    assert readiness_prepared_at({"prepared_at": "2026-08-29T12:00:00"}) is None


def test_repeated_observations_have_identical_action_semantics() -> None:
    now = datetime.now(timezone.utc)
    first = evidence(now)["provider_repository_readiness"]
    repeated = evidence(now + timedelta(seconds=31))["provider_repository_readiness"]
    assert isinstance(first, dict)
    assert isinstance(repeated, dict)
    repeated["worker_id"] = first["worker_id"]

    assert first["prepared_at"] != repeated["prepared_at"]
    assert readiness_semantics(first) == readiness_semantics(repeated)


def test_action_relevant_readiness_changes_are_not_idempotent() -> None:
    now = datetime.now(timezone.utc)
    current = evidence(now)["provider_repository_readiness"]
    changed = evidence(now, observed_head="c" * 40)["provider_repository_readiness"]
    assert isinstance(current, dict)
    assert isinstance(changed, dict)
    changed["worker_id"] = current["worker_id"]

    assert readiness_semantics(current) != readiness_semantics(changed)


def test_identical_heartbeat_does_not_require_milestone_version_update() -> None:
    now = datetime.now(timezone.utc)
    current = evidence(now)["provider_repository_readiness"]
    repeated = evidence(now + timedelta(seconds=31))["provider_repository_readiness"]
    assert isinstance(current, dict)
    assert isinstance(repeated, dict)
    repeated["worker_id"] = current["worker_id"]

    assert not readiness_requires_milestone_update(
        current,
        repeated,
        current_readiness_state="ready",
        desired_readiness_state="ready",
    )

    for elapsed_seconds in (62, 93, 124, 155):
        later = evidence(now + timedelta(seconds=elapsed_seconds))[
            "provider_repository_readiness"
        ]
        assert isinstance(later, dict)
        later["worker_id"] = current["worker_id"]
        assert not readiness_requires_milestone_update(
            current,
            later,
            current_readiness_state="ready",
            desired_readiness_state="ready",
        )


def test_semantic_or_readiness_state_change_requires_version_update() -> None:
    now = datetime.now(timezone.utc)
    current = evidence(now)["provider_repository_readiness"]
    changed = evidence(now, candidate_head="c" * 40)["provider_repository_readiness"]
    assert isinstance(current, dict)
    assert isinstance(changed, dict)
    changed["worker_id"] = current["worker_id"]

    assert readiness_requires_milestone_update(
        current,
        changed,
        current_readiness_state="ready",
        desired_readiness_state="ready",
    )
    assert readiness_requires_milestone_update(
        current,
        current,
        current_readiness_state="ready",
        desired_readiness_state="preparing_environment",
    )


@pytest.mark.asyncio
async def test_identical_authenticated_observation_refreshes_durable_freshness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    company_id, worker_id, milestone_id = uuid4(), uuid4(), uuid4()
    current = evidence(now)["provider_repository_readiness"]
    assert isinstance(current, dict)
    current["worker_id"] = str(worker_id)
    milestone = SimpleNamespace(
        starting_commit_evidence={"provider_repository_readiness": current},
        readiness_state="ready",
        version=7,
        updated_at=now,
    )
    service = RepositoryReadinessService()

    async def targets(*_args: object, **_kwargs: object):
        return (
            RepositoryReadinessTarget(
                milestone_id=milestone_id,
                repository_key="acp-enterprise",
                branch="customer-management-v1",
                candidate_head="a" * 40,
            ),
        )

    monkeypatch.setattr(service, "targets", targets)
    session = SimpleNamespace(scalar=lambda *_args, **_kwargs: milestone)

    async def scalar(*_args: object, **_kwargs: object):
        return milestone

    session.scalar = scalar
    refreshed_at = now + timedelta(seconds=31)
    await service.record(
        session,
        company_id=company_id,
        worker_id=worker_id,
        milestone_id=milestone_id,
        repository_key="acp-enterprise",
        branch="customer-management-v1",
        candidate_head="a" * 40,
        observed_head="a" * 40,
        provider_software_sha="a" * 40,
        prepared_at=refreshed_at,
        ready=True,
        reason_code=None,
    )

    durable = milestone.starting_commit_evidence["provider_repository_readiness"]
    assert readiness_prepared_at(durable) == refreshed_at
    assert milestone.version == 7
    assert milestone.updated_at == now


@pytest.mark.asyncio
async def test_older_observation_cannot_move_durable_freshness_backward(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    company_id, worker_id, milestone_id = uuid4(), uuid4(), uuid4()
    current = evidence(now)["provider_repository_readiness"]
    assert isinstance(current, dict)
    current["worker_id"] = str(worker_id)
    milestone = SimpleNamespace(
        starting_commit_evidence={"provider_repository_readiness": current},
        readiness_state="ready",
        version=7,
        updated_at=now,
    )
    service = RepositoryReadinessService()

    async def targets(*_args: object, **_kwargs: object):
        return (
            RepositoryReadinessTarget(
                milestone_id=milestone_id,
                repository_key="acp-enterprise",
                branch="customer-management-v1",
                candidate_head="a" * 40,
            ),
        )

    async def scalar(*_args: object, **_kwargs: object):
        return milestone

    monkeypatch.setattr(service, "targets", targets)
    session = SimpleNamespace(scalar=scalar)
    with pytest.raises(ValueError, match="older than durable evidence"):
        await service.record(
            session,
            company_id=company_id,
            worker_id=worker_id,
            milestone_id=milestone_id,
            repository_key="acp-enterprise",
            branch="customer-management-v1",
            candidate_head="a" * 40,
            observed_head="a" * 40,
            provider_software_sha="a" * 40,
            prepared_at=now - timedelta(seconds=1),
            ready=True,
            reason_code=None,
        )
    assert (
        readiness_prepared_at(
            milestone.starting_commit_evidence["provider_repository_readiness"]
        )
        == now
    )
