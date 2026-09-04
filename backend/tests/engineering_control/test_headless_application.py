from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.engineering_control.repository_operation.errors import (
    RepositoryOperationGitError,
)
from app.engineering_control.scheduler.application import (
    HeadlessApplicationError,
    HeadlessApplicationService,
)
from app.engineering_control.scheduler.approved_queue import (
    load_approved_factory_queue,
)
from app.engineering_control.scheduler.headless import HeadlessProposal


class Authority:
    def __init__(self, current: str, *, reject: bool = False):
        self.current = current
        self.reject = reject
        self.calls = []

    def verify_historical_publication(self, branch, commit_sha):
        self.calls.append((branch, commit_sha))
        if self.reject:
            raise RepositoryOperationGitError("not_ancestor", "not ancestor")
        return self.current


def context(company_id):
    return SimpleNamespace(company=SimpleNamespace(id=company_id))


def proposal(kind="activate"):
    return HeadlessProposal(
        kind=kind,
        milestone_id="MOBILE.PHYSICAL.ACCEPTANCE.HANDOFF.1",
        capacity_identity="OM1",
        reason="owner-approved executable queue item",
    )


@pytest.mark.asyncio
async def test_bridge_preserves_manage_approve_and_execution_contexts() -> None:
    queue = load_approved_factory_queue()
    company_id = uuid4()
    manage, approve, execute = (context(company_id) for _ in range(3))
    command = SimpleNamespace(
        id=uuid4(),
        version=1,
        instruction_digest="instruction",
        request_digest="request",
        repository_key="acp-enterprise",
        expected_branch="customer-management-v1",
        expected_head=queue.authoritative_repository_sha,
        requested_code_changes=True,
        execution_boundary_digest="a" * 64,
    )
    approved = SimpleNamespace(id=command.id)
    result = object()
    commands = SimpleNamespace(
        create_command=AsyncMock(return_value=command),
        approve_command=AsyncMock(return_value=approved),
    )
    executions = SimpleNamespace(request_execution=AsyncMock(return_value=result))
    current = "1258f59259580f44549ec3c09edffd7043c26d70"
    authority = Authority(current)
    service = HeadlessApplicationService(
        commands=commands, executions=executions, authority=authority
    )

    actual = await service.apply_proposal(
        object(),
        manage_context=manage,
        approve_context=approve,
        execution_context=execute,
        proposal=proposal(),
        expected_authority_sha=current,
        now=datetime.now(timezone.utc),
    )

    assert actual is result
    assert commands.create_command.await_args.kwargs["context"] is manage
    assert commands.approve_command.await_args.kwargs["context"] is approve
    assert executions.request_execution.await_args.kwargs["context"] is execute
    created = commands.create_command.await_args.kwargs["command"]
    assert created.expected_head == current
    assert authority.calls == [
        ("customer-management-v1", queue.authoritative_repository_sha)
    ]
    assert created.execution_boundary["forbidden_paths"] == [
        ".git/**",
        ".env*",
        "**/.env*",
    ]


@pytest.mark.asyncio
async def test_stale_reconciliation_uses_existing_authenticated_lease_lifecycle() -> None:
    transaction = AsyncMock()
    transaction.__aenter__.return_value = None
    transaction.__aexit__.return_value = None
    session = SimpleNamespace(begin=lambda: transaction)
    worker_context = object()
    controlled = SimpleNamespace(
        reconcile_expired_worker_leases_in_transaction=AsyncMock(return_value=2)
    )
    service = HeadlessApplicationService(controlled=controlled)
    now = datetime.now(timezone.utc)

    count = await service.reconcile_stale_executions(
        session, worker_context=worker_context, now=now
    )

    assert count == 2
    controlled.reconcile_expired_worker_leases_in_transaction.assert_awaited_once_with(
        session, worker_context=worker_context, now=now
    )


@pytest.mark.asyncio
async def test_bridge_rejects_reconciliation_retry_and_unattested_authority() -> None:
    company_id = uuid4()
    contexts = [context(company_id) for _ in range(3)]
    current = "1258f59259580f44549ec3c09edffd7043c26d70"
    service = HeadlessApplicationService(
        commands=SimpleNamespace(),
        executions=SimpleNamespace(),
        authority=Authority(current),
    )
    arguments = {
        "session": object(),
        "manage_context": contexts[0],
        "approve_context": contexts[1],
        "execution_context": contexts[2],
        "now": datetime.now(timezone.utc),
    }
    with pytest.raises(HeadlessApplicationError, match="lifecycle reconciliation"):
        await service.apply_proposal(
            **arguments,
            proposal=proposal("reconcile"),
            expected_authority_sha=load_approved_factory_queue().authoritative_repository_sha,
        )
    with pytest.raises(HeadlessApplicationError, match="not attested"):
        await service.apply_proposal(
            **arguments,
            proposal=proposal(),
            expected_authority_sha="0" * 40,
        )

    rejected = HeadlessApplicationService(
        commands=SimpleNamespace(),
        executions=SimpleNamespace(),
        authority=Authority(current, reject=True),
    )
    with pytest.raises(HeadlessApplicationError, match="not in authoritative lineage"):
        await rejected.apply_proposal(
            **arguments,
            proposal=proposal(),
            expected_authority_sha=current,
        )


def test_reviewed_queue_tracks_actual_factory_authority_gates_and_successors() -> None:
    queue = load_approved_factory_queue()
    by_id = {item.milestone_id: item for item in queue.items}
    assert by_id["MOBILE.PREVIEW.IDENTITY.FIXTURE.1"].queue_state == "AUTHORITATIVE"
    assert by_id["REVENUE.CYCLE.FAILURE.RECOVERY.ACCEPTANCE.1"].queue_state == "AUTHORITATIVE"
    admission = by_id["MIGRATION.HCP.SOURCE4.PREVIEW.ADMISSION.1"]
    assert admission.execution_mode == "preview_gated"
    assert admission.hard_boundary_operations == ("preview_data_admission",)
    live_v2 = by_id["MIGRATION.HCP.SOURCE4.LIVE.V2.RECONCILIATION.1"]
    assert live_v2.queue_state == "AUTHORITATIVE"
    assert live_v2.authoritative_commit_sha == (
        "e297f36bf4d1e4b176fa9b70aff7c771bfdb65d0"
    )
    assert admission.dependencies == (live_v2.milestone_id,)
    assert by_id["PRICEBOOK.ALLCOUNTY.MIGRATION.RECONCILIATION.1"].queue_state == "READY"
    assert by_id["COMMUNICATIONS.OPERATIONAL.MEASUREMENT.1"].queue_state == "READY"
    assert by_id["PRICEBOOK.OWNER.DECISION.WORKSPACE.1"].queue_state == "BLOCKED_DEPENDENCY"
