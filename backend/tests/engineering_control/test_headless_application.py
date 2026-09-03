from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.engineering_control.scheduler.application import (
    HeadlessApplicationError,
    HeadlessApplicationService,
)
from app.engineering_control.scheduler.approved_queue import (
    load_approved_factory_queue,
)
from app.engineering_control.scheduler.headless import HeadlessProposal


def context(company_id):
    return SimpleNamespace(company=SimpleNamespace(id=company_id))


def proposal(kind="activate"):
    return HeadlessProposal(
        kind=kind,
        milestone_id="BANK.DF.003",
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
    service = HeadlessApplicationService(commands=commands, executions=executions)

    actual = await service.apply_proposal(
        object(),
        manage_context=manage,
        approve_context=approve,
        execution_context=execute,
        proposal=proposal(),
        expected_authority_sha=queue.authoritative_repository_sha,
        now=datetime.now(timezone.utc),
    )

    assert actual is result
    assert commands.create_command.await_args.kwargs["context"] is manage
    assert commands.approve_command.await_args.kwargs["context"] is approve
    assert executions.request_execution.await_args.kwargs["context"] is execute
    created = commands.create_command.await_args.kwargs["command"]
    assert created.expected_head == queue.authoritative_repository_sha
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
async def test_bridge_rejects_reconciliation_retry_and_stale_authority() -> None:
    company_id = uuid4()
    contexts = [context(company_id) for _ in range(3)]
    service = HeadlessApplicationService(
        commands=SimpleNamespace(), executions=SimpleNamespace()
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
    with pytest.raises(HeadlessApplicationError, match="authority is stale"):
        await service.apply_proposal(
            **arguments,
            proposal=proposal(),
            expected_authority_sha="0" * 40,
        )


def test_reviewed_queue_is_fingerprinted_repository_only_and_successor_bounded() -> None:
    queue = load_approved_factory_queue()
    assert [item.milestone_id for item in queue.items] == [
        "BANK.DF.003",
        "BANK.DF.004",
    ]
    assert all(item.execution_mode == "repository_only" for item in queue.items)
    assert all(not item.hard_boundary_operations for item in queue.items)
    assert queue.items[0].successor_ids == ("BANK.DF.004",)
