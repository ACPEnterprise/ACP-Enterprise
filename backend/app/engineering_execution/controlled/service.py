import json
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_control.models import EngineeringCommand
from app.engineering_control.records import EngineeringApprovalState
from app.engineering_execution.contracts import (
    EngineeringExecutionState,
    EngineeringExecutionStatus,
)
from app.engineering_execution.models import EngineeringExecution
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.permissions.authorization import (
    AuthorizationContext,
    AuthorizationService,
    PermissionDeniedError,
    authorization_service,
)
from app.platform.permissions.codes import EngineeringExecutionPermission
from app.worker_control.contracts import (
    AuthenticatedWorkerContext,
    ExecutionOffer,
    WorkerCapability,
)
from app.worker_control.models import WorkerLease
from app.worker_control.service import WorkerControlService
from app.worker_control.transport.contracts import WorkerSession

from .contracts import (
    ControlledExecutionOffer,
    ControlledExecutionResult,
    ControlledOfferState,
    ControlledOutcome,
    immutable_mapping,
)
from .errors import (
    ControlledExecutionConflictError,
    ControlledExecutionIneligibleError,
    ControlledExecutionNotFoundError,
    ControlledExecutionPayloadError,
)
from .repository import ControlledExecutionRepository

SAFE_WORKSPACE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,99}$")
SAFE_ERROR = re.compile(r"^[a-z][a-z0-9_]{2,79}$")
MAX_OUTPUT_BYTES = 8_000


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ControlledExecutionService:
    def __init__(
        self,
        *,
        repository: type[ControlledExecutionRepository] = ControlledExecutionRepository,
        workers: WorkerControlService | None = None,
        authorization: AuthorizationService = authorization_service,
        events: type[BusinessEventService] = BusinessEventService,
    ) -> None:
        self.repository = repository
        self.workers = workers or WorkerControlService()
        self.authorization = authorization
        self.events = events

    async def prepare_offer(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        execution_id: UUID,
        workspace_id: str,
        lease_seconds: int = 300,
        now: datetime | None = None,
    ) -> ControlledExecutionOffer:
        self._require(context)
        occurred_at = now or utc_now()
        workspace = workspace_id.strip().lower()
        if SAFE_WORKSPACE.fullmatch(workspace) is None:
            raise ControlledExecutionPayloadError("Workspace identifier is invalid.")
        if not 30 <= lease_seconds <= 900:
            raise ControlledExecutionPayloadError("Lease duration is invalid.")
        try:
            async with session.begin():
                source = await self.repository.load_authoritative_source(
                    session,
                    company_id=context.company.id,
                    execution_id=execution_id,
                )
                if source is None:
                    raise ControlledExecutionNotFoundError(
                        "Engineering Execution was not found."
                    )
                command, execution = source
                if (
                    command.approval_state != EngineeringApprovalState.APPROVED.value
                    or command.expires_at <= occurred_at
                    or command.canceled_at is not None
                    or command.requested_code_changes
                ):
                    raise ControlledExecutionIneligibleError(
                        "Engineering Command is not eligible for read-only execution."
                    )
                if (
                    execution.state
                    != EngineeringExecutionState.EXECUTION_NOT_CONNECTED.value
                ):
                    raise ControlledExecutionIneligibleError(
                        "Engineering Execution is not eligible for an offer."
                    )
                offer = await self.repository.create_offer(
                    session,
                    company_id=context.company.id,
                    command_id=command.id,
                    execution_id=execution.id,
                    correlation_id=execution.correlation_id,
                    workspace_id=workspace,
                    payload={
                        "manifest_name": "workspace-manifest.json",
                        "expected_branch": command.expected_branch,
                        "expected_head": command.expected_head,
                        "repository_key": command.repository_key,
                        "repository_mutation_allowed": False,
                    },
                    expires_at=min(
                        command.expires_at,
                        occurred_at + timedelta(seconds=lease_seconds),
                    ),
                    lease_seconds=lease_seconds,
                    now=occurred_at,
                )
                self._stage(
                    session,
                    offer=offer,
                    event_type=EventType.ENGINEERING_CONTROLLED_OFFER_CREATED,
                    now=occurred_at,
                )
            return offer
        except IntegrityError as error:
            await session.rollback()
            raise ControlledExecutionConflictError(
                "A controlled offer already exists for this execution."
            ) from error

    async def poll(
        self,
        database: AsyncSession,
        *,
        session: WorkerSession,
        limit: int,
    ) -> tuple[ExecutionOffer, ...]:
        if WorkerCapability.ENGINEERING_EXECUTE not in session.capabilities:
            return ()
        offers = await self.repository.list_available(
            database,
            company_id=session.context.company_id,
            now=utc_now(),
            limit=limit,
        )
        return tuple(
            ExecutionOffer(
                offer_id=offer.id,
                execution_id=offer.execution_id,
                correlation_id=offer.correlation_id,
                capability_required=offer.capability_required,
                lease_duration=timedelta(seconds=offer.lease_seconds),
                expires_at=offer.expires_at,
                metadata=immutable_mapping(
                    {
                        "command_id": str(offer.command_id),
                        "workspace_id": offer.workspace_id,
                        "command_type": offer.command_type.value,
                        **offer.payload,
                    }
                ),
            )
            for offer in offers
        )

    async def acquire_in_transaction(
        self,
        database: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        session_id: UUID,
        offer_id: UUID,
        now: datetime,
    ) -> ControlledExecutionOffer:
        offer = await self.repository.get_offer_for_update(
            database,
            company_id=worker_context.company_id,
            offer_id=offer_id,
        )
        if offer is None:
            raise ControlledExecutionNotFoundError("Execution offer was not found.")
        if (
            offer.state != ControlledOfferState.AVAILABLE.value
            or offer.expires_at <= now
        ):
            raise ControlledExecutionIneligibleError("Execution offer is unavailable.")
        lease = await self.workers.acquire_lease_in_transaction(
            database,
            worker_context=worker_context,
            offer=ExecutionOffer(
                offer_id=offer.id,
                execution_id=offer.execution_id,
                correlation_id=offer.correlation_id,
                capability_required=WorkerCapability(offer.capability_required),
                lease_duration=timedelta(seconds=offer.lease_seconds),
                expires_at=offer.expires_at,
                metadata=immutable_mapping({}),
            ),
            now=now,
        )
        bound = await self.repository.bind_offer(
            database,
            offer=offer,
            lease_id=lease.id,
            worker_id=worker_context.worker_id,
            session_id=session_id,
            now=now,
        )
        execution = await database.get(EngineeringExecution, offer.execution_id)
        if execution is None:
            raise ControlledExecutionNotFoundError(
                "Engineering Execution was not found."
            )
        execution.state = EngineeringExecutionState.RUNNING.value
        execution.status = EngineeringExecutionStatus.RUNNING.value
        execution.failure_classification = None
        execution.started_at = now
        execution.updated_at = now
        execution.version += 1
        self._stage(
            database,
            offer=bound,
            event_type=EventType.ENGINEERING_CONTROLLED_OFFER_ACQUIRED,
            now=now,
        )
        return bound

    async def complete_in_transaction(
        self,
        database: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        session_id: UUID,
        offer_id: UUID,
        lease_id: UUID,
        outcome: ControlledOutcome,
        output: dict[str, object],
        error_classification: str | None,
        started_at: datetime,
        completed_at: datetime,
    ) -> ControlledExecutionResult:
        serialized = json.dumps(output, sort_keys=True, separators=(",", ":")).encode()
        if len(serialized) > MAX_OUTPUT_BYTES:
            raise ControlledExecutionPayloadError("Controlled result is too large.")
        if output.get("repository_mutated") is not False:
            raise ControlledExecutionPayloadError(
                "Controlled result must prove repository_mutated=false."
            )
        if outcome is ControlledOutcome.SUCCEEDED:
            expected = {
                "workspace_id",
                "repository_key",
                "branch",
                "head",
                "clean",
                "file_count",
                "file_boundary",
                "repository_mutated",
            }
            boundary = output.get("file_boundary")
            if (
                set(output) != expected
                or output.get("clean") is not True
                or not isinstance(output.get("file_count"), int)
                or not isinstance(boundary, (list, tuple))
                or output.get("file_count") != len(boundary)
                or len(boundary) > 500
                or any(
                    not isinstance(item, str)
                    or len(item) > 500
                    or not _safe_relative_path(item)
                    for item in boundary
                )
                or list(boundary) != sorted(set(boundary))
            ):
                raise ControlledExecutionPayloadError(
                    "Successful controlled result shape is invalid."
                )
        elif set(output) != {"repository_mutated"}:
            raise ControlledExecutionPayloadError(
                "Failed controlled result must not include untrusted output."
            )
        if (
            error_classification is not None
            and SAFE_ERROR.fullmatch(error_classification) is None
        ):
            raise ControlledExecutionPayloadError("Failure classification is invalid.")
        offer = await self.repository.get_offer_for_update(
            database,
            company_id=worker_context.company_id,
            offer_id=offer_id,
        )
        if offer is None:
            raise ControlledExecutionNotFoundError("Execution offer was not found.")
        if (
            offer.state != ControlledOfferState.ACQUIRED.value
            or offer.worker_id != worker_context.worker_id
            or offer.session_id != session_id
            or offer.lease_id != lease_id
        ):
            raise ControlledExecutionIneligibleError(
                "Execution result binding is invalid."
            )
        if outcome is ControlledOutcome.SUCCEEDED and (
            output.get("workspace_id") != offer.workspace_id
            or output.get("repository_key") != offer.payload.get("repository_key")
            or output.get("branch") != offer.payload.get("expected_branch")
            or output.get("head") != offer.payload.get("expected_head")
        ):
            raise ControlledExecutionPayloadError(
                "Controlled result does not match the immutable offer."
            )
        command = await database.get(EngineeringCommand, offer.command_id)
        lease = await database.get(WorkerLease, lease_id)
        if (
            command is None
            or command.company_id != worker_context.company_id
            or command.approval_state != EngineeringApprovalState.APPROVED.value
            or command.canceled_at is not None
            or command.expires_at <= completed_at
            or lease is None
            or lease.company_id != worker_context.company_id
            or lease.worker_id != worker_context.worker_id
            or lease.status != "active"
            or lease.expires_at <= completed_at
        ):
            raise ControlledExecutionIneligibleError(
                "Execution authority is no longer active."
            )
        if offer.expires_at <= completed_at:
            raise ControlledExecutionIneligibleError("Execution offer has expired.")
        if completed_at < started_at or started_at < (offer.acquired_at or started_at):
            raise ControlledExecutionPayloadError("Execution timestamps are invalid.")
        result = await self.repository.create_result(
            database,
            offer=offer,
            outcome=outcome,
            output=output,
            error_classification=error_classification,
            started_at=started_at,
            completed_at=completed_at,
        )
        await self.workers.release_lease_in_transaction(
            database,
            worker_context=worker_context,
            lease_id=lease_id,
            now=completed_at,
        )
        execution = await database.get(EngineeringExecution, offer.execution_id)
        if execution is None:
            raise ControlledExecutionNotFoundError(
                "Engineering Execution was not found."
            )
        succeeded = outcome is ControlledOutcome.SUCCEEDED
        execution.state = (
            EngineeringExecutionState.COMPLETED.value
            if succeeded
            else EngineeringExecutionState.FAILED.value
        )
        execution.status = (
            EngineeringExecutionStatus.SUCCEEDED.value
            if succeeded
            else EngineeringExecutionStatus.FAILED.value
        )
        execution.evidence_summary = dict(output)
        execution.validation_summary = {
            "controlled_execution": True,
            "repository_mutated": False,
        }
        execution.failure_classification = error_classification
        execution.finished_at = completed_at
        execution.updated_at = completed_at
        execution.version += 1
        self._stage(
            database,
            offer=_offer_record(offer),
            event_type=(
                EventType.ENGINEERING_CONTROLLED_EXECUTION_COMPLETED
                if succeeded
                else EventType.ENGINEERING_CONTROLLED_EXECUTION_FAILED
            ),
            now=completed_at,
            result_id=result.id,
        )
        return result

    def _require(self, context: AuthorizationContext) -> None:
        try:
            self.authorization.require_permission(
                context, EngineeringExecutionPermission.REQUEST
            )
        except PermissionDeniedError as error:
            raise ControlledExecutionNotFoundError(
                "Engineering Execution was not found."
            ) from error

    def _stage(
        self,
        session: AsyncSession,
        *,
        offer: ControlledExecutionOffer,
        event_type: EventType,
        now: datetime,
        result_id: UUID | None = None,
    ) -> None:
        self.events.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="engineering_controlled_execution",
                entity_id=result_id or offer.id,
                company_id=offer.company_id,
                payload={
                    "offer_id": str(offer.id),
                    "command_id": str(offer.command_id),
                    "execution_id": str(offer.execution_id),
                    "state": offer.state.value,
                    "capability": offer.capability_required.value,
                    "repository_mutated": False,
                },
                correlation_id=offer.correlation_id,
                occurred_at=now,
            ),
        )


def _offer_record(entity) -> ControlledExecutionOffer:
    from .repository import _offer

    return _offer(entity)


def _safe_relative_path(value: str) -> bool:
    parts = value.split("/")
    return (
        bool(value)
        and not value.startswith("/")
        and all(part not in {"", ".", "..", ".git"} for part in parts)
    )
