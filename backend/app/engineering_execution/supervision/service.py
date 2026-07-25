from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.execution_providers.contracts import ProviderCapability
from app.execution_providers.contracts import ProviderCapabilities
from app.execution_providers.errors import (
    ProviderAuthenticationError,
    ProviderNotFoundError,
    ProviderUnavailableError,
)
from app.execution_providers.runtime import (
    ProviderCredentialStatus,
    ProviderRuntime,
    ProviderRuntimeRequest,
    ProviderRuntimeState,
)
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.worker_control.contracts import AuthenticatedWorkerContext

from .contracts import (
    CapabilityNegotiation,
    CreateProviderSession,
    ProviderSessionState,
    SupervisorRecovery,
    SupervisorState,
)
from .errors import (
    SupervisionCapabilityError,
    SupervisionConflictError,
    SupervisionIneligibleError,
    SupervisionNotFoundError,
    SupervisionTransitionError,
)
from .records import LiveClientSupervisorRecord, ProviderSessionRecord
from .repository import SupervisionRepository


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LiveClientSupervisor:
    def __init__(
        self,
        *,
        repository: type[SupervisionRepository] = SupervisionRepository,
        audit: AuditService = audit_service,
        events: type[BusinessEventService] = BusinessEventService,
    ) -> None:
        self.repository = repository
        self.audit = audit
        self.events = events

    async def start(
        self,
        session: AsyncSession,
        *,
        context: AuthenticatedWorkerContext,
        now: datetime | None = None,
    ) -> LiveClientSupervisorRecord:
        occurred_at = now or utc_now()
        async with session.begin():
            current = await self.repository.get_or_create_supervisor(
                session,
                company_id=context.company_id,
                worker_id=context.worker_id,
                now=occurred_at,
            )
            if current.state is SupervisorState.READY:
                return current
            starting = await self.repository.transition_supervisor(
                session,
                company_id=context.company_id,
                supervisor_id=current.id,
                expected_version=current.version,
                from_states=(
                    SupervisorState.STOPPED,
                    SupervisorState.RECONNECTING,
                    SupervisorState.TIMED_OUT,
                    SupervisorState.FAILED,
                ),
                to_state=SupervisorState.STARTING,
                now=occurred_at,
            )
            if starting is None:
                raise SupervisionTransitionError("Supervisor cannot start.")
            ready = await self.repository.transition_supervisor(
                session,
                company_id=context.company_id,
                supervisor_id=current.id,
                expected_version=starting.version,
                from_states=(SupervisorState.STARTING,),
                to_state=SupervisorState.READY,
                now=occurred_at,
            )
            if ready is None:
                raise SupervisionConflictError("Supervisor version changed.")
            self._stage(
                session,
                context=context,
                event_type=EventType.ENGINEERING_SUPERVISOR_STARTED,
                action="engineering_execution.supervisor_started",
                resource_id=ready.id,
                details={"state": ready.state.value, "version": ready.version},
                now=occurred_at,
            )
        return ready

    async def recover(
        self,
        session: AsyncSession,
        *,
        context: AuthenticatedWorkerContext,
        now: datetime | None = None,
    ) -> SupervisorRecovery:
        occurred_at = now or utc_now()
        async with session.begin():
            current = await self.repository.get_or_create_supervisor(
                session,
                company_id=context.company_id,
                worker_id=context.worker_id,
                now=occurred_at,
            )
            recovering = await self.repository.transition_supervisor(
                session,
                company_id=context.company_id,
                supervisor_id=current.id,
                expected_version=current.version,
                from_states=(
                    SupervisorState.STOPPED,
                    SupervisorState.READY,
                    SupervisorState.RECONNECTING,
                    SupervisorState.TIMED_OUT,
                    SupervisorState.FAILED,
                ),
                to_state=SupervisorState.RECOVERING,
                now=occurred_at,
            )
            if recovering is None:
                raise SupervisionTransitionError("Supervisor cannot recover.")
            items = await self.repository.recovery_items(
                session,
                company_id=context.company_id,
                worker_id=context.worker_id,
                now=occurred_at,
            )
            ready = await self.repository.transition_supervisor(
                session,
                company_id=context.company_id,
                supervisor_id=current.id,
                expected_version=recovering.version,
                from_states=(SupervisorState.RECOVERING,),
                to_state=SupervisorState.READY,
                now=occurred_at,
            )
            if ready is None:
                raise SupervisionConflictError("Supervisor version changed.")
            self._stage(
                session,
                context=context,
                event_type=EventType.ENGINEERING_SUPERVISOR_RECOVERED,
                action="engineering_execution.supervisor_recovered",
                resource_id=ready.id,
                details={"recovery_count": len(items), "state": ready.state.value},
                now=occurred_at,
            )
        return SupervisorRecovery(ready.id, occurred_at, items)

    def _stage(
        self,
        session: AsyncSession,
        *,
        context: AuthenticatedWorkerContext,
        event_type: EventType,
        action: str,
        resource_id: UUID,
        details: dict[str, object],
        now: datetime,
    ) -> None:
        safe_details: dict[str, object] = {
            **details,
            "worker_id": str(context.worker_id),
            "provider_identifier": context.provider_identifier,
        }
        self.audit.stage(
            session,
            AuditEntry(
                action=action,
                resource_type="engineering_execution_supervisor",
                company_id=context.company_id,
                resource_id=resource_id,
                details=safe_details,
                occurred_at=now,
            ),
        )
        self.events.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="engineering_execution_supervisor",
                entity_id=resource_id,
                company_id=context.company_id,
                payload=safe_details,
                occurred_at=now,
            ),
        )


class ProviderSessionService:
    def __init__(
        self,
        *,
        repository: type[SupervisionRepository] = SupervisionRepository,
        runtime: ProviderRuntime,
        audit: AuditService = audit_service,
        events: type[BusinessEventService] = BusinessEventService,
    ) -> None:
        self.repository = repository
        self.runtime = runtime
        self.audit = audit
        self.events = events

    async def create(
        self,
        session: AsyncSession,
        *,
        context: AuthenticatedWorkerContext,
        command: CreateProviderSession,
        now: datetime | None = None,
    ) -> ProviderSessionRecord:
        occurred_at = now or utc_now()
        if not 30 <= command.timeout_seconds <= 3600:
            raise SupervisionIneligibleError("Session timeout is invalid.")
        try:
            async with session.begin():
                try:
                    supervisor = await self.repository.get_or_create_supervisor(
                        session,
                        company_id=context.company_id,
                        worker_id=context.worker_id,
                        now=occurred_at,
                    )
                except ValueError as error:
                    raise SupervisionNotFoundError("Worker was not found.") from error
                if supervisor.state is not SupervisorState.READY:
                    raise SupervisionIneligibleError("Supervisor is not ready.")
                source = await self.repository.load_session_source_for_update(
                    session,
                    company_id=context.company_id,
                    worker_id=context.worker_id,
                    composition_id=command.composition_id,
                    attempt_id=command.attempt_id,
                )
                if source is None:
                    raise SupervisionNotFoundError("Composition was not found.")
                composition, attempt, lease, worker = source
                if (
                    composition.expires_at <= occurred_at
                    or lease.status != "active"
                    or lease.expires_at <= occurred_at
                    or composition.provider_identifier != context.provider_identifier
                    or worker.provider_identifier != context.provider_identifier
                    or attempt.state not in {"prepared", "starting", "running"}
                ):
                    raise SupervisionIneligibleError(
                        "Composition is not eligible for a provider session."
                    )
                negotiation = self.negotiate(
                    composition_required=tuple(composition.required_capabilities),
                    composition_effective=tuple(composition.effective_capabilities),
                    worker_capabilities=tuple(worker.capabilities),
                    provider_identifier=composition.provider_identifier,
                    approved_code_changes=composition.approved_code_changes,
                )
                record = await self.repository.create_session(
                    session,
                    supervisor_id=supervisor.id,
                    composition=composition,
                    attempt=attempt,
                    effective_capabilities=negotiation.effective,
                    expires_at=min(
                        composition.expires_at,
                        lease.expires_at,
                        occurred_at + timedelta(seconds=command.timeout_seconds),
                    ),
                    now=occurred_at,
                )
                self._stage(
                    session,
                    context=context,
                    event_type=EventType.ENGINEERING_PROVIDER_SESSION_CREATED,
                    action="engineering_execution.provider_session_created",
                    record=record,
                    now=occurred_at,
                )
            return record
        except IntegrityError as error:
            await session.rollback()
            raise SupervisionConflictError("Provider session conflicts.") from error

    def negotiate(
        self,
        *,
        composition_required: tuple[str, ...],
        composition_effective: tuple[str, ...],
        worker_capabilities: tuple[str, ...],
        provider_identifier: str,
        approved_code_changes: bool,
    ) -> CapabilityNegotiation:
        try:
            provider_capabilities = self.runtime.capabilities(provider_identifier)
            required = tuple(
                ProviderCapability(value) for value in composition_required
            )
        except (ProviderNotFoundError, ValueError) as error:
            raise SupervisionCapabilityError(
                "Provider capability declaration is unavailable."
            ) from error
        effective_values = (
            set(composition_effective)
            & set(worker_capabilities)
            & {item.value for item in provider_capabilities.values}
            & {item.value for item in required}
        )
        if effective_values != {item.value for item in required}:
            raise SupervisionCapabilityError(
                "Effective provider capability intersection is insufficient."
            )
        return CapabilityNegotiation(
            required=required,
            effective=tuple(
                ProviderCapability(value) for value in sorted(effective_values)
            ),
            approved_code_changes=approved_code_changes,
        )

    async def transition(
        self,
        session: AsyncSession,
        *,
        context: AuthenticatedWorkerContext,
        session_id: UUID,
        expected_version: int,
        to_state: ProviderSessionState,
        failure_classification: str | None = None,
        now: datetime | None = None,
    ) -> ProviderSessionRecord:
        occurred_at = now or utc_now()
        allowed = _session_allowed_from(to_state)
        async with session.begin():
            record = await self.repository.transition_session(
                session,
                company_id=context.company_id,
                session_id=session_id,
                expected_version=expected_version,
                from_states=allowed,
                to_state=to_state,
                now=occurred_at,
                failure_classification=failure_classification,
            )
            if record is None or record.worker_id != context.worker_id:
                raise SupervisionTransitionError("Provider session transition failed.")
            event_type = (
                EventType.ENGINEERING_PROVIDER_SESSION_READY
                if to_state is ProviderSessionState.READY
                else EventType.ENGINEERING_PROVIDER_SESSION_CLOSED
                if to_state
                in {
                    ProviderSessionState.CLOSED,
                    ProviderSessionState.EXPIRED,
                    ProviderSessionState.FAILED,
                    ProviderSessionState.CANCELLED,
                }
                else EventType.ENGINEERING_PROVIDER_SESSION_STATE_CHANGED
            )
            self._stage(
                session,
                context=context,
                event_type=event_type,
                action="engineering_execution.provider_session_state_changed",
                record=record,
                now=occurred_at,
            )
        return record

    async def open(
        self,
        session: AsyncSession,
        *,
        context: AuthenticatedWorkerContext,
        record: ProviderSessionRecord,
        now: datetime | None = None,
    ) -> ProviderSessionRecord:
        occurred_at = now or utc_now()
        async with session.begin():
            opening = await self.repository.update_runtime(
                session,
                company_id=context.company_id,
                session_id=record.id,
                expected_version=record.version,
                from_states=(ProviderSessionState.CREATED,),
                to_state=ProviderSessionState.OPENING,
                runtime_state=ProviderRuntimeState.INITIALIZING,
                credential_status=ProviderCredentialStatus.UNAVAILABLE,
                provider_ready=False,
                provider_session_reference=None,
                now=occurred_at,
            )
            if opening is None or opening.worker_id != context.worker_id:
                raise SupervisionTransitionError("Provider session cannot initialize.")
            self._stage(
                session,
                context=context,
                event_type=EventType.ENGINEERING_PROVIDER_RUNTIME_INITIALIZED,
                action="engineering_execution.provider_runtime_initialized",
                record=opening,
                now=occurred_at,
            )
        try:
            runtime_result = await self.runtime.open(
                ProviderRuntimeRequest(
                    provider_session_id=opening.id,
                    company_id=opening.company_id,
                    worker_id=opening.worker_id,
                    provider_identifier=opening.provider_identifier,
                    capabilities=ProviderCapabilities(opening.effective_capabilities),
                    expires_at=opening.expires_at,
                )
            )
        except ProviderAuthenticationError:
            return await self._runtime_failure(
                session,
                context=context,
                record=opening,
                runtime_state=ProviderRuntimeState.CREDENTIAL_FAILURE,
                credential_status=ProviderCredentialStatus.INVALID,
                failure_classification="credential_failure",
                now=occurred_at,
            )
        except ProviderUnavailableError:
            return await self._runtime_failure(
                session,
                context=context,
                record=opening,
                runtime_state=ProviderRuntimeState.PROVIDER_FAILURE,
                credential_status=ProviderCredentialStatus.USABLE,
                failure_classification="provider_unavailable",
                now=occurred_at,
            )
        if (
            runtime_result.state is not ProviderRuntimeState.PROVIDER_READY
            or runtime_result.credential_status is not ProviderCredentialStatus.USABLE
            or runtime_result.provider_session_reference is None
        ):
            return await self._runtime_failure(
                session,
                context=context,
                record=opening,
                runtime_state=ProviderRuntimeState.PROVIDER_FAILURE,
                credential_status=runtime_result.credential_status,
                failure_classification="provider_not_ready",
                now=runtime_result.observed_at,
            )
        async with session.begin():
            ready = await self.repository.update_runtime(
                session,
                company_id=context.company_id,
                session_id=opening.id,
                expected_version=opening.version,
                from_states=(ProviderSessionState.OPENING,),
                to_state=ProviderSessionState.READY,
                runtime_state=runtime_result.state,
                credential_status=runtime_result.credential_status,
                provider_ready=True,
                provider_session_reference=runtime_result.provider_session_reference,
                now=runtime_result.observed_at,
            )
            if ready is None:
                raise SupervisionConflictError("Provider session version changed.")
            self._stage(
                session,
                context=context,
                event_type=EventType.ENGINEERING_PROVIDER_CREDENTIAL_VALIDATED,
                action="engineering_execution.provider_credential_validated",
                record=ready,
                now=runtime_result.observed_at,
            )
            self._stage(
                session,
                context=context,
                event_type=EventType.ENGINEERING_PROVIDER_READY,
                action="engineering_execution.provider_ready",
                record=ready,
                now=runtime_result.observed_at,
            )
        return ready

    async def _runtime_failure(
        self,
        session: AsyncSession,
        *,
        context: AuthenticatedWorkerContext,
        record: ProviderSessionRecord,
        runtime_state: ProviderRuntimeState,
        credential_status: ProviderCredentialStatus,
        failure_classification: str,
        now: datetime,
    ) -> ProviderSessionRecord:
        async with session.begin():
            failed = await self.repository.update_runtime(
                session,
                company_id=context.company_id,
                session_id=record.id,
                expected_version=record.version,
                from_states=(ProviderSessionState.OPENING,),
                to_state=ProviderSessionState.FAILED,
                runtime_state=runtime_state,
                credential_status=credential_status,
                provider_ready=False,
                provider_session_reference=None,
                now=now,
                failure_classification=failure_classification,
            )
            if failed is None:
                raise SupervisionConflictError("Provider session version changed.")
            self._stage(
                session,
                context=context,
                event_type=EventType.ENGINEERING_PROVIDER_RUNTIME_FAILED,
                action="engineering_execution.provider_runtime_failed",
                record=failed,
                now=now,
            )
        return failed

    def _stage(
        self,
        session: AsyncSession,
        *,
        context: AuthenticatedWorkerContext,
        event_type: EventType,
        action: str,
        record: ProviderSessionRecord,
        now: datetime,
    ) -> None:
        details: dict[str, object] = {
            "provider_session_id": str(record.id),
            "composition_id": str(record.composition_id),
            "attempt_id": str(record.attempt_id),
            "worker_id": str(record.worker_id),
            "provider_identifier": record.provider_identifier,
            "state": record.state.value,
            "runtime_state": record.runtime_state.value,
            "provider_ready": record.provider_ready,
            "version": record.version,
        }
        self.audit.stage(
            session,
            AuditEntry(
                action=action,
                resource_type="engineering_provider_session",
                company_id=context.company_id,
                resource_id=record.id,
                details=details,
                occurred_at=now,
            ),
        )
        self.events.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="engineering_provider_session",
                entity_id=record.id,
                company_id=context.company_id,
                payload=details,
                occurred_at=now,
            ),
        )


def _session_allowed_from(
    to_state: ProviderSessionState,
) -> tuple[ProviderSessionState, ...]:
    transitions = {
        ProviderSessionState.OPENING: (ProviderSessionState.CREATED,),
        ProviderSessionState.READY: (ProviderSessionState.OPENING,),
        ProviderSessionState.ACTIVE: (ProviderSessionState.READY,),
        ProviderSessionState.CLOSING: (
            ProviderSessionState.READY,
            ProviderSessionState.ACTIVE,
        ),
        ProviderSessionState.CLOSED: (ProviderSessionState.CLOSING,),
        ProviderSessionState.EXPIRED: (
            ProviderSessionState.CREATED,
            ProviderSessionState.OPENING,
            ProviderSessionState.READY,
            ProviderSessionState.ACTIVE,
        ),
        ProviderSessionState.FAILED: (
            ProviderSessionState.CREATED,
            ProviderSessionState.OPENING,
            ProviderSessionState.READY,
            ProviderSessionState.ACTIVE,
            ProviderSessionState.CLOSING,
        ),
        ProviderSessionState.CANCELLED: (
            ProviderSessionState.CREATED,
            ProviderSessionState.OPENING,
            ProviderSessionState.READY,
            ProviderSessionState.ACTIVE,
            ProviderSessionState.CLOSING,
        ),
    }
    try:
        return transitions[to_state]
    except KeyError as error:
        raise SupervisionTransitionError(
            "Provider session transition is invalid."
        ) from error
