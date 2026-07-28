import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_control.records import EngineeringApprovalState
from app.engineering_control.repository import (
    EngineeringCommandRepository,
    engineering_command_repository,
)
from app.engineering_execution.contracts import EngineeringExecutionState
from app.engineering_execution.repository import EngineeringExecutionRepository
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.execution_providers.contracts import (
    ProviderCapability,
    ProviderExecutionRequest,
    ProviderExecutionResult,
    ProviderExecutionStatus,
)
from app.execution_providers.errors import (
    ExecutionProviderError,
    ProviderCapabilityError,
    ProviderNotFoundError,
    ProviderRequestError,
    ProviderUnavailableError,
)
from app.execution_providers.registry import (
    ExecutionProviderRegistry,
    execution_provider_registry,
)
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.permissions.authorization import (
    AuthorizationContext,
    AuthorizationService,
    PermissionDeniedError,
    authorization_service,
)
from app.platform.permissions.codes import WorkerControlPermission
from app.worker_control.contracts import (
    AuthenticatedWorkerContext,
    ExecutionOffer,
    WorkerCapability,
    WorkerExecutionResult,
    WorkerFailureClassification,
    WorkerHealth,
    WorkerLeaseStatus,
    WorkerLifecycleState,
    WorkerResultStatus,
    immutable_mapping,
)
from app.worker_control.errors import (
    WorkerAuthenticationError,
    WorkerConflictError,
    WorkerControlPermissionError,
    WorkerLeaseError,
    WorkerLifecycleError,
    WorkerNotFoundError,
    WorkerValidationError,
)
from app.worker_control.records import (
    RegisterWorker,
    WorkerHeartbeatRecord,
    WorkerIdentity,
    WorkerLeaseRecord,
    WorkerResultRecord,
)
from app.worker_control.repository import WorkerControlRepository

SAFE_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")
MIN_LEASE_SECONDS = 30
MAX_LEASE_SECONDS = 900
MAX_OFFER_SECONDS = 300


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class RegisterWorkerCommand:
    provider_identifier: str
    name: str
    worker_version: str
    capabilities: tuple[WorkerCapability, ...]


class WorkerControlService:
    def __init__(
        self,
        *,
        repository: type[WorkerControlRepository] = WorkerControlRepository,
        execution_repository: type[
            EngineeringExecutionRepository
        ] = EngineeringExecutionRepository,
        command_repository: EngineeringCommandRepository = engineering_command_repository,
        providers: ExecutionProviderRegistry = execution_provider_registry,
        authorization: AuthorizationService = authorization_service,
        audit: AuditService = audit_service,
        business_events: type[BusinessEventService] = BusinessEventService,
    ) -> None:
        self.repository = repository
        self.execution_repository = execution_repository
        self.command_repository = command_repository
        self.providers = providers
        self.authorization = authorization
        self.audit = audit
        self.business_events = business_events

    async def register_worker(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: RegisterWorkerCommand,
        now: datetime | None = None,
    ) -> WorkerIdentity:
        self._require_operator(context)
        provider, name, version, capabilities = self._validate_registration(command)
        occurred_at = now or utc_now()
        try:
            async with session.begin():
                record = await self.repository.create_worker(
                    session,
                    worker=RegisterWorker(
                        company_id=context.company.id,
                        provider_identifier=provider,
                        name=name,
                        worker_version=version,
                        capabilities=capabilities,
                        registered_by_user_id=context.user.id,
                        registered_at=occurred_at,
                    ),
                )
                self._stage_audit(
                    session,
                    action="engineering.worker_registered",
                    context=context,
                    resource_id=record.id,
                    details={
                        "provider_identifier": record.provider_identifier,
                        "worker_name": record.name,
                        "capabilities": [
                            capability.value for capability in record.capabilities
                        ],
                        "lifecycle_state": record.lifecycle_state.value,
                    },
                    occurred_at=occurred_at,
                )
            return record
        except IntegrityError as error:
            await session.rollback()
            raise WorkerConflictError(
                "Worker identity already exists for this Company."
            ) from error

    async def record_heartbeat(
        self,
        session: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        health: WorkerHealth,
        now: datetime | None = None,
    ) -> tuple[WorkerIdentity, WorkerHeartbeatRecord]:
        occurred_at = now or utc_now()
        async with session.begin():
            return await self.record_heartbeat_in_transaction(
                session,
                worker_context=worker_context,
                health=health,
                now=occurred_at,
            )

    async def record_heartbeat_in_transaction(
        self,
        session: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        health: WorkerHealth,
        now: datetime,
    ) -> tuple[WorkerIdentity, WorkerHeartbeatRecord]:
        worker = await self._authenticated_worker(
            session, worker_context=worker_context
        )
        if worker.lifecycle_state == WorkerLifecycleState.DISABLED.value:
            raise WorkerLifecycleError("Disabled worker cannot send heartbeats.")
        return await self.repository.record_heartbeat(
            session, worker=worker, health=health, occurred_at=now
        )

    async def validate_worker(
        self,
        session: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
    ) -> WorkerIdentity:
        async with session.begin():
            return await self.validate_worker_in_transaction(
                session, worker_context=worker_context
            )

    async def validate_worker_in_transaction(
        self,
        session: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
    ) -> WorkerIdentity:
        worker = await self._authenticated_worker(
            session, worker_context=worker_context
        )
        return self.repository.snapshot_worker(worker)

    async def set_worker_lifecycle(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        worker_id: UUID,
        lifecycle_state: WorkerLifecycleState,
        now: datetime | None = None,
    ) -> WorkerIdentity:
        self._require_operator(context)
        if lifecycle_state not in {
            WorkerLifecycleState.AVAILABLE,
            WorkerLifecycleState.OFFLINE,
            WorkerLifecycleState.DISABLED,
        }:
            raise WorkerLifecycleError("Requested worker lifecycle is not assignable.")
        occurred_at = now or utc_now()
        async with session.begin():
            worker = await self.repository.get_worker_for_update(
                session, company_id=context.company.id, worker_id=worker_id
            )
            if worker is None:
                raise WorkerNotFoundError("Worker was not found.")
            if worker.lifecycle_state == WorkerLifecycleState.LEASED.value:
                raise WorkerLifecycleError(
                    "Leased worker cannot be administratively transitioned."
                )
            record = await self.repository.set_worker_state(
                session,
                worker=worker,
                lifecycle_state=lifecycle_state,
                occurred_at=occurred_at,
            )
            self._stage_audit(
                session,
                action="engineering.worker_lifecycle_changed",
                context=context,
                resource_id=record.id,
                details={
                    "lifecycle_state": record.lifecycle_state.value,
                    "provider_identifier": record.provider_identifier,
                },
                occurred_at=occurred_at,
            )
            return record

    async def issue_offer(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        execution_id: UUID,
        capability_required: WorkerCapability,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> ExecutionOffer:
        self._require_operator(context)
        self._validate_lease_seconds(lease_seconds)
        occurred_at = now or utc_now()
        async with session.begin():
            execution = await self.execution_repository.get(
                session,
                company_id=context.company.id,
                execution_id=execution_id,
            )
        if execution is None:
            raise WorkerNotFoundError("Engineering Execution was not found.")
        if execution.state is not EngineeringExecutionState.EXECUTION_NOT_CONNECTED:
            raise WorkerLifecycleError("Engineering Execution is not disconnected.")
        return ExecutionOffer(
            offer_id=uuid4(),
            execution_id=execution.id,
            correlation_id=execution.correlation_id,
            capability_required=capability_required,
            lease_duration=timedelta(seconds=lease_seconds),
            expires_at=occurred_at
            + timedelta(seconds=min(lease_seconds, MAX_OFFER_SECONDS)),
            metadata=immutable_mapping(
                {
                    "execution_state": execution.state.value,
                    "work_dispatched": False,
                }
            ),
        )

    async def acquire_lease(
        self,
        session: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        offer: ExecutionOffer,
        now: datetime | None = None,
    ) -> WorkerLeaseRecord:
        occurred_at = now or utc_now()
        if offer.expires_at <= occurred_at:
            raise WorkerLeaseError("Execution offer has expired.")
        self._validate_lease_seconds(int(offer.lease_duration.total_seconds()))
        try:
            async with session.begin():
                return await self.acquire_lease_in_transaction(
                    session,
                    worker_context=worker_context,
                    offer=offer,
                    now=occurred_at,
                )
        except IntegrityError as error:
            await session.rollback()
            raise WorkerConflictError(
                "Worker or Engineering Execution already has an active lease."
            ) from error

    async def acquire_lease_in_transaction(
        self,
        session: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        offer: ExecutionOffer,
        now: datetime,
    ) -> WorkerLeaseRecord:
        if offer.expires_at <= now:
            raise WorkerLeaseError("Execution offer has expired.")
        worker = await self._authenticated_worker(
            session, worker_context=worker_context
        )
        if worker.lifecycle_state != WorkerLifecycleState.AVAILABLE.value:
            raise WorkerLifecycleError("Worker is not available.")
        capabilities = {WorkerCapability(value) for value in worker.capabilities}
        if offer.capability_required not in capabilities:
            raise WorkerLifecycleError("Worker does not claim the required capability.")
        execution = await self.execution_repository.get(
            session,
            company_id=worker.company_id,
            execution_id=offer.execution_id,
        )
        if execution is None:
            raise WorkerNotFoundError("Engineering Execution was not found.")
        if execution.correlation_id != offer.correlation_id:
            raise WorkerLeaseError("Execution offer identity is invalid.")
        if execution.state is not EngineeringExecutionState.EXECUTION_NOT_CONNECTED:
            raise WorkerLifecycleError("Engineering Execution is not disconnected.")
        lease = await self.repository.create_lease(
            session,
            worker=worker,
            execution_id=execution.id,
            capability=offer.capability_required,
            started_at=now,
            expires_at=now + offer.lease_duration,
        )
        self._stage_worker_audit(
            session,
            action="engineering.worker_lease_acquired",
            worker_context=worker_context,
            resource_id=lease.id,
            correlation_id=execution.correlation_id,
            details=self._lease_details(lease),
            occurred_at=now,
        )
        return lease

    async def renew_lease(
        self,
        session: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        lease_id: UUID,
        expected_version: int,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> WorkerLeaseRecord:
        self._validate_lease_seconds(lease_seconds)
        occurred_at = now or utc_now()
        async with session.begin():
            return await self.renew_lease_in_transaction(
                session,
                worker_context=worker_context,
                lease_id=lease_id,
                expected_version=expected_version,
                lease_seconds=lease_seconds,
                now=occurred_at,
            )

    async def renew_lease_in_transaction(
        self,
        session: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        lease_id: UUID,
        expected_version: int,
        lease_seconds: int,
        now: datetime,
    ) -> WorkerLeaseRecord:
        self._validate_lease_seconds(lease_seconds)
        await self._authenticated_worker(session, worker_context=worker_context)
        lease = await self._owned_lease(
            session,
            worker_context=worker_context,
            lease_id=lease_id,
            expected_version=expected_version,
            now=now,
        )
        return await self.repository.renew_lease(
            session,
            lease=lease,
            expires_at=now + timedelta(seconds=lease_seconds),
            occurred_at=now,
        )

    async def release_lease(
        self,
        session: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        lease_id: UUID,
        expected_version: int,
        now: datetime | None = None,
    ) -> WorkerLeaseRecord:
        occurred_at = now or utc_now()
        async with session.begin():
            worker = await self._authenticated_worker(
                session, worker_context=worker_context
            )
            lease = await self._owned_lease(
                session,
                worker_context=worker_context,
                lease_id=lease_id,
                expected_version=expected_version,
                now=occurred_at,
                permit_expired=True,
            )
            status = (
                WorkerLeaseStatus.EXPIRED
                if lease.expires_at <= occurred_at
                else WorkerLeaseStatus.RELEASED
            )
            record = await self.repository.finish_lease(
                session,
                lease=lease,
                worker=worker,
                status=status,
                occurred_at=occurred_at,
            )
            self._stage_worker_audit(
                session,
                action=f"engineering.worker_lease_{status.value}",
                worker_context=worker_context,
                resource_id=record.id,
                correlation_id=uuid4(),
                details=self._lease_details(record),
                occurred_at=occurred_at,
            )
            return record

    async def release_lease_in_transaction(
        self,
        session: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        lease_id: UUID,
        now: datetime,
    ) -> WorkerLeaseRecord:
        worker = await self._authenticated_worker(
            session, worker_context=worker_context
        )
        lease = await self.repository.get_lease_for_update(
            session,
            company_id=worker_context.company_id,
            lease_id=lease_id,
        )
        if (
            lease is None
            or lease.worker_id != worker_context.worker_id
            or lease.status != WorkerLeaseStatus.ACTIVE.value
        ):
            raise WorkerLeaseError("Worker lease is not active.")
        status = (
            WorkerLeaseStatus.EXPIRED
            if lease.expires_at <= now
            else WorkerLeaseStatus.RELEASED
        )
        return await self.repository.finish_lease(
            session,
            lease=lease,
            worker=worker,
            status=status,
            occurred_at=now,
        )

    async def expire_lease(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        lease_id: UUID,
        expected_version: int,
        now: datetime | None = None,
    ) -> WorkerLeaseRecord:
        self._require_operator(context)
        occurred_at = now or utc_now()
        async with session.begin():
            lease = await self.repository.get_lease_for_update(
                session, company_id=context.company.id, lease_id=lease_id
            )
            if lease is None:
                raise WorkerNotFoundError("Worker lease was not found.")
            if lease.version != expected_version:
                raise WorkerLeaseError("Worker lease version is stale.")
            if lease.status != WorkerLeaseStatus.ACTIVE.value:
                raise WorkerLifecycleError("Worker lease is not active.")
            if lease.expires_at > occurred_at:
                raise WorkerLeaseError("Worker lease has not expired.")
            worker = await self.repository.get_worker_for_update(
                session,
                company_id=context.company.id,
                worker_id=lease.worker_id,
            )
            if worker is None:
                raise WorkerNotFoundError("Worker was not found.")
            record = await self.repository.finish_lease(
                session,
                lease=lease,
                worker=worker,
                status=WorkerLeaseStatus.EXPIRED,
                occurred_at=occurred_at,
            )
            self._stage_audit(
                session,
                action="engineering.worker_lease_expired",
                context=context,
                resource_id=record.id,
                details=self._lease_details(record),
                occurred_at=occurred_at,
            )
            return record

    async def accept_result(
        self,
        session: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        lease_id: UUID,
        expected_lease_version: int,
        result: WorkerExecutionResult,
        correlation_id: UUID,
        now: datetime | None = None,
    ) -> WorkerResultRecord:
        occurred_at = now or utc_now()
        async with session.begin():
            return await self.accept_result_in_transaction(
                session,
                worker_context=worker_context,
                lease_id=lease_id,
                expected_version=expected_lease_version,
                result=result,
                correlation_id=correlation_id,
                now=occurred_at,
            )

    async def accept_result_in_transaction(
        self,
        session: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        lease_id: UUID,
        expected_version: int,
        result: WorkerExecutionResult,
        correlation_id: UUID,
        now: datetime,
    ) -> WorkerResultRecord:
        self._validate_disconnected_result(result)
        worker = await self._authenticated_worker(
            session, worker_context=worker_context
        )
        lease = await self._owned_lease(
            session,
            worker_context=worker_context,
            lease_id=lease_id,
            expected_version=expected_version,
            now=now,
        )
        if result.worker_id != worker.id or result.execution_id != lease.execution_id:
            raise WorkerLeaseError("Worker result identity does not match lease.")
        record = await self.repository.create_result(
            session,
            lease=lease,
            status=result.status,
            validation_summary=dict(result.validation_summary),
            evidence_summary=dict(result.evidence_summary),
            output_references=result.output_references,
            failure_classification=result.failure_classification,
            correlation_id=correlation_id,
            occurred_at=now,
        )
        await self.repository.finish_lease(
            session,
            lease=lease,
            worker=worker,
            status=WorkerLeaseStatus.RELEASED,
            occurred_at=now,
        )
        self._stage_worker_audit(
            session,
            action="engineering.worker_result_recorded",
            worker_context=worker_context,
            resource_id=record.id,
            correlation_id=correlation_id,
            details={
                "execution_id": str(record.execution_id),
                "lease_id": str(record.lease_id),
                "status": record.status.value,
                "failure_classification": record.failure_classification.value,
                "repository_mutated": False,
            },
            occurred_at=now,
        )
        return record

    async def execute_with_provider(
        self,
        session: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        lease_id: UUID,
        expected_lease_version: int,
        now: datetime | None = None,
    ) -> ProviderExecutionResult:
        """Invoke the worker's provider after authoritative worker/lease checks.

        The lease ID is the stable provider request identifier. Provider clients
        must use it as their idempotency key. No Engineering Command can call
        this boundary directly.
        """

        occurred_at = now or utc_now()
        deferred_error: ExecutionProviderError | None = None
        request: ProviderExecutionRequest | None = None
        provider = None
        async with session.begin():
            worker = await self._authenticated_worker(
                session, worker_context=worker_context
            )
            lease = await self._owned_lease(
                session,
                worker_context=worker_context,
                lease_id=lease_id,
                expected_version=expected_lease_version,
                now=occurred_at,
            )
            execution = await self.execution_repository.get(
                session,
                company_id=worker.company_id,
                execution_id=lease.execution_id,
            )
            if execution is None:
                raise WorkerNotFoundError("Engineering Execution was not found.")
            command = await self.command_repository.get_command(
                session,
                company_id=worker.company_id,
                command_id=execution.command_id,
            )
            if (
                command is None
                or command.approval_state is not EngineeringApprovalState.APPROVED
                or command.instruction_digest != execution.instruction_digest
            ):
                raise WorkerLifecycleError(
                    "Engineering Command is not eligible for provider execution."
                )
            try:
                provider = self.providers.resolve(worker.provider_identifier)
            except ProviderNotFoundError:
                deferred_error = ProviderUnavailableError(
                    "Execution provider is unavailable."
                )
                self._stage_provider_observation(
                    session,
                    event_type=EventType.EXECUTION_PROVIDER_UNAVAILABLE,
                    action="engineering.execution_provider_unavailable",
                    worker_context=worker_context,
                    execution_id=execution.id,
                    lease_id=lease.id,
                    correlation_id=execution.correlation_id,
                    occurred_at=occurred_at,
                    outcome="failure",
                )
            if provider is not None:
                required = ProviderCapability(lease.capability_required)
                if not provider.capabilities.supports(required):
                    deferred_error = ProviderCapabilityError(
                        "Execution provider lacks the leased capability."
                    )
                    self._stage_provider_observation(
                        session,
                        event_type=(EventType.EXECUTION_PROVIDER_CAPABILITY_MISMATCH),
                        action="engineering.execution_provider_capability_mismatch",
                        worker_context=worker_context,
                        execution_id=execution.id,
                        lease_id=lease.id,
                        correlation_id=execution.correlation_id,
                        occurred_at=occurred_at,
                        outcome="failure",
                    )
                else:
                    try:
                        health = await provider.health()
                    except ExecutionProviderError:
                        health = None
                    if health is None or not health.available:
                        deferred_error = ProviderUnavailableError(
                            "Execution provider is unavailable."
                        )
                        self._stage_provider_observation(
                            session,
                            event_type=EventType.EXECUTION_PROVIDER_UNAVAILABLE,
                            action="engineering.execution_provider_unavailable",
                            worker_context=worker_context,
                            execution_id=execution.id,
                            lease_id=lease.id,
                            correlation_id=execution.correlation_id,
                            occurred_at=occurred_at,
                            outcome="failure",
                        )
                    else:
                        request = ProviderExecutionRequest(
                            provider_request_id=lease.id,
                            execution_id=execution.id,
                            lease_id=lease.id,
                            company_id=worker.company_id,
                            worker_id=worker.id,
                            provider_identifier=worker.provider_identifier,
                            repository_key=command.repository_key,
                            expected_branch=command.expected_branch,
                            expected_head=command.expected_head,
                            authorized_code_changes=command.requested_code_changes,
                            instruction=command.owner_instruction,
                            instruction_digest=command.instruction_digest,
                            request_digest=command.request_digest,
                            correlation_id=execution.correlation_id,
                        )
                        self._stage_provider_observation(
                            session,
                            event_type=EventType.EXECUTION_PROVIDER_SELECTED,
                            action="engineering.execution_provider_selected",
                            worker_context=worker_context,
                            execution_id=execution.id,
                            lease_id=lease.id,
                            correlation_id=execution.correlation_id,
                            occurred_at=occurred_at,
                        )
                        self._stage_provider_observation(
                            session,
                            event_type=EventType.PROVIDER_EXECUTION_STARTED,
                            action="engineering.provider_execution_started",
                            worker_context=worker_context,
                            execution_id=execution.id,
                            lease_id=lease.id,
                            correlation_id=execution.correlation_id,
                            occurred_at=occurred_at,
                        )
        if deferred_error is not None:
            raise deferred_error
        if provider is None or request is None:
            raise ProviderUnavailableError("Execution provider is unavailable.")
        try:
            result = await provider.execute(request)
            self._validate_provider_result(request=request, result=result)
        except ExecutionProviderError as error:
            async with session.begin():
                self._stage_provider_observation(
                    session,
                    event_type=EventType.PROVIDER_EXECUTION_FAILED,
                    action="engineering.provider_execution_failed",
                    worker_context=worker_context,
                    execution_id=request.execution_id,
                    lease_id=request.lease_id,
                    correlation_id=request.correlation_id,
                    occurred_at=utc_now(),
                    outcome="failure",
                    reason_code=error.code,
                )
            raise
        async with session.begin():
            self._stage_provider_observation(
                session,
                event_type=(
                    EventType.PROVIDER_EXECUTION_COMPLETED
                    if result.status is ProviderExecutionStatus.SUCCEEDED
                    else EventType.PROVIDER_EXECUTION_FAILED
                ),
                action=(
                    "engineering.provider_execution_completed"
                    if result.status is ProviderExecutionStatus.SUCCEEDED
                    else "engineering.provider_execution_failed"
                ),
                worker_context=worker_context,
                execution_id=request.execution_id,
                lease_id=request.lease_id,
                correlation_id=request.correlation_id,
                occurred_at=result.finished_at,
                outcome=(
                    "success"
                    if result.status is ProviderExecutionStatus.SUCCEEDED
                    else "failure"
                ),
                reason_code=(
                    None
                    if result.failure_classification is None
                    else result.failure_classification.value
                ),
            )
        return result

    @staticmethod
    def _validate_provider_result(
        *,
        request: ProviderExecutionRequest,
        result: ProviderExecutionResult,
    ) -> None:
        if (
            result.provider_request_id != request.provider_request_id
            or result.execution_id != request.execution_id
            or result.provider_identifier != request.provider_identifier
            or result.finished_at < result.started_at
        ):
            raise ProviderRequestError("Provider result identity is invalid.")

    async def _authenticated_worker(
        self,
        session: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
    ):
        if (
            not worker_context.provider_identifier.strip()
            or not worker_context.authentication_subject.strip()
        ):
            raise WorkerAuthenticationError("Worker authentication is invalid.")
        worker = await self.repository.get_worker_for_update(
            session,
            company_id=worker_context.company_id,
            worker_id=worker_context.worker_id,
        )
        if worker is None:
            raise WorkerNotFoundError("Worker was not found.")
        if worker.provider_identifier != worker_context.provider_identifier:
            raise WorkerAuthenticationError("Worker authentication is invalid.")
        return worker

    async def _owned_lease(
        self,
        session: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        lease_id: UUID,
        expected_version: int,
        now: datetime,
        permit_expired: bool = False,
    ):
        lease = await self.repository.get_lease_for_update(
            session, company_id=worker_context.company_id, lease_id=lease_id
        )
        if lease is None or lease.worker_id != worker_context.worker_id:
            raise WorkerNotFoundError("Worker lease was not found.")
        if lease.version != expected_version:
            raise WorkerLeaseError("Worker lease version is stale.")
        if lease.status != WorkerLeaseStatus.ACTIVE.value:
            raise WorkerLifecycleError("Worker lease is not active.")
        if not permit_expired and lease.expires_at <= now:
            raise WorkerLeaseError("Worker lease has expired.")
        return lease

    def _require_operator(self, context: AuthorizationContext) -> None:
        if context.membership.status != "active":
            raise WorkerControlPermissionError("Permission denied.")
        try:
            self.authorization.require_permission(
                context, WorkerControlPermission.MANAGE
            )
        except PermissionDeniedError as error:
            raise WorkerControlPermissionError("Permission denied.") from error

    @staticmethod
    def _validate_registration(
        command: RegisterWorkerCommand,
    ) -> tuple[str, str, str, tuple[WorkerCapability, ...]]:
        provider = command.provider_identifier.strip().lower()
        name = command.name.strip()
        version = command.worker_version.strip()
        if not SAFE_IDENTIFIER.fullmatch(provider):
            raise WorkerValidationError("Provider identifier is invalid.")
        if not name or len(name) > 100 or not version or len(version) > 50:
            raise WorkerValidationError("Worker name or version is invalid.")
        capabilities = tuple(
            sorted(set(command.capabilities), key=lambda item: item.value)
        )
        if not capabilities:
            raise WorkerValidationError("At least one capability is required.")
        return provider, name, version, capabilities

    @staticmethod
    def _validate_lease_seconds(value: int) -> None:
        if value < MIN_LEASE_SECONDS or value > MAX_LEASE_SECONDS:
            raise WorkerValidationError(
                f"Lease duration must be between {MIN_LEASE_SECONDS} and "
                f"{MAX_LEASE_SECONDS} seconds."
            )

    @staticmethod
    def _validate_disconnected_result(result: WorkerExecutionResult) -> None:
        if (
            result.status is not WorkerResultStatus.NOT_EXECUTED
            or result.failure_classification
            is not WorkerFailureClassification.EXECUTION_NOT_CONNECTED
            or result.output_references
            or result.validation_summary
        ):
            raise WorkerValidationError(
                "DF.5B.2 accepts only disconnected, non-executed results."
            )
        if result.evidence_summary.get("repository_mutated") is not False:
            raise WorkerValidationError(
                "Disconnected result must attest repository_mutated=false."
            )

    def _stage_audit(
        self,
        session: AsyncSession,
        *,
        action: str,
        context: AuthorizationContext,
        resource_id: UUID,
        details: dict[str, object],
        occurred_at: datetime,
    ) -> None:
        self.audit.stage(
            session,
            AuditEntry(
                action=action,
                resource_type="engineering_worker",
                actor_user_id=context.user.id,
                company_id=context.company.id,
                resource_id=resource_id,
                correlation_id=uuid4(),
                details=details,
                occurred_at=occurred_at,
            ),
        )

    def _stage_worker_audit(
        self,
        session: AsyncSession,
        *,
        action: str,
        worker_context: AuthenticatedWorkerContext,
        resource_id: UUID,
        correlation_id: UUID,
        details: dict[str, object],
        occurred_at: datetime,
    ) -> None:
        self.audit.stage(
            session,
            AuditEntry(
                action=action,
                resource_type="engineering_worker_control",
                company_id=worker_context.company_id,
                resource_id=resource_id,
                correlation_id=correlation_id,
                details={
                    **details,
                    "worker_id": str(worker_context.worker_id),
                    "provider_identifier": worker_context.provider_identifier,
                },
                occurred_at=occurred_at,
            ),
        )

    def _stage_provider_observation(
        self,
        session: AsyncSession,
        *,
        event_type: EventType,
        action: str,
        worker_context: AuthenticatedWorkerContext,
        execution_id: UUID,
        lease_id: UUID,
        correlation_id: UUID,
        occurred_at: datetime,
        outcome: str = "success",
        reason_code: str | None = None,
    ) -> None:
        safe: dict[str, object] = {
            "execution_id": str(execution_id),
            "lease_id": str(lease_id),
            "worker_id": str(worker_context.worker_id),
            "provider_identifier": worker_context.provider_identifier,
        }
        self.audit.stage(
            session,
            AuditEntry(
                action=action,
                outcome=outcome,
                resource_type="engineering_execution_provider",
                company_id=worker_context.company_id,
                resource_id=execution_id,
                reason_code=reason_code,
                correlation_id=correlation_id,
                details=safe,
                occurred_at=occurred_at,
            ),
        )
        self.business_events.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="engineering_execution",
                entity_id=execution_id,
                company_id=worker_context.company_id,
                payload=safe,
                correlation_id=correlation_id,
                occurred_at=occurred_at,
            ),
        )

    @staticmethod
    def _lease_details(lease: WorkerLeaseRecord) -> dict[str, object]:
        return {
            "lease_id": str(lease.id),
            "execution_id": str(lease.execution_id),
            "capability": lease.capability_required.value,
            "status": lease.status.value,
            "repository_mutated": False,
        }


worker_control_service = WorkerControlService()
