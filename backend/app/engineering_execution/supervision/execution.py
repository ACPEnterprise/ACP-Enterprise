import asyncio
import hashlib
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_execution.composition.contracts import (
    ProviderAttemptState,
    ProviderResultStatus,
)
from app.engineering_execution.composition.records import (
    NormalizedProviderResultRecord,
)
from app.engineering_execution.composition.repository import (
    ExecutionCompositionRepository,
)
from app.engineering_execution.composition.service import (
    ExecutionCompositionService,
    RecordProviderResult,
)
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.execution_providers.contracts import (
    ProviderCapabilities,
    ProviderCapability,
    ProviderExecutionRequest,
    ProviderExecutionResult,
    ProviderExecutionStatus,
)
from app.execution_providers.errors import (
    ProviderAuthenticationError,
    ProviderRequestError,
    ProviderUnavailableError,
)
from app.execution_providers.runtime import (
    ProviderCredentialStatus,
    ProviderRuntime,
    ProviderRuntimeRequest,
    ProviderRuntimeState,
)
from app.worker_control.contracts import AuthenticatedWorkerContext

from .contracts import ProviderSessionState
from .errors import (
    SupervisionConflictError,
    SupervisionIneligibleError,
    SupervisionNotFoundError,
)
from .records import ProviderSessionRecord
from .repository import SupervisedExecutionSource, SupervisionRepository
from .service import utc_now


@dataclass(frozen=True)
class ExecuteApprovedComposition:
    provider_session_id: UUID
    execution_offer_id: UUID
    max_output_tokens: int = 256
    timeout_seconds: int = 30


@dataclass(frozen=True)
class SupervisedExecutionOutcome:
    provider_session: ProviderSessionRecord
    provider_result: ProviderExecutionResult
    durable_result: NormalizedProviderResultRecord


class SupervisedExecutionService:
    def __init__(
        self,
        *,
        runtime: ProviderRuntime,
        repository: type[SupervisionRepository] = SupervisionRepository,
        compositions: ExecutionCompositionService | None = None,
        events: type[BusinessEventService] = BusinessEventService,
    ) -> None:
        self.runtime = runtime
        self.repository = repository
        self.compositions = compositions or ExecutionCompositionService()
        self.events = events

    async def execute(
        self,
        session: AsyncSession,
        *,
        context: AuthenticatedWorkerContext,
        command: ExecuteApprovedComposition,
        now: datetime | None = None,
    ) -> SupervisedExecutionOutcome:
        occurred_at = now or utc_now()
        if not 1 <= command.max_output_tokens <= 512:
            raise SupervisionIneligibleError("Output limit is invalid.")
        if not 1 <= command.timeout_seconds <= 120:
            raise SupervisionIneligibleError("Execution timeout is invalid.")
        source = await self._authorize(
            session, context=context, command=command, now=occurred_at
        )
        session_reference = f"supervised-execution-{source.provider_session.id}"
        request = ProviderExecutionRequest(
            provider_request_id=source.attempt.idempotency_key,
            execution_id=source.execution.id,
            lease_id=source.lease.id,
            company_id=context.company_id,
            worker_id=context.worker_id,
            provider_identifier=context.provider_identifier,
            repository_key="",
            expected_branch="",
            expected_head="",
            authorized_code_changes=False,
            instruction=source.command.owner_instruction,
            instruction_digest=source.composition.instruction_digest,
            request_digest=source.composition.request_digest,
            correlation_id=source.execution.correlation_id,
            provider_session_reference=session_reference,
            max_output_tokens=command.max_output_tokens,
            timeout_seconds=command.timeout_seconds,
        )
        runtime_request = ProviderRuntimeRequest(
            provider_session_id=source.provider_session.id,
            company_id=context.company_id,
            worker_id=context.worker_id,
            provider_identifier=context.provider_identifier,
            capabilities=ProviderCapabilities(
                tuple(
                    ProviderCapability(value)
                    for value in source.provider_session.effective_capabilities
                )
            ),
            expires_at=source.provider_session.expires_at,
            provider_session_reference=session_reference,
        )
        try:
            provider_result = await asyncio.wait_for(
                self.runtime.execute(runtime_request, request),
                timeout=float(command.timeout_seconds + 1),
            )
        except asyncio.TimeoutError:
            await self._record_failure(
                session,
                context=context,
                source=source,
                status=ProviderResultStatus.FAILED,
                failure_classification="timed_out",
                now=utc_now(),
            )
            raise
        except asyncio.CancelledError:
            await self._record_failure(
                session,
                context=context,
                source=source,
                status=ProviderResultStatus.CANCELLED,
                failure_classification="cancelled",
                now=utc_now(),
            )
            raise
        except (
            ProviderAuthenticationError,
            ProviderRequestError,
            ProviderUnavailableError,
        ) as error:
            await self._record_failure(
                session,
                context=context,
                source=source,
                status=ProviderResultStatus.FAILED,
                failure_classification=type(error).__name__,
                now=utc_now(),
            )
            raise
        if provider_result.status is not ProviderExecutionStatus.SUCCEEDED:
            await self._record_failure(
                session,
                context=context,
                source=source,
                status=ProviderResultStatus.FAILED,
                failure_classification=(
                    provider_result.failure_classification.value
                    if provider_result.failure_classification
                    else "provider_failed"
                ),
                now=provider_result.finished_at,
            )
            raise SupervisionIneligibleError("Provider execution failed.")
        async with session.begin():
            ready = await SupervisionRepository.update_runtime(
                session,
                company_id=context.company_id,
                session_id=source.provider_session.id,
                expected_version=source.provider_session.version,
                from_states=(ProviderSessionState.CREATED,),
                to_state=ProviderSessionState.READY,
                runtime_state=ProviderRuntimeState.PROVIDER_READY,
                credential_status=ProviderCredentialStatus.USABLE,
                provider_ready=True,
                provider_session_reference=session_reference,
                now=provider_result.finished_at,
            )
            if ready is None:
                raise SupervisionConflictError("Provider session changed.")
            durable = await self.compositions.record_result_in_transaction(
                session,
                worker_context=context,
                lease_id=source.lease.id,
                composition_digest=source.composition.composition_digest,
                instruction_digest=source.composition.instruction_digest,
                request_digest=source.composition.request_digest,
                command=RecordProviderResult(
                    attempt_id=source.attempt.id,
                    status=ProviderResultStatus.SUCCEEDED,
                    evidence_summary=dict(provider_result.evidence_summary),
                    validation_summary=dict(provider_result.validation_summary),
                    output_references=provider_result.output_references,
                    repository_mutated=False,
                ),
                now=provider_result.finished_at,
            )
            self._event(
                session,
                context=context,
                event_type=EventType.ENGINEERING_PROVIDER_EXECUTION_COMPLETED,
                entity_id=source.attempt.id,
                payload={"status": "succeeded", "repository_mutated": False},
                now=provider_result.finished_at,
            )
        return SupervisedExecutionOutcome(ready, provider_result, durable)

    async def _authorize(
        self,
        session: AsyncSession,
        *,
        context: AuthenticatedWorkerContext,
        command: ExecuteApprovedComposition,
        now: datetime,
    ) -> SupervisedExecutionSource:
        async with session.begin():
            source = await self.repository.load_execution_source_for_update(
                session,
                company_id=context.company_id,
                worker_id=context.worker_id,
                provider_session_id=command.provider_session_id,
            )
            if source is None:
                raise SupervisionNotFoundError("Execution binding was not found.")
            digest = hashlib.sha256(
                source.command.owner_instruction.encode()
            ).hexdigest()
            if (
                source.provider_session.provider_identifier
                != context.provider_identifier
                or source.worker.provider_identifier != context.provider_identifier
                or source.lease.status != "active"
                or source.lease.expires_at <= now
                or source.composition.expires_at <= now
                or source.command.approval_state != "approved"
                or source.command.expires_at <= now
                or source.command.canceled_at is not None
                or source.composition.instruction_digest != digest
                or source.execution.instruction_digest != digest
                or source.attempt.idempotency_key != command.execution_offer_id
                or source.attempt.state != ProviderAttemptState.PREPARED.value
                or source.existing_result is not None
                or source.composition.approved_code_changes
                or "engineering.execute"
                not in source.provider_session.effective_capabilities
            ):
                raise SupervisionIneligibleError("Execution is not eligible.")
            starting = await ExecutionCompositionRepository.transition_attempt(
                session,
                company_id=context.company_id,
                attempt_id=source.attempt.id,
                expected_version=source.attempt.version,
                from_states=(ProviderAttemptState.PREPARED,),
                to_state=ProviderAttemptState.STARTING,
                occurred_at=now,
            )
            if starting is None:
                raise SupervisionConflictError("Execution attempt changed.")
            running = await ExecutionCompositionRepository.transition_attempt(
                session,
                company_id=context.company_id,
                attempt_id=starting.id,
                expected_version=starting.version,
                from_states=(ProviderAttemptState.STARTING,),
                to_state=ProviderAttemptState.RUNNING,
                occurred_at=now,
            )
            if running is None:
                raise SupervisionConflictError("Execution attempt changed.")
            self._event(
                session,
                context=context,
                event_type=EventType.ENGINEERING_PROVIDER_EXECUTION_STARTED,
                entity_id=running.id,
                payload={"state": "running", "repository_mutated": False},
                now=now,
            )
        return source

    async def _record_failure(
        self,
        session: AsyncSession,
        *,
        context: AuthenticatedWorkerContext,
        source: SupervisedExecutionSource,
        status: ProviderResultStatus,
        failure_classification: str,
        now: datetime,
    ) -> None:
        async with session.begin():
            await SupervisionRepository.update_runtime(
                session,
                company_id=context.company_id,
                session_id=source.provider_session.id,
                expected_version=source.provider_session.version,
                from_states=(ProviderSessionState.CREATED,),
                to_state=(
                    ProviderSessionState.CANCELLED
                    if status is ProviderResultStatus.CANCELLED
                    else ProviderSessionState.FAILED
                ),
                runtime_state=(
                    ProviderRuntimeState.CANCELLED
                    if status is ProviderResultStatus.CANCELLED
                    else ProviderRuntimeState.TIMEOUT
                    if failure_classification == "timed_out"
                    else ProviderRuntimeState.PROVIDER_FAILURE
                ),
                credential_status=ProviderCredentialStatus.USABLE,
                provider_ready=False,
                provider_session_reference=None,
                now=now,
                failure_classification=failure_classification[:100],
            )
            await self.compositions.record_result_in_transaction(
                session,
                worker_context=context,
                lease_id=source.lease.id,
                composition_digest=source.composition.composition_digest,
                instruction_digest=source.composition.instruction_digest,
                request_digest=source.composition.request_digest,
                command=RecordProviderResult(
                    attempt_id=source.attempt.id,
                    status=status,
                    evidence_summary={},
                    validation_summary={},
                    output_references=(),
                    failure_classification=failure_classification[:100],
                    repository_mutated=False,
                ),
                now=now,
            )
            self._event(
                session,
                context=context,
                event_type=EventType.ENGINEERING_PROVIDER_EXECUTION_FAILED,
                entity_id=source.attempt.id,
                payload={
                    "status": status.value,
                    "failure_classification": failure_classification[:100],
                    "repository_mutated": False,
                },
                now=now,
            )

    def _event(
        self,
        session: AsyncSession,
        *,
        context: AuthenticatedWorkerContext,
        event_type: EventType,
        entity_id: UUID,
        payload: dict[str, object],
        now: datetime,
    ) -> None:
        self.events.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="engineering_provider_execution",
                entity_id=entity_id,
                company_id=context.company_id,
                payload=payload,
                occurred_at=now,
            ),
        )
