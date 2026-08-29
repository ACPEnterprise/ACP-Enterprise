from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from app.beacon.contracts import BeaconWorkflowAction
from app.beacon.errors import BeaconWorkflowConflictError
from app.beacon.evaluation import SignalEvaluationService
from app.beacon.records import BeaconWorkflowState
from app.beacon.workflow import BeaconWorkflowCommand, BeaconWorkflowService
from app.platform.permissions.authorization import PermissionDeniedError
from app.platform.permissions.codes import BeaconPermission

from tests.beacon.test_beacon import COMPANY_ID, snapshot

NOW = datetime(2026, 7, 28, 16, 0, tzinfo=timezone.utc)
USER_A = UUID("10000000-0000-0000-0000-000000000001")
USER_B = UUID("10000000-0000-0000-0000-000000000002")
BRANCH_ID = UUID("20000000-0000-0000-0000-000000000001")


class Context:
    def __init__(self, user_id=USER_A, permissions=()):
        self.user = SimpleNamespace(id=user_id)
        self.company = SimpleNamespace(id=COMPANY_ID)
        self.membership = SimpleNamespace(id=uuid4(), has_all_branch_access=True)
        self.active_branch = SimpleNamespace(id=BRANCH_ID)
        self.authorized_branch_ids = frozenset({BRANCH_ID})
        self.permissions = frozenset(permissions)

    def has_permission(self, permission):
        return permission in self.permissions

    def can_access_branch(self, branch_id):
        return branch_id in self.authorized_branch_ids


def signal():
    return next(
        item
        for item in SignalEvaluationService().evaluate_signals(snapshot())
        if item.evidence_quality is not None
    )


def state(owner=None, acknowledged=False, version=0):
    item = signal()
    return BeaconWorkflowState(
        company_id=COMPANY_ID,
        branch_id=BRANCH_ID if version else None,
        condition_key=item.condition_key,
        signal_id=item.id,
        definition_id=item.evidence_quality.definition_id,
        definition_version=item.evidence_quality.definition_version,
        evidence_digest=item.evidence_digest,
        workflow_version=version,
        acknowledged=acknowledged,
        acknowledged_by_user_id=USER_A if acknowledged else None,
        acknowledged_at=NOW if acknowledged else None,
        owner_user_id=owner,
        owned_since=NOW if owner else None,
        last_action=None,
        last_actor_user_id=None,
        updated_at=None,
    )


def command(action, *, owner=None, version=0):
    item = signal()
    return BeaconWorkflowCommand(
        signal_id=item.id,
        evidence_digest=item.evidence_digest,
        request_id=uuid4(),
        action=action,
        expected_version=version,
        owner_user_id=owner,
    )


@pytest.mark.asyncio
async def test_acknowledgement_and_ownership_are_independent() -> None:
    service = BeaconWorkflowService()
    context = Context(permissions=(BeaconPermission.REVIEW, BeaconPermission.OWN))
    acknowledged = await service._resulting_state(
        object(),
        context=context,
        command=command(BeaconWorkflowAction.ACKNOWLEDGE),
        state=state(),
        signal=signal(),
        occurred_at=NOW,
    )
    claimed = await service._resulting_state(
        object(),
        context=context,
        command=command(BeaconWorkflowAction.CLAIM, version=1),
        state=acknowledged,
        signal=signal(),
        occurred_at=NOW,
    )

    assert acknowledged.acknowledged and acknowledged.owner_user_id is None
    assert claimed.acknowledged and claimed.owner_user_id == USER_A
    assert claimed.workflow_version == 2


@pytest.mark.asyncio
async def test_claim_is_explicit_and_dual_owner_fails_closed() -> None:
    service = BeaconWorkflowService()
    with pytest.raises(BeaconWorkflowConflictError, match="already owned"):
        await service._resulting_state(
            object(),
            context=Context(USER_B, (BeaconPermission.OWN,)),
            command=command(BeaconWorkflowAction.CLAIM, version=1),
            state=state(owner=USER_A, version=1),
            signal=signal(),
            occurred_at=NOW,
        )


@pytest.mark.asyncio
async def test_transfer_and_release_preserve_previous_state() -> None:
    service = BeaconWorkflowService()

    async def accept_owner(*_args):
        return None

    service._validate_owner = accept_owner  # type: ignore[method-assign]
    context = Context(permissions=(BeaconPermission.ASSIGN,))
    transferred = await service._resulting_state(
        object(),
        context=context,
        command=command(BeaconWorkflowAction.TRANSFER, owner=USER_B, version=1),
        state=state(owner=USER_A, version=1),
        signal=signal(),
        occurred_at=NOW,
    )
    released = await service._resulting_state(
        object(),
        context=context,
        command=command(BeaconWorkflowAction.RELEASE, version=2),
        state=transferred,
        signal=signal(),
        occurred_at=NOW,
    )

    assert transferred.owner_user_id == USER_B
    assert transferred.last_action is BeaconWorkflowAction.TRANSFER
    assert released.owner_user_id is None
    assert released.owned_since is None


def test_authorization_separates_review_claim_and_assignment() -> None:
    with pytest.raises(PermissionDeniedError):
        BeaconWorkflowService._authorize(
            Context(permissions=(BeaconPermission.REVIEW,)),
            command(BeaconWorkflowAction.CLAIM),
        )
    BeaconWorkflowService._authorize(
        Context(permissions=(BeaconPermission.OWN,)),
        command(BeaconWorkflowAction.CLAIM),
    )
    with pytest.raises(PermissionDeniedError):
        BeaconWorkflowService._authorize(
            Context(permissions=(BeaconPermission.OWN,)),
            command(BeaconWorkflowAction.ASSIGN, owner=USER_B),
        )


def test_priority_and_signal_identity_are_not_workflow_inputs() -> None:
    source = signal()
    workflow = replace(
        state(owner=USER_A, acknowledged=True, version=2),
        signal_id=source.id,
        evidence_digest=source.evidence_digest,
    )

    assert workflow.signal_id == source.id
    assert workflow.evidence_digest == source.evidence_digest
    assert not hasattr(workflow, "severity")
    assert not hasattr(workflow, "priority")


@pytest.mark.asyncio
async def test_exact_replay_uses_durable_event_without_re_evaluating_signal() -> None:
    service = BeaconWorkflowService()
    request_id = uuid4()
    source = signal()
    replay = SimpleNamespace(
        id=uuid4(),
        company_id=COMPANY_ID,
        branch_id=BRANCH_ID,
        condition_key=source.condition_key,
        signal_id=source.id,
        definition_id=source.evidence_quality.definition_id,
        definition_version=source.evidence_quality.definition_version,
        evidence_digest=source.evidence_digest,
        workflow_version=1,
        acknowledged_at=NOW,
        acknowledged_by_user_id=USER_A,
        owner_user_id=None,
        owned_since=None,
        action=BeaconWorkflowAction.ACKNOWLEDGE.value,
        actor_user_id=USER_A,
        previous_owner_user_id=None,
        workflow_request_id=request_id,
        action_at=NOW,
    )

    class Transaction:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *_args):
            return None

    session = SimpleNamespace(
        begin=MagicMock(return_value=Transaction()),
        scalar=AsyncMock(return_value=replay),
    )
    service._current_signal = AsyncMock(  # type: ignore[method-assign]
        side_effect=AssertionError("source evidence must not be re-evaluated")
    )
    result = await service.mutate(
        session,
        context=Context(permissions=(BeaconPermission.REVIEW,)),
        command=BeaconWorkflowCommand(
            signal_id=source.id,
            evidence_digest=source.evidence_digest,
            request_id=request_id,
            action=BeaconWorkflowAction.ACKNOWLEDGE,
        ),
        now=NOW,
    )

    assert result.request_id == request_id
    service._current_signal.assert_not_awaited()


@pytest.mark.asyncio
async def test_contradictory_replay_version_fails_closed() -> None:
    service = BeaconWorkflowService()
    source = signal()
    replay = SimpleNamespace(
        company_id=COMPANY_ID,
        branch_id=BRANCH_ID,
        signal_id=source.id,
        evidence_digest=source.evidence_digest,
        action=BeaconWorkflowAction.CLAIM.value,
        workflow_version=2,
        owner_user_id=USER_A,
    )
    session = SimpleNamespace(scalar=AsyncMock(return_value=replay))
    changed = BeaconWorkflowCommand(
        signal_id=source.id,
        evidence_digest=source.evidence_digest,
        request_id=uuid4(),
        action=BeaconWorkflowAction.CLAIM,
        expected_version=0,
    )

    with pytest.raises(BeaconWorkflowConflictError, match="reused"):
        await service._replay(
            session,
            Context(permissions=(BeaconPermission.OWN,)),
            changed,
        )


@pytest.mark.asyncio
async def test_assign_requires_unowned_state_and_transfer_requires_owned_state() -> None:
    service = BeaconWorkflowService()

    async def accept_owner(*_args):
        return None

    service._validate_owner = accept_owner  # type: ignore[method-assign]
    context = Context(permissions=(BeaconPermission.ASSIGN,))
    with pytest.raises(BeaconWorkflowConflictError, match="explicit transfer"):
        await service._resulting_state(
            object(),
            context=context,
            command=command(BeaconWorkflowAction.ASSIGN, owner=USER_B, version=1),
            state=state(owner=USER_A, version=1),
            signal=signal(),
            occurred_at=NOW,
        )


def test_irrelevant_command_fields_fail_closed() -> None:
    source = signal()
    with pytest.raises(BeaconWorkflowConflictError, match="Acknowledgement"):
        BeaconWorkflowService._validate_command(
            BeaconWorkflowCommand(
                signal_id=source.id,
                evidence_digest=source.evidence_digest,
                request_id=uuid4(),
                action=BeaconWorkflowAction.ACKNOWLEDGE,
                expected_version=0,
            )
        )
    with pytest.raises(BeaconWorkflowConflictError, match="explicit owner"):
        BeaconWorkflowService._validate_command(
            BeaconWorkflowCommand(
                signal_id=source.id,
                evidence_digest=source.evidence_digest,
                request_id=uuid4(),
                action=BeaconWorkflowAction.CLAIM,
                expected_version=0,
                owner_user_id=USER_B,
            )
        )
