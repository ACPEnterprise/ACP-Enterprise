import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_control.workstream_runtime import workstream_runtime_service
from app.engineering_execution.composition.contracts import (
    CompositionIntegrityProvider,
    DigestOnlyCompositionIntegrityProvider,
    ProviderAttemptState,
    ProviderProgressPhase,
    ProviderResultDisposition,
    ProviderResultStatus,
)
from app.engineering_execution.composition.errors import (
    AttemptTransitionError,
    CompositionCapabilityError,
    CompositionConflictError,
    CompositionEvidenceMismatchError,
    CompositionIneligibleError,
    CompositionNotFoundError,
    CompositionPermissionError,
    ProgressValidationError,
    ResultValidationError,
    StaleAttemptVersionError,
)
from app.engineering_execution.composition.records import (
    AppendProviderProgress,
    CompositionBundle,
    CompositionDeliveryPackage,
    CreateExecutionComposition,
    ExecutionCompositionRecord,
    NormalizedProviderResultRecord,
    PrepareProviderAttempt,
    ProviderExecutionAttemptRecord,
    ProviderProgressEventRecord,
    StoreProviderResult,
)
from app.engineering_execution.composition.repository import (
    CompositionSource,
    ExecutionCompositionRepository,
)
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.execution_providers.contracts import ProviderCapability
from app.execution_providers.errors import ProviderNotFoundError
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
from app.platform.permissions.codes import EngineeringExecutionPermission
from app.worker_control.contracts import AuthenticatedWorkerContext

SAFE_CODE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")
MAX_OUTPUT_REFERENCES = 20
MAX_OUTPUT_REFERENCE_LENGTH = 500


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ComposeExecution:
    execution_id: UUID
    lease_id: UUID
    provider_identifier: str
    required_capabilities: tuple[ProviderCapability, ...]
    instruction_digest: str
    request_digest: str
    repository_key: str
    expected_branch: str
    expected_head: str
    approved_code_changes: bool


@dataclass(frozen=True)
class RecordProviderResult:
    attempt_id: UUID
    status: ProviderResultStatus
    evidence_summary: dict[str, object]
    validation_summary: dict[str, object]
    output_references: tuple[str, ...]
    failure_classification: str | None = None
    repository_mutated: bool = False


class ExecutionCompositionService:
    def __init__(
        self,
        *,
        repository: type[
            ExecutionCompositionRepository
        ] = ExecutionCompositionRepository,
        providers: ExecutionProviderRegistry = execution_provider_registry,
        integrity: CompositionIntegrityProvider | None = None,
        authorization: AuthorizationService = authorization_service,
        audit: AuditService = audit_service,
        business_events: type[BusinessEventService] = BusinessEventService,
    ) -> None:
        self.repository = repository
        self.providers = providers
        self.integrity = integrity or DigestOnlyCompositionIntegrityProvider()
        self.authorization = authorization
        self.audit = audit
        self.business_events = business_events

    async def compose(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: ComposeExecution,
        now: datetime | None = None,
    ) -> CompositionBundle:
        self._require(context)
        created_at = now or utc_now()
        provider_identifier = command.provider_identifier.strip().lower()
        if not SAFE_CODE.fullmatch(provider_identifier):
            raise CompositionCapabilityError("Provider identifier is invalid.")
        required = tuple(
            sorted(set(command.required_capabilities), key=lambda item: item.value)
        )
        if not required:
            raise CompositionCapabilityError("A required capability is needed.")
        try:
            provider = self.providers.resolve(provider_identifier)
        except ProviderNotFoundError as error:
            raise CompositionCapabilityError(
                "Provider capability declaration was not found."
            ) from error
        provider_capabilities = set(provider.capabilities.values)

        try:
            async with session.begin():
                source = await self.repository.load_source_for_update(
                    session,
                    company_id=context.company.id,
                    execution_id=command.execution_id,
                    lease_id=command.lease_id,
                )
                if source is None:
                    raise CompositionNotFoundError(
                        "Engineering Execution or lease was not found."
                    )
                self._validate_source(
                    source,
                    command=command,
                    provider_identifier=provider_identifier,
                    provider_capabilities=provider_capabilities,
                    now=created_at,
                )
                existing = await self.repository.get_bundle(
                    session,
                    company_id=context.company.id,
                    execution_id=source.execution_id,
                    lease_id=source.lease_id,
                )
                effective = tuple(
                    sorted(
                        {
                            capability.value
                            for capability in required
                            if capability in provider_capabilities
                            and capability.value in source.worker_capabilities
                        }
                    )
                )
                if len(effective) != len(required):
                    raise CompositionCapabilityError(
                        "Effective capability intersection is insufficient."
                    )
                digest = composition_digest(
                    source=source,
                    provider_identifier=provider_identifier,
                    required=tuple(item.value for item in required),
                    effective=effective,
                    approved_code_changes=command.approved_code_changes,
                )
                if existing is not None:
                    if existing.composition.composition_digest != digest:
                        raise CompositionConflictError(
                            "Existing composition evidence differs."
                        )
                    return existing
                bundle = await self.repository.create_bundle(
                    session,
                    composition=CreateExecutionComposition(
                        company_id=context.company.id,
                        command_id=source.command_id,
                        execution_id=source.execution_id,
                        worker_id=source.worker_id,
                        lease_id=source.lease_id,
                        provider_identifier=provider_identifier,
                        required_capabilities=tuple(item.value for item in required),
                        effective_capabilities=effective,
                        approved_code_changes=command.approved_code_changes,
                        repository_key=source.repository_key,
                        expected_branch=source.expected_branch,
                        expected_head=source.expected_head,
                        instruction_digest=source.command_instruction_digest,
                        request_digest=source.command_request_digest,
                        expires_at=min(
                            source.command_expires_at, source.lease_expires_at
                        ),
                        composition_digest=digest,
                        created_at=created_at,
                    ),
                    integrity=self.integrity.evidence_for(composition_digest=digest),
                )
                self._stage_composition_evidence(
                    session,
                    context=context,
                    bundle=bundle,
                    occurred_at=created_at,
                )
            return bundle
        except IntegrityError as error:
            await session.rollback()
            raise CompositionConflictError(
                "Composition already exists or violates its binding."
            ) from error

    async def prepare_attempt(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        composition_id: UUID,
        idempotency_key: UUID,
        now: datetime | None = None,
    ) -> ProviderExecutionAttemptRecord:
        self._require(context)
        occurred_at = now or utc_now()
        try:
            async with session.begin():
                composition = await self.repository.get_composition(
                    session,
                    company_id=context.company.id,
                    composition_id=composition_id,
                )
                if composition is None:
                    raise CompositionNotFoundError("Composition was not found.")
                if composition.expires_at <= occurred_at:
                    raise CompositionIneligibleError("Composition has expired.")
                record = await self.repository.prepare_attempt(
                    session,
                    attempt=PrepareProviderAttempt(
                        company_id=context.company.id,
                        composition_id=composition.id,
                        worker_id=composition.worker_id,
                        lease_id=composition.lease_id,
                        provider_identifier=composition.provider_identifier,
                        idempotency_key=idempotency_key,
                        prepared_at=occurred_at,
                    ),
                )
                self._stage(
                    session,
                    context=context,
                    event_type=EventType.ENGINEERING_EXECUTION_ATTEMPT_PREPARED,
                    action="engineering_execution.attempt_prepared",
                    resource_id=record.id,
                    correlation_id=record.idempotency_key,
                    details={
                        "attempt_id": str(record.id),
                        "composition_id": str(record.composition_id),
                        "attempt_ordinal": record.attempt_ordinal,
                        "provider_identifier": record.provider_identifier,
                        "state": record.state.value,
                    },
                    occurred_at=occurred_at,
                )
            return record
        except IntegrityError as error:
            await session.rollback()
            raise CompositionConflictError(
                "Attempt conflicts with existing data."
            ) from error

    async def transition_attempt(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        attempt_id: UUID,
        expected_version: int,
        to_state: ProviderAttemptState,
        failure_classification: str | None = None,
        now: datetime | None = None,
    ) -> ProviderExecutionAttemptRecord:
        self._require(context)
        occurred_at = now or utc_now()
        allowed_from = _allowed_from(to_state)
        async with session.begin():
            current = await self.repository.get_attempt_for_update(
                session,
                company_id=context.company.id,
                attempt_id=attempt_id,
            )
            if current is None:
                raise CompositionNotFoundError("Attempt was not found.")
            if current.version != expected_version:
                raise StaleAttemptVersionError("Attempt version is stale.")
            if current.state not in allowed_from:
                raise AttemptTransitionError("Attempt transition is invalid.")
            record = await self.repository.transition_attempt(
                session,
                company_id=context.company.id,
                attempt_id=attempt_id,
                expected_version=expected_version,
                from_states=allowed_from,
                to_state=to_state,
                occurred_at=occurred_at,
                failure_classification=failure_classification,
            )
            if record is None:
                raise StaleAttemptVersionError("Attempt version is stale.")
            self._stage(
                session,
                context=context,
                event_type=EventType.ENGINEERING_EXECUTION_ATTEMPT_STATE_CHANGED,
                action="engineering_execution.attempt_state_changed",
                resource_id=record.id,
                correlation_id=record.idempotency_key,
                details={
                    "attempt_id": str(record.id),
                    "prior_state": current.state.value,
                    "new_state": record.state.value,
                    "version": record.version,
                },
                occurred_at=occurred_at,
            )
        return record

    async def append_progress(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        attempt_id: UUID,
        phase: ProviderProgressPhase,
        message_code: str,
        summary: str | None = None,
        percentage: int | None = None,
        now: datetime | None = None,
    ) -> ProviderProgressEventRecord:
        self._require(context)
        code = message_code.strip().lower()
        normalized_summary = summary.strip() if summary is not None else None
        if not SAFE_CODE.fullmatch(code):
            raise ProgressValidationError("Progress message code is invalid.")
        if normalized_summary is not None and len(normalized_summary) > 500:
            raise ProgressValidationError("Progress summary is too long.")
        if percentage is not None and not 0 <= percentage <= 100:
            raise ProgressValidationError("Progress percentage is invalid.")
        occurred_at = now or utc_now()
        async with session.begin():
            attempt = await self.repository.get_attempt_for_update(
                session,
                company_id=context.company.id,
                attempt_id=attempt_id,
            )
            if attempt is None:
                raise CompositionNotFoundError("Attempt was not found.")
            if attempt.state not in {
                ProviderAttemptState.STARTING,
                ProviderAttemptState.RUNNING,
            }:
                raise AttemptTransitionError("Attempt cannot accept progress.")
            record = await self.repository.append_progress(
                session,
                progress=AppendProviderProgress(
                    company_id=context.company.id,
                    attempt_id=attempt.id,
                    phase=phase,
                    message_code=code,
                    summary=normalized_summary,
                    percentage=percentage,
                    created_at=occurred_at,
                ),
            )
            composition = await self.repository.get_composition(
                session,
                company_id=context.company.id,
                composition_id=attempt.composition_id,
            )
            if composition is None:
                raise CompositionNotFoundError("Composition was not found.")
            await workstream_runtime_service.project_provider_progress(
                session,
                company_id=context.company.id,
                command_id=composition.command_id,
                attempt_id=attempt.id,
                sequence_number=record.sequence_number,
                phase=record.phase.value,
                percentage=record.percentage,
                summary=record.summary,
                message_code=record.message_code,
                occurred_at=occurred_at,
            )
            self._stage(
                session,
                context=context,
                event_type=EventType.ENGINEERING_EXECUTION_PROGRESS_RECORDED,
                action="engineering_execution.progress_recorded",
                resource_id=attempt.id,
                correlation_id=attempt.idempotency_key,
                details={
                    "attempt_id": str(attempt.id),
                    "sequence_number": record.sequence_number,
                    "phase": record.phase.value,
                    "message_code": record.message_code,
                    "percentage": record.percentage,
                },
                occurred_at=occurred_at,
            )
        return record

    async def record_result(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: RecordProviderResult,
        now: datetime | None = None,
    ) -> NormalizedProviderResultRecord:
        self._require(context)
        received_at = now or utc_now()
        self._validate_result(command)
        async with session.begin():
            attempt = await self.repository.get_attempt_for_update(
                session,
                company_id=context.company.id,
                attempt_id=command.attempt_id,
            )
            if attempt is None:
                raise CompositionNotFoundError("Attempt was not found.")
            composition = await self.repository.get_composition(
                session,
                company_id=context.company.id,
                composition_id=attempt.composition_id,
            )
            if composition is None:
                raise CompositionNotFoundError("Composition was not found.")
            source = await self.repository.load_source_for_update(
                session,
                company_id=context.company.id,
                execution_id=composition.execution_id,
                lease_id=composition.lease_id,
            )
            disposition, reason = _result_disposition(
                source=source,
                attempt=attempt,
                composition_expires_at=composition.expires_at,
                now=received_at,
            )
            result = await self.repository.store_result(
                session,
                result=StoreProviderResult(
                    company_id=context.company.id,
                    attempt_id=attempt.id,
                    composition_id=composition.id,
                    status=command.status,
                    evidence_summary=dict(command.evidence_summary),
                    validation_summary=dict(command.validation_summary),
                    output_references=command.output_references,
                    failure_classification=command.failure_classification,
                    received_at=received_at,
                    disposition=disposition,
                    disposition_reason=reason,
                ),
            )
            terminal_state = (
                ProviderAttemptState.QUARANTINED
                if disposition is ProviderResultDisposition.QUARANTINED
                else ProviderAttemptState.COMPLETED
                if command.status is ProviderResultStatus.SUCCEEDED
                and disposition is ProviderResultDisposition.ACCEPTED
                else ProviderAttemptState.CANCELLED
                if command.status is ProviderResultStatus.CANCELLED
                and disposition is ProviderResultDisposition.ACCEPTED
                else ProviderAttemptState.FAILED
                if disposition is ProviderResultDisposition.ACCEPTED
                else None
            )
            if terminal_state is not None:
                transitioned = await self.repository.transition_attempt(
                    session,
                    company_id=context.company.id,
                    attempt_id=attempt.id,
                    expected_version=attempt.version,
                    from_states=(attempt.state,),
                    to_state=terminal_state,
                    occurred_at=received_at,
                    failure_classification=command.failure_classification,
                )
                if transitioned is None:
                    raise StaleAttemptVersionError("Attempt version is stale.")
            self._stage(
                session,
                context=context,
                event_type=(
                    EventType.ENGINEERING_EXECUTION_RESULT_QUARANTINED
                    if disposition is ProviderResultDisposition.QUARANTINED
                    else EventType.ENGINEERING_EXECUTION_RESULT_RECORDED
                ),
                action=(
                    "engineering_execution.result_quarantined"
                    if disposition is ProviderResultDisposition.QUARANTINED
                    else "engineering_execution.result_recorded"
                ),
                resource_id=result.id,
                correlation_id=attempt.idempotency_key,
                details={
                    "result_id": str(result.id),
                    "attempt_id": str(attempt.id),
                    "composition_id": str(composition.id),
                    "status": result.status.value,
                    "disposition": result.disposition.value,
                    "disposition_reason": result.disposition_reason,
                    "repository_mutated": False,
                },
                occurred_at=received_at,
            )
        return result

    async def deliver_next_in_transaction(
        self,
        session: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        now: datetime,
    ) -> CompositionDeliveryPackage | None:
        return await self.repository.next_delivery_for_update(
            session,
            company_id=worker_context.company_id,
            worker_id=worker_context.worker_id,
            provider_identifier=worker_context.provider_identifier,
            now=now,
        )

    async def get_delivery_package(
        self,
        session: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        composition_id: UUID,
    ) -> CompositionDeliveryPackage | None:
        return await self.repository.get_delivery_package(
            session,
            company_id=worker_context.company_id,
            worker_id=worker_context.worker_id,
            composition_id=composition_id,
        )

    async def acknowledge_composition_in_transaction(
        self,
        session: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        composition_id: UUID,
        composition_digest: str,
        instruction_digest: str,
        request_digest: str,
        now: datetime,
    ) -> ExecutionCompositionRecord:
        composition = await self.repository.get_composition(
            session,
            company_id=worker_context.company_id,
            composition_id=composition_id,
        )
        if composition is None or composition.worker_id != worker_context.worker_id:
            raise CompositionNotFoundError("Composition was not found.")
        if (
            composition.provider_identifier != worker_context.provider_identifier
            or composition.lease_id is None
            or composition.expires_at <= now
        ):
            raise CompositionIneligibleError("Composition is not deliverable.")
        if (
            composition.composition_digest != composition_digest
            or composition.instruction_digest != instruction_digest
            or composition.request_digest != request_digest
        ):
            raise CompositionEvidenceMismatchError("Composition evidence differs.")
        return composition

    async def append_progress_in_transaction(
        self,
        session: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        attempt_id: UUID,
        lease_id: UUID,
        composition_digest: str,
        instruction_digest: str,
        request_digest: str,
        phase: ProviderProgressPhase,
        message_code: str,
        summary: str | None,
        percentage: int | None,
        now: datetime,
    ) -> ProviderProgressEventRecord:
        code = message_code.strip().lower()
        normalized_summary = summary.strip() if summary is not None else None
        if not SAFE_CODE.fullmatch(code):
            raise ProgressValidationError("Progress message code is invalid.")
        if normalized_summary is not None and len(normalized_summary) > 500:
            raise ProgressValidationError("Progress summary is too long.")
        if percentage is not None and not 0 <= percentage <= 100:
            raise ProgressValidationError("Progress percentage is invalid.")
        attempt, composition = await self._worker_attempt_binding(
            session,
            worker_context=worker_context,
            attempt_id=attempt_id,
            lease_id=lease_id,
            composition_digest=composition_digest,
            instruction_digest=instruction_digest,
            request_digest=request_digest,
            now=now,
        )
        if attempt.state not in {
            ProviderAttemptState.STARTING,
            ProviderAttemptState.RUNNING,
        }:
            raise AttemptTransitionError("Attempt cannot accept progress.")
        record = await self.repository.append_progress(
            session,
            progress=AppendProviderProgress(
                company_id=worker_context.company_id,
                attempt_id=attempt.id,
                phase=phase,
                message_code=code,
                summary=normalized_summary,
                percentage=percentage,
                created_at=now,
            ),
        )
        await workstream_runtime_service.project_provider_progress(
            session,
            company_id=worker_context.company_id,
            command_id=composition.command_id,
            attempt_id=attempt.id,
            sequence_number=record.sequence_number,
            phase=record.phase.value,
            percentage=record.percentage,
            summary=record.summary,
            message_code=record.message_code,
            occurred_at=now,
        )
        self._stage_worker_event(
            session,
            worker_context=worker_context,
            event_type=EventType.ENGINEERING_EXECUTION_PROGRESS_RECORDED,
            action="engineering_execution.progress_recorded",
            resource_id=attempt.id,
            correlation_id=attempt.idempotency_key,
            details={
                "attempt_id": str(attempt.id),
                "sequence_number": record.sequence_number,
                "phase": record.phase.value,
                "message_code": record.message_code,
            },
            occurred_at=now,
        )
        return record

    async def record_result_in_transaction(
        self,
        session: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        lease_id: UUID,
        composition_digest: str,
        instruction_digest: str,
        request_digest: str,
        command: RecordProviderResult,
        now: datetime,
    ) -> NormalizedProviderResultRecord:
        self._validate_result(command)
        attempt, composition = await self._worker_attempt_binding(
            session,
            worker_context=worker_context,
            attempt_id=command.attempt_id,
            lease_id=lease_id,
            composition_digest=composition_digest,
            instruction_digest=instruction_digest,
            request_digest=request_digest,
            now=now,
            allow_expired=True,
        )
        source = await self.repository.load_source_for_update(
            session,
            company_id=worker_context.company_id,
            execution_id=composition.execution_id,
            lease_id=composition.lease_id,
        )
        disposition, reason = _result_disposition(
            source=source,
            attempt=attempt,
            composition_expires_at=composition.expires_at,
            now=now,
        )
        result = await self.repository.store_result(
            session,
            result=StoreProviderResult(
                company_id=worker_context.company_id,
                attempt_id=attempt.id,
                composition_id=composition.id,
                status=command.status,
                evidence_summary=dict(command.evidence_summary),
                validation_summary=dict(command.validation_summary),
                output_references=command.output_references,
                failure_classification=command.failure_classification,
                received_at=now,
                disposition=disposition,
                disposition_reason=reason,
            ),
        )
        terminal = (
            ProviderAttemptState.QUARANTINED
            if disposition is ProviderResultDisposition.QUARANTINED
            else ProviderAttemptState.COMPLETED
            if disposition is ProviderResultDisposition.ACCEPTED
            and command.status is ProviderResultStatus.SUCCEEDED
            else ProviderAttemptState.CANCELLED
            if disposition is ProviderResultDisposition.ACCEPTED
            and command.status is ProviderResultStatus.CANCELLED
            else ProviderAttemptState.FAILED
            if disposition is ProviderResultDisposition.ACCEPTED
            else None
        )
        if terminal is not None:
            changed = await self.repository.transition_attempt(
                session,
                company_id=worker_context.company_id,
                attempt_id=attempt.id,
                expected_version=attempt.version,
                from_states=(attempt.state,),
                to_state=terminal,
                occurred_at=now,
                failure_classification=command.failure_classification,
            )
            if changed is None:
                raise StaleAttemptVersionError("Attempt version is stale.")
        self._stage_worker_event(
            session,
            worker_context=worker_context,
            event_type=(
                EventType.ENGINEERING_EXECUTION_RESULT_QUARANTINED
                if disposition is ProviderResultDisposition.QUARANTINED
                else EventType.ENGINEERING_EXECUTION_RESULT_RECORDED
            ),
            action=(
                "engineering_execution.result_quarantined"
                if disposition is ProviderResultDisposition.QUARANTINED
                else "engineering_execution.result_recorded"
            ),
            resource_id=result.id,
            correlation_id=attempt.idempotency_key,
            details={
                "attempt_id": str(attempt.id),
                "composition_id": str(composition.id),
                "disposition": disposition.value,
                "repository_mutated": False,
            },
            occurred_at=now,
        )
        return result

    async def acknowledge_cancellation_in_transaction(
        self,
        session: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        attempt_id: UUID,
        lease_id: UUID,
        expected_version: int,
        composition_digest: str,
        now: datetime,
    ) -> ProviderExecutionAttemptRecord:
        attempt, _ = await self._worker_attempt_binding(
            session,
            worker_context=worker_context,
            attempt_id=attempt_id,
            lease_id=lease_id,
            composition_digest=composition_digest,
            instruction_digest=None,
            request_digest=None,
            now=now,
            allow_expired=True,
        )
        if attempt.cancellation_acknowledged_at is not None:
            return attempt
        record = await self.repository.acknowledge_cancellation(
            session,
            company_id=worker_context.company_id,
            attempt_id=attempt.id,
            expected_version=expected_version,
            acknowledged_at=now,
        )
        if record is None:
            raise AttemptTransitionError(
                "Cancellation is not awaiting acknowledgement."
            )
        self._stage_worker_event(
            session,
            worker_context=worker_context,
            event_type=EventType.ENGINEERING_EXECUTION_CANCELLATION_ACKNOWLEDGED,
            action="engineering_execution.cancellation_acknowledged",
            resource_id=record.id,
            correlation_id=record.idempotency_key,
            details={
                "attempt_id": str(record.id),
                "composition_id": str(record.composition_id),
                "version": record.version,
            },
            occurred_at=now,
        )
        return record

    async def _worker_attempt_binding(
        self,
        session: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        attempt_id: UUID,
        lease_id: UUID,
        composition_digest: str,
        instruction_digest: str | None,
        request_digest: str | None,
        now: datetime,
        allow_expired: bool = False,
    ) -> tuple[ProviderExecutionAttemptRecord, ExecutionCompositionRecord]:
        attempt = await self.repository.get_attempt_for_update(
            session,
            company_id=worker_context.company_id,
            attempt_id=attempt_id,
        )
        if (
            attempt is None
            or attempt.worker_id != worker_context.worker_id
            or attempt.lease_id != lease_id
            or attempt.provider_identifier != worker_context.provider_identifier
        ):
            raise CompositionNotFoundError("Attempt was not found.")
        composition = await self.repository.get_composition(
            session,
            company_id=worker_context.company_id,
            composition_id=attempt.composition_id,
        )
        if composition is None or composition.worker_id != worker_context.worker_id:
            raise CompositionNotFoundError("Composition was not found.")
        source = await self.repository.load_source_for_update(
            session,
            company_id=worker_context.company_id,
            execution_id=composition.execution_id,
            lease_id=composition.lease_id,
        )
        if source is None:
            raise CompositionNotFoundError("Composition binding was not found.")
        if (
            source.worker_id != worker_context.worker_id
            or source.worker_provider_identifier != worker_context.provider_identifier
            or source.lease_worker_id != worker_context.worker_id
        ):
            raise CompositionNotFoundError("Composition binding was not found.")
        if not allow_expired and (
            source.lease_state != "active" or source.lease_expires_at <= now
        ):
            raise CompositionIneligibleError("Worker lease is invalid or expired.")
        if not allow_expired and composition.expires_at <= now:
            raise CompositionIneligibleError("Composition has expired.")
        if composition.composition_digest != composition_digest:
            raise CompositionEvidenceMismatchError("Composition digest differs.")
        if (
            instruction_digest is not None
            and composition.instruction_digest != instruction_digest
        ) or (
            request_digest is not None and composition.request_digest != request_digest
        ):
            raise CompositionEvidenceMismatchError("Composition evidence differs.")
        return attempt, composition

    def _stage_worker_event(
        self,
        session: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        event_type: EventType,
        action: str,
        resource_id: UUID,
        correlation_id: UUID,
        details: dict[str, object],
        occurred_at: datetime,
    ) -> None:
        safe_details = {
            **details,
            "worker_id": str(worker_context.worker_id),
            "provider_identifier": worker_context.provider_identifier,
        }
        self.audit.stage(
            session,
            AuditEntry(
                action=action,
                resource_type="engineering_execution",
                company_id=worker_context.company_id,
                resource_id=resource_id,
                correlation_id=correlation_id,
                details=safe_details,
                occurred_at=occurred_at,
            ),
        )
        self.business_events.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="engineering_execution",
                entity_id=resource_id,
                company_id=worker_context.company_id,
                payload=safe_details,
                correlation_id=correlation_id,
                occurred_at=occurred_at,
            ),
        )

    def _require(self, context: AuthorizationContext) -> None:
        if context.membership.status != "active":
            raise CompositionPermissionError("Permission denied.")
        try:
            self.authorization.require_permission(
                context, EngineeringExecutionPermission.REQUEST
            )
        except PermissionDeniedError as error:
            raise CompositionPermissionError("Permission denied.") from error

    @staticmethod
    def _validate_source(
        source: CompositionSource,
        *,
        command: ComposeExecution,
        provider_identifier: str,
        provider_capabilities: set[ProviderCapability],
        now: datetime,
    ) -> None:
        if source.command_approval_state != "approved":
            raise CompositionIneligibleError("Engineering Command is not approved.")
        if source.command_expires_at <= now:
            raise CompositionIneligibleError("Engineering Command has expired.")
        if source.execution_state != "execution_not_connected":
            raise CompositionIneligibleError("Engineering Execution is ineligible.")
        if source.execution_instruction_digest != source.command_instruction_digest:
            raise CompositionEvidenceMismatchError("Execution evidence is stale.")
        if source.worker_state != "leased":
            raise CompositionIneligibleError("Engineering Worker is not leased.")
        if (
            source.lease_state != "active"
            or source.lease_expires_at <= now
            or source.lease_execution_id != source.execution_id
            or source.lease_worker_id != source.worker_id
        ):
            raise CompositionIneligibleError("Worker lease is invalid or expired.")
        if (
            source.worker_provider_identifier != provider_identifier
            or command.provider_identifier.strip().lower() != provider_identifier
        ):
            raise CompositionEvidenceMismatchError("Provider binding differs.")
        evidence = (
            command.instruction_digest,
            command.request_digest,
            command.repository_key,
            command.expected_branch,
            command.expected_head,
            command.approved_code_changes,
        )
        authoritative = (
            source.command_instruction_digest,
            source.command_request_digest,
            source.repository_key,
            source.expected_branch,
            source.expected_head,
            source.requested_code_changes,
        )
        if evidence != authoritative:
            raise CompositionEvidenceMismatchError(
                "Approved composition evidence differs."
            )
        required = set(command.required_capabilities)
        if (
            ProviderCapability(source.lease_capability) not in required
            or not required.issubset(provider_capabilities)
            or not {item.value for item in required}.issubset(
                set(source.worker_capabilities)
            )
        ):
            raise CompositionCapabilityError(
                "Worker, lease, or provider capability is insufficient."
            )

    @staticmethod
    def _validate_result(command: RecordProviderResult) -> None:
        if command.repository_mutated:
            raise ResultValidationError("Repository mutation claims are prohibited.")
        if len(command.output_references) > MAX_OUTPUT_REFERENCES:
            raise ResultValidationError("Too many output references.")
        if any(
            not value.strip() or len(value) > MAX_OUTPUT_REFERENCE_LENGTH
            for value in command.output_references
        ):
            raise ResultValidationError("Output reference is invalid.")
        forbidden = {
            "repository_mutated",
            "commit",
            "push",
            "merge",
            "deployment",
            "shell",
            "docker",
        }
        if forbidden.intersection(command.evidence_summary):
            raise ResultValidationError("Result contains prohibited claims.")

    def _stage_composition_evidence(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        bundle: CompositionBundle,
        occurred_at: datetime,
    ) -> None:
        common: dict[str, object] = {
            "composition_id": str(bundle.composition.id),
            "execution_id": str(bundle.composition.execution_id),
            "worker_id": str(bundle.composition.worker_id),
            "lease_id": str(bundle.composition.lease_id),
            "provider_identifier": bundle.composition.provider_identifier,
            "instruction_digest": bundle.composition.instruction_digest,
            "request_digest": bundle.composition.request_digest,
            "composition_digest": bundle.composition.composition_digest,
            "approved_code_changes": bundle.composition.approved_code_changes,
        }
        self._stage(
            session,
            context=context,
            event_type=EventType.ENGINEERING_EXECUTION_COMPOSITION_CREATED,
            action="engineering_execution.composition_created",
            resource_id=bundle.composition.id,
            correlation_id=bundle.composition.id,
            details=common,
            occurred_at=occurred_at,
        )
        self._stage(
            session,
            context=context,
            event_type=EventType.ENGINEERING_EXECUTION_COMPOSITION_RECEIPT_CREATED,
            action="engineering_execution.composition_receipt_created",
            resource_id=bundle.receipt.id,
            correlation_id=bundle.composition.id,
            details={
                **common,
                "receipt_id": str(bundle.receipt.id),
                "receipt_status": bundle.receipt.status.value,
                "integrity_method": bundle.receipt.integrity.method,
            },
            occurred_at=occurred_at,
        )

    def _stage(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        event_type: EventType,
        action: str,
        resource_id: UUID,
        correlation_id: UUID,
        details: dict[str, object],
        occurred_at: datetime,
    ) -> None:
        self.audit.stage(
            session,
            AuditEntry(
                action=action,
                resource_type="engineering_execution",
                actor_user_id=context.user.id,
                company_id=context.company.id,
                resource_id=resource_id,
                correlation_id=correlation_id,
                details=details,
                occurred_at=occurred_at,
            ),
        )
        self.business_events.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="engineering_execution",
                entity_id=resource_id,
                company_id=context.company.id,
                user_id=context.user.id,
                payload=details,
                correlation_id=correlation_id,
                occurred_at=occurred_at,
            ),
        )


def composition_digest(
    *,
    source: CompositionSource,
    provider_identifier: str,
    required: tuple[str, ...],
    effective: tuple[str, ...],
    approved_code_changes: bool,
) -> str:
    payload = {
        "company_id": str(source.company_id),
        "command_id": str(source.command_id),
        "execution_id": str(source.execution_id),
        "worker_id": str(source.worker_id),
        "lease_id": str(source.lease_id),
        "provider_identifier": provider_identifier,
        "required_capabilities": required,
        "effective_capabilities": effective,
        "approved_code_changes": approved_code_changes,
        "repository_key": source.repository_key,
        "expected_branch": source.expected_branch,
        "expected_head": source.expected_head,
        "instruction_digest": source.command_instruction_digest,
        "request_digest": source.command_request_digest,
        "expires_at": min(
            source.command_expires_at, source.lease_expires_at
        ).isoformat(),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _allowed_from(to_state: ProviderAttemptState) -> tuple[ProviderAttemptState, ...]:
    transitions = {
        ProviderAttemptState.STARTING: (ProviderAttemptState.PREPARED,),
        ProviderAttemptState.RUNNING: (ProviderAttemptState.STARTING,),
        ProviderAttemptState.COMPLETED: (ProviderAttemptState.RUNNING,),
        ProviderAttemptState.FAILED: (
            ProviderAttemptState.PREPARED,
            ProviderAttemptState.STARTING,
            ProviderAttemptState.RUNNING,
        ),
        ProviderAttemptState.CANCELLED: (
            ProviderAttemptState.PREPARED,
            ProviderAttemptState.STARTING,
            ProviderAttemptState.RUNNING,
        ),
        ProviderAttemptState.TIMED_OUT: (
            ProviderAttemptState.STARTING,
            ProviderAttemptState.RUNNING,
        ),
        ProviderAttemptState.QUARANTINED: (
            ProviderAttemptState.PREPARED,
            ProviderAttemptState.STARTING,
            ProviderAttemptState.RUNNING,
        ),
    }
    try:
        return transitions[to_state]
    except KeyError as error:
        raise AttemptTransitionError("Attempt transition is invalid.") from error


def _result_disposition(
    *,
    source: CompositionSource | None,
    attempt: ProviderExecutionAttemptRecord,
    composition_expires_at: datetime,
    now: datetime,
) -> tuple[ProviderResultDisposition, str | None]:
    if source is None:
        return ProviderResultDisposition.QUARANTINED, "binding_unavailable"
    if source.command_approval_state != "approved":
        return ProviderResultDisposition.QUARANTINED, "approval_not_active"
    if source.command_expires_at <= now:
        return ProviderResultDisposition.QUARANTINED, "approval_expired"
    if (
        source.lease_state != "active"
        or source.lease_expires_at <= now
        or composition_expires_at <= now
    ):
        return ProviderResultDisposition.QUARANTINED, "lease_expired"
    if attempt.state in {
        ProviderAttemptState.CANCELLED,
        ProviderAttemptState.TIMED_OUT,
        ProviderAttemptState.QUARANTINED,
    }:
        return ProviderResultDisposition.QUARANTINED, "attempt_terminal"
    if attempt.state is not ProviderAttemptState.RUNNING:
        return ProviderResultDisposition.REJECTED, "attempt_not_running"
    return ProviderResultDisposition.ACCEPTED, None


execution_composition_service = ExecutionCompositionService()
