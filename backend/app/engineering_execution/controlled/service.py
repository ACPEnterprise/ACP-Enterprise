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
from app.execution_nodes.models import ProviderExecutionTransition
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
    ControlledCommandType,
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
MAX_OUTPUT_BYTES = 128_000


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
        await self.reconcile_acknowledged_code_commands(
            database, worker_session=session
        )
        offers = await self.repository.list_available(
            database,
            company_id=session.context.company_id,
            worker_id=session.context.worker_id,
            session_id=session.session_id,
            now=utc_now(),
            limit=limit,
        )
        responses: list[ExecutionOffer] = []
        for offer in offers:
            recovery: dict[str, object] = {}
            if offer.state is ControlledOfferState.ACQUIRED and offer.lease_id:
                if offer.session_id != session.session_id:
                    attached = await self.repository.reattach_acquired_session(
                        database,
                        company_id=session.context.company_id,
                        offer_id=offer.id,
                        worker_id=session.context.worker_id,
                        session_id=session.session_id,
                        now=utc_now(),
                    )
                    if attached is None:
                        continue
                    offer = attached
                lease = await database.get(WorkerLease, offer.lease_id)
                if lease is None or lease.status != "active":
                    continue
                recovery = {
                    "recovery_lease_id": str(lease.id),
                    "recovery_lease_version": lease.version,
                }
            responses.append(
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
                            **recovery,
                            **offer.payload,
                        }
                    ),
                )
            )
        return tuple(responses)

    async def reconcile_acknowledged_code_commands(
        self, database: AsyncSession, *, worker_session: WorkerSession
    ) -> int:
        occurred_at = utc_now()
        created = 0
        node_id = await self.repository.active_node_id(
            database,
            company_id=worker_session.context.company_id,
            worker_id=worker_session.context.worker_id,
            now=occurred_at,
        )
        if node_id is None:
            return 0
        sources = await self.repository.list_acknowledged_code_executions(
            database,
            company_id=worker_session.context.company_id,
            worker_id=worker_session.context.worker_id,
            now=occurred_at,
            limit=1,
        )
        for command, execution in sources:
            boundary = dict(command.execution_boundary)
            offer = await self.repository.create_offer(
                database,
                company_id=command.company_id,
                command_id=command.id,
                execution_id=execution.id,
                correlation_id=execution.correlation_id,
                workspace_id=f"execution-{execution.id}",
                command_type=ControlledCommandType.EXECUTE_CODE,
                payload={
                    "node_id": str(node_id),
                    "company_id": str(command.company_id),
                    "command_id": str(command.id),
                    "execution_id": str(execution.id),
                    "repository_key": command.repository_key,
                    "expected_branch": command.expected_branch,
                    "expected_head": command.expected_head,
                    "instruction": command.owner_instruction,
                    "instruction_digest": command.instruction_digest,
                    "request_digest": command.request_digest,
                    "boundary": boundary,
                    "boundary_digest": command.execution_boundary_digest,
                    "commit_subject": _commit_subject(
                        command.command_type, command.ecid
                    ),
                    "repository_mutation_allowed": True,
                },
                expires_at=command.expires_at,
                lease_seconds=900,
                now=occurred_at,
            )
            self._stage(
                database,
                offer=offer,
                event_type=EventType.ENGINEERING_CONTROLLED_OFFER_CREATED,
                now=occurred_at,
            )
            created += 1
        return created

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
        mutation = output.get("repository_mutated")
        if mutation not in {True, False}:
            raise ControlledExecutionPayloadError(
                "Controlled result must declare repository mutation truth."
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
            if mutation is True:
                expected |= {"starting_head", "commit_sha", "validation", "evidence"}
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
            or offer.lease_id != lease_id
        ):
            raise ControlledExecutionIneligibleError(
                "Execution result binding is invalid."
            )
        if offer.session_id != session_id:
            # A signed pending result may be redelivered after reconnect by the
            # same enrolled worker and original lease. Rebind only the session;
            # command, offer, lease, execution, and result identity are unchanged.
            offer.session_id = session_id
            offer.updated_at = completed_at
            offer.version += 1
        validation_output = output.get("validation")
        if outcome is ControlledOutcome.SUCCEEDED and (
            output.get("workspace_id") != offer.workspace_id
            or output.get("repository_key") != offer.payload.get("repository_key")
            or output.get("branch") != offer.payload.get("expected_branch")
            or (
                mutation is False
                and output.get("head") != offer.payload.get("expected_head")
            )
            or (
                mutation is True
                and (
                    offer.command_type != "execute_code"
                    or output.get("starting_head") != offer.payload.get("expected_head")
                    or output.get("head") != output.get("commit_sha")
                    or not re.fullmatch(r"[0-9a-f]{40}", str(output.get("commit_sha")))
                    or not isinstance(validation_output, dict)
                    or not all(value is True for value in validation_output.values())
                )
            )
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
            repository_mutated=bool(mutation),
        )
        if mutation is True:
            evidence = output.get("evidence")
            phases = evidence.get("phases", []) if isinstance(evidence, dict) else []
            expected_phases = [
                "composed",
                "workspace_ready",
                "executing",
                "validating",
                "commit_ready",
                "publishing_result",
                "completed",
            ]
            if phases != expected_phases:
                raise ControlledExecutionPayloadError(
                    "Provider lifecycle evidence is incomplete."
                )
            for sequence, phase in enumerate(phases, start=1):
                database.add(
                    ProviderExecutionTransition(
                        company_id=offer.company_id,
                        node_id=UUID(str(offer.payload["node_id"])),
                        command_id=offer.command_id,
                        execution_id=offer.execution_id,
                        lease_id=lease_id,
                        sequence=sequence,
                        phase=phase,
                        evidence=(
                            {
                                "commit_sha": output.get("commit_sha"),
                                "files": output.get("file_boundary"),
                            }
                            if phase == "completed"
                            else {}
                        ),
                        occurred_at=completed_at,
                    )
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


def _commit_subject(command_type: str, ecid: str) -> str:
    scope = "engineering" if command_type == "mission_control_milestone" else "devx"
    return f"feat({scope}): complete {ecid.lower()} controlled execution"
