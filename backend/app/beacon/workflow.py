"""Durable, explicit human workflow for admitted operational signals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.beacon.contracts import BeaconWorkflowAction
from app.beacon.errors import (
    BeaconSignalNotFoundError,
    BeaconSignalStaleError,
    BeaconWorkflowConflictError,
    BeaconWorkflowOwnerInvalidError,
)
from app.beacon.models import BeaconSignalReviewEventModel
from app.beacon.records import BeaconSignal, BeaconWorkflowEvent, BeaconWorkflowState
from app.beacon.service import BeaconQueryService, beacon_query_service
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, AuditService
from app.platform.company.membership_models import Membership, MembershipBranchAccess
from app.platform.permissions.authorization import (
    AuthorizationContext,
    authorization_service,
)
from app.platform.permissions.codes import AnalyticsPermission, BeaconPermission


@dataclass(frozen=True)
class BeaconWorkflowCommand:
    signal_id: UUID
    evidence_digest: str
    request_id: UUID
    action: BeaconWorkflowAction
    expected_version: int | None = None
    owner_user_id: UUID | None = None


class BeaconWorkflowService:
    def __init__(
        self, query_service: BeaconQueryService = beacon_query_service
    ) -> None:
        self.query_service = query_service

    async def mutate(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: BeaconWorkflowCommand,
        now: datetime | None = None,
    ) -> BeaconWorkflowEvent:
        occurred_at = now or datetime.now(timezone.utc)
        self._authorize(context, command)
        self._validate_command(command)
        async with session.begin():
            replay = await self._replay(session, context, command)
            if replay is not None:
                return replay
            signal = await self._current_signal(session, context, command, occurred_at)
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"{context.company.id}:{signal.condition_key}"},
            )
            replay = await self._replay(session, context, command)
            if replay is not None:
                return replay
            current = await self._latest(
                session,
                company_id=context.company.id,
                condition_key=signal.condition_key,
                lock=True,
            )
            state = _state(current, signal, context.company.id)
            if (
                command.action is BeaconWorkflowAction.ACKNOWLEDGE
                and state.acknowledged
            ):
                acknowledged = await session.scalar(
                    select(BeaconSignalReviewEventModel)
                    .where(
                        BeaconSignalReviewEventModel.company_id == context.company.id,
                        BeaconSignalReviewEventModel.condition_key
                        == signal.condition_key,
                        BeaconSignalReviewEventModel.action == "acknowledge",
                        BeaconSignalReviewEventModel.workflow_version.is_not(None),
                    )
                    .order_by(BeaconSignalReviewEventModel.workflow_version)
                )
                assert acknowledged is not None
                return _event(acknowledged)
            if command.action is not BeaconWorkflowAction.ACKNOWLEDGE and (
                command.expected_version is None
                or command.expected_version != state.workflow_version
            ):
                raise BeaconWorkflowConflictError("Workflow version is stale.")
            resulting = await self._resulting_state(
                session,
                context=context,
                command=command,
                state=state,
                signal=signal,
                occurred_at=occurred_at,
            )
            quality = signal.evidence_quality
            assert quality is not None
            entity = BeaconSignalReviewEventModel(
                company_id=context.company.id,
                branch_id=resulting.branch_id,
                condition_key=signal.condition_key,
                signal_id=signal.id,
                definition_id=quality.definition_id,
                definition_version=quality.definition_version,
                rule_code=signal.rule_code,
                signal_source=signal.source.value,
                evidence_digest=signal.evidence_digest,
                action=resulting.last_action.value,
                actor_membership_id=context.membership.id,
                actor_user_id=context.user.id,
                action_at=occurred_at,
                snooze_until=None,
                workflow_request_id=command.request_id,
                workflow_version=resulting.workflow_version,
                acknowledged_by_user_id=resulting.acknowledged_by_user_id,
                acknowledged_at=resulting.acknowledged_at,
                previous_owner_user_id=state.owner_user_id,
                owner_user_id=resulting.owner_user_id,
                owned_since=resulting.owned_since,
                created_at=occurred_at,
            )
            session.add(entity)
            await session.flush()
            self._stage_evidence(session, entity, context)
            return _event(entity)

    async def current(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        condition_key: UUID,
    ) -> BeaconWorkflowState | None:
        authorization_service.require_permission(context, AnalyticsPermission.READ)
        row = await self._latest(
            session,
            company_id=context.company.id,
            condition_key=condition_key,
            lock=False,
        )
        if row is None:
            return None
        self._assert_branch(context, row.branch_id)
        return _state_from_row(row)

    async def history(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        condition_key: UUID,
        limit: int,
    ) -> tuple[BeaconWorkflowEvent, ...]:
        authorization_service.require_permission(context, AnalyticsPermission.READ)
        rows = tuple(
            (
                await session.scalars(
                    select(BeaconSignalReviewEventModel)
                    .where(
                        BeaconSignalReviewEventModel.company_id == context.company.id,
                        BeaconSignalReviewEventModel.condition_key == condition_key,
                        BeaconSignalReviewEventModel.workflow_version.is_not(None),
                    )
                    .order_by(BeaconSignalReviewEventModel.workflow_version.desc())
                    .limit(limit)
                )
            ).all()
        )
        if rows:
            self._assert_branch(context, rows[0].branch_id)
        return tuple(_event(row) for row in rows)

    async def _current_signal(
        self, session, context, command, occurred_at
    ) -> BeaconSignal:
        if len(command.evidence_digest) != 64:
            raise BeaconSignalStaleError("Signal evidence digest is invalid.")
        signals = await self.query_service.evaluate_current(
            session, company_id=context.company.id, measured_at=occurred_at
        )
        signal = next((item for item in signals if item.id == command.signal_id), None)
        if (
            signal is None
            or signal.evidence_quality is None
            or not signal.evidence_quality.conclusion_admissible
        ):
            raise BeaconSignalNotFoundError(
                "The admitted Company signal was not found."
            )
        if signal.evidence_digest != command.evidence_digest:
            raise BeaconSignalStaleError(
                "Signal evidence changed and must be reviewed again."
            )
        return signal

    async def _resulting_state(
        self, session, *, context, command, state, signal, occurred_at
    ):
        action = command.action
        owner = state.owner_user_id
        owned_since = state.owned_since
        acknowledged_by = state.acknowledged_by_user_id
        acknowledged_at = state.acknowledged_at
        if action is BeaconWorkflowAction.ACKNOWLEDGE:
            acknowledged_by = acknowledged_by or context.user.id
            acknowledged_at = acknowledged_at or occurred_at
        elif action is BeaconWorkflowAction.CLAIM:
            if owner not in (None, context.user.id):
                raise BeaconWorkflowConflictError("Signal is already owned.")
            owner = context.user.id
            owned_since = owned_since or occurred_at
        elif action in (BeaconWorkflowAction.ASSIGN, BeaconWorkflowAction.TRANSFER):
            if command.owner_user_id is None:
                raise BeaconWorkflowOwnerInvalidError(
                    "An explicit owner User is required."
                )
            await self._validate_owner(session, context, command.owner_user_id)
            if action is BeaconWorkflowAction.ASSIGN and owner is not None:
                raise BeaconWorkflowConflictError(
                    "An owned signal must use an explicit transfer."
                )
            if action is BeaconWorkflowAction.TRANSFER and owner is None:
                raise BeaconWorkflowConflictError("An unowned signal cannot transfer.")
            if owner == command.owner_user_id:
                raise BeaconWorkflowConflictError("Signal already has that owner.")
            owner = command.owner_user_id
            owned_since = occurred_at
        elif action is BeaconWorkflowAction.RELEASE:
            if owner is None:
                raise BeaconWorkflowConflictError("Signal is already unowned.")
            if owner != context.user.id and not context.has_permission(
                BeaconPermission.ASSIGN
            ):
                from app.platform.permissions.authorization import PermissionDeniedError

                raise PermissionDeniedError(
                    "Only the current owner or an assign-authorized User may release."
                )
            owner = None
            owned_since = None
        branch_id = state.branch_id or (
            context.active_branch.id if context.active_branch else None
        )
        if state.branch_id is not None:
            self._assert_branch(context, state.branch_id)
        return BeaconWorkflowState(
            company_id=context.company.id,
            branch_id=branch_id,
            condition_key=signal.condition_key,
            signal_id=signal.id,
            definition_id=signal.evidence_quality.definition_id,
            definition_version=signal.evidence_quality.definition_version,
            evidence_digest=signal.evidence_digest,
            workflow_version=state.workflow_version + 1,
            acknowledged=acknowledged_at is not None,
            acknowledged_by_user_id=acknowledged_by,
            acknowledged_at=acknowledged_at,
            owner_user_id=owner,
            owned_since=owned_since,
            last_action=action,
            last_actor_user_id=context.user.id,
            updated_at=occurred_at,
        )

    @staticmethod
    async def _latest(session, *, company_id, condition_key, lock):
        statement = (
            select(BeaconSignalReviewEventModel)
            .where(
                BeaconSignalReviewEventModel.company_id == company_id,
                BeaconSignalReviewEventModel.condition_key == condition_key,
                BeaconSignalReviewEventModel.workflow_version.is_not(None),
            )
            .order_by(BeaconSignalReviewEventModel.workflow_version.desc())
            .limit(1)
        )
        return await session.scalar(statement.with_for_update() if lock else statement)

    async def _replay(self, session, context, command):
        replay = await session.scalar(
            select(BeaconSignalReviewEventModel).where(
                BeaconSignalReviewEventModel.company_id == context.company.id,
                BeaconSignalReviewEventModel.workflow_request_id == command.request_id,
            )
        )
        if replay is None:
            return None
        self._assert_branch(context, replay.branch_id)
        if replay.workflow_version is None:
            raise BeaconWorkflowConflictError(
                "Workflow request identity has invalid durable evidence."
            )
        expected_version = (
            None
            if command.action is BeaconWorkflowAction.ACKNOWLEDGE
            else replay.workflow_version - 1
        )
        if (
            replay.signal_id != command.signal_id
            or replay.action != command.action.value
            or replay.evidence_digest != command.evidence_digest
            or command.expected_version != expected_version
            or (
                command.action
                in (BeaconWorkflowAction.ASSIGN, BeaconWorkflowAction.TRANSFER)
                and replay.owner_user_id != command.owner_user_id
            )
        ):
            raise BeaconWorkflowConflictError(
                "Workflow request identity was reused for another command."
            )
        return _event(replay)

    @staticmethod
    def _validate_command(command):
        if command.action is BeaconWorkflowAction.ACKNOWLEDGE and (
            command.expected_version is not None or command.owner_user_id is not None
        ):
            raise BeaconWorkflowConflictError(
                "Acknowledgement does not accept ownership or version fields."
            )
        if command.action in (
            BeaconWorkflowAction.CLAIM,
            BeaconWorkflowAction.RELEASE,
        ) and command.owner_user_id is not None:
            raise BeaconWorkflowConflictError(
                "Claim and release do not accept an explicit owner."
            )

    @staticmethod
    async def _validate_owner(session, context, user_id):
        membership = await session.scalar(
            select(Membership).where(
                Membership.company_id == context.company.id,
                Membership.user_id == user_id,
                Membership.status == "active",
            )
        )
        if membership is None:
            raise BeaconWorkflowOwnerInvalidError(
                "Owner is not an active Company User."
            )
        if context.active_branch and not membership.has_all_branch_access:
            access = await session.scalar(
                select(MembershipBranchAccess).where(
                    MembershipBranchAccess.membership_id == membership.id,
                    MembershipBranchAccess.branch_id == context.active_branch.id,
                )
            )
            if access is None:
                raise BeaconWorkflowOwnerInvalidError(
                    "Owner lacks access to the active Branch."
                )

    @staticmethod
    def _authorize(context, command):
        if command.action is BeaconWorkflowAction.ACKNOWLEDGE:
            required = BeaconPermission.REVIEW
        elif command.action is BeaconWorkflowAction.CLAIM:
            required = BeaconPermission.OWN
        elif (
            command.action is BeaconWorkflowAction.RELEASE
            and command.owner_user_id is None
        ):
            required = (
                BeaconPermission.OWN
                if context.has_permission(BeaconPermission.OWN)
                else BeaconPermission.ASSIGN
            )
        else:
            required = BeaconPermission.ASSIGN
        if not context.has_permission(required):
            from app.platform.permissions.authorization import PermissionDeniedError

            raise PermissionDeniedError(f"Missing required permission: {required}")

    @staticmethod
    def _assert_branch(context, branch_id):
        if branch_id is not None and not context.can_access_branch(branch_id):
            from app.platform.permissions.authorization import TenantAccessDeniedError

            raise TenantAccessDeniedError("Beacon workflow Branch is not authorized.")

    @staticmethod
    def _stage_evidence(session, entity, context):
        event_type = {
            "acknowledge": EventType.BEACON_SIGNAL_ACKNOWLEDGED,
            "claim": EventType.BEACON_SIGNAL_CLAIMED,
            "assign": EventType.BEACON_SIGNAL_ASSIGNED,
            "transfer": EventType.BEACON_SIGNAL_TRANSFERRED,
            "release": EventType.BEACON_SIGNAL_RELEASED,
        }[entity.action]
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="beacon_signal",
                entity_id=entity.signal_id,
                company_id=entity.company_id,
                branch_id=entity.branch_id,
                user_id=entity.actor_user_id,
                payload={
                    "condition_key": str(entity.condition_key),
                    "definition_id": entity.definition_id,
                    "definition_version": entity.definition_version,
                    "workflow_version": entity.workflow_version,
                    "owner_user_id": str(entity.owner_user_id)
                    if entity.owner_user_id
                    else None,
                    "evidence_digest": entity.evidence_digest,
                },
                correlation_id=entity.workflow_request_id,
                occurred_at=entity.action_at,
            ),
        )
        AuditService.stage(
            session,
            AuditEntry(
                action=f"beacon.signal_{entity.action}",
                resource_type="beacon_signal",
                actor_user_id=context.user.id,
                company_id=context.company.id,
                branch_id=entity.branch_id,
                resource_id=entity.signal_id,
                correlation_id=entity.workflow_request_id,
                details={
                    "condition_key": str(entity.condition_key),
                    "workflow_version": entity.workflow_version,
                    "previous_owner_user_id": str(entity.previous_owner_user_id)
                    if entity.previous_owner_user_id
                    else None,
                    "owner_user_id": str(entity.owner_user_id)
                    if entity.owner_user_id
                    else None,
                },
                occurred_at=entity.action_at,
            ),
        )


def _state(row, signal, company_id):
    return (
        _state_from_row(row)
        if row
        else BeaconWorkflowState(
            company_id=company_id,
            branch_id=None,
            condition_key=signal.condition_key,
            signal_id=signal.id,
            definition_id=signal.evidence_quality.definition_id,
            definition_version=signal.evidence_quality.definition_version,
            evidence_digest=signal.evidence_digest,
            workflow_version=0,
            acknowledged=False,
            acknowledged_by_user_id=None,
            acknowledged_at=None,
            owner_user_id=None,
            owned_since=None,
            last_action=None,
            last_actor_user_id=None,
            updated_at=None,
        )
    )


def _state_from_row(row):
    return BeaconWorkflowState(
        company_id=row.company_id,
        branch_id=row.branch_id,
        condition_key=row.condition_key,
        signal_id=row.signal_id,
        definition_id=row.definition_id,
        definition_version=row.definition_version,
        evidence_digest=row.evidence_digest,
        workflow_version=row.workflow_version,
        acknowledged=row.acknowledged_at is not None,
        acknowledged_by_user_id=row.acknowledged_by_user_id,
        acknowledged_at=row.acknowledged_at,
        owner_user_id=row.owner_user_id,
        owned_since=row.owned_since,
        last_action=BeaconWorkflowAction(row.action),
        last_actor_user_id=row.actor_user_id,
        updated_at=row.action_at,
    )


def _event(row):
    return BeaconWorkflowEvent(
        id=row.id,
        state=_state_from_row(row),
        action=BeaconWorkflowAction(row.action),
        actor_user_id=row.actor_user_id,
        previous_owner_user_id=row.previous_owner_user_id,
        request_id=row.workflow_request_id,
        occurred_at=row.action_at,
    )


beacon_workflow_service = BeaconWorkflowService()
