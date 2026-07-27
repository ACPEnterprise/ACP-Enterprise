from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.permissions.authorization import (
    AuthorizationContext,
    AuthorizationError,
    authorization_service,
)
from app.platform.permissions.codes import EngineeringCommandPermission

from .contracts import (
    ConnectionState,
    ExecutionStatusProvider,
    ExecutionStatusSources,
    LeasePhase,
    MonitoringState,
    ProjectionAvailability,
)
from .policy import HEARTBEAT_FRESH_FOR, LEASE_EXPIRING_WITHIN
from .repository import SqlExecutionStatusProvider
from .schemas import (
    HeartbeatStatus,
    LeaseStatus,
    MobileExecutionStatus,
    ResultStatus,
    SupervisorStatus,
    TimelineEntry,
    TransportSessionStatus,
)


class ExecutionStatusNotFoundError(Exception):
    """The command is absent from the active Company scope."""


class MobileExecutionStatusService:
    def __init__(self, provider: ExecutionStatusProvider | None = None) -> None:
        self.provider = provider or SqlExecutionStatusProvider()

    async def get(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command_id: UUID,
        now: datetime | None = None,
    ) -> MobileExecutionStatus:
        self._authorize(context)
        sources = await self.provider.load(
            session, company_id=context.company.id, command_id=command_id
        )
        if sources is None:
            raise ExecutionStatusNotFoundError
        return self._project(sources, now=now or datetime.now(timezone.utc))

    @staticmethod
    def _authorize(context: AuthorizationContext) -> None:
        if context.membership.status != "active":
            raise AuthorizationError("Active membership required")
        authorization_service.require_permission(
            context, EngineeringCommandPermission.READ
        )

    @staticmethod
    def _project(
        sources: ExecutionStatusSources, *, now: datetime
    ) -> MobileExecutionStatus:
        execution = sources.execution
        approved = sources.command.approval_state == "approved"
        if execution is None:
            monitoring_state = (
                MonitoringState.APPROVED_NOT_DISPATCHABLE
                if approved
                else MonitoringState.NOT_APPROVED
            )
        else:
            monitoring_state = (
                MonitoringState.DISCONNECTED
                if execution.state == "execution_not_connected"
                else MonitoringState(execution.state)
            )

        timeline = [
            TimelineEntry(
                event="command_updated",
                occurred_at=sources.command.command_updated_at,
            )
        ]
        if execution is not None:
            timeline.append(
                TimelineEntry(
                    event="execution_requested", occurred_at=execution.requested_at
                )
            )
            if execution.started_at:
                timeline.append(
                    TimelineEntry(
                        event="execution_started", occurred_at=execution.started_at
                    )
                )
            if execution.finished_at:
                timeline.append(
                    TimelineEntry(
                        event="execution_finished", occurred_at=execution.finished_at
                    )
                )
        if sources.lease is not None:
            timeline.append(
                TimelineEntry(
                    event="lease_started", occurred_at=sources.lease.started_at
                )
            )
            if sources.lease.released_at:
                timeline.append(
                    TimelineEntry(
                        event="lease_released",
                        occurred_at=sources.lease.released_at,
                    )
                )
        if sources.result is not None:
            timeline.append(
                TimelineEntry(
                    event="result_recorded", occurred_at=sources.result.created_at
                )
            )
        if sources.transport_session is not None:
            timeline.append(
                TimelineEntry(
                    event="transport_session_established",
                    occurred_at=sources.transport_session.established_at,
                )
            )
            if sources.transport_session.last_message_at is not None:
                timeline.append(
                    TimelineEntry(
                        event="transport_contact",
                        occurred_at=sources.transport_session.last_message_at,
                    )
                )
        if sources.supervisor is not None:
            timeline.append(
                TimelineEntry(
                    event="supervisor_state_updated",
                    occurred_at=sources.supervisor.updated_at,
                )
            )
        timeline.sort(key=lambda item: (item.occurred_at, item.event))

        heartbeat_age = (
            max(0, int((now - sources.heartbeat.last_seen).total_seconds()))
            if sources.heartbeat
            else None
        )
        transport_session = sources.transport_session
        session_active = bool(
            transport_session
            and transport_session.state == "active"
            and transport_session.expires_at > now
        )
        heartbeat_fresh = bool(
            sources.heartbeat
            and now - sources.heartbeat.last_seen <= HEARTBEAT_FRESH_FOR
        )
        if session_active and heartbeat_fresh:
            connection_state = ConnectionState.CONNECTED
        elif session_active:
            connection_state = ConnectionState.CONNECTING
        else:
            connection_state = ConnectionState.DISCONNECTED
        lease_phase = LeasePhase.INACTIVE
        if sources.lease and sources.lease.status == "active":
            lease_phase = (
                LeasePhase.EXPIRING
                if sources.lease.expires_at <= now + LEASE_EXPIRING_WITHIN
                else LeasePhase.ACTIVE
            )
        last_contact = (
            max(
                timestamp
                for timestamp in (
                    sources.heartbeat.last_seen if sources.heartbeat else None,
                    transport_session.last_message_at if transport_session else None,
                    transport_session.established_at if transport_session else None,
                )
                if timestamp is not None
            )
            if sources.heartbeat or transport_session
            else None
        )
        terminal = monitoring_state in {
            MonitoringState.COMPLETED,
            MonitoringState.FAILED,
            MonitoringState.CANCELLED,
        }
        return MobileExecutionStatus(
            command_id=sources.command.command_id,
            ecid=sources.command.ecid,
            approval_state=sources.command.approval_state,
            monitoring_state=monitoring_state,
            execution_available=execution is not None,
            execution_connected=bool(
                sources.supervisor and sources.supervisor.provider_ready
            ),
            connection_state=connection_state,
            transport_health=(
                sources.heartbeat.health
                if heartbeat_fresh and sources.heartbeat
                else "stale"
                if sources.heartbeat
                else "unavailable"
            ),
            execution_id=execution.execution_id if execution else None,
            execution_state=execution.state if execution else None,
            execution_status=execution.status if execution else None,
            progress_label=_progress_label(monitoring_state),
            requested_at=execution.requested_at if execution else None,
            started_at=execution.started_at if execution else None,
            finished_at=execution.finished_at if execution else None,
            updated_at=execution.updated_at
            if execution
            else sources.command.command_updated_at,
            lease=LeaseStatus(
                availability=(
                    ProjectionAvailability.AVAILABLE
                    if sources.lease
                    else ProjectionAvailability.UNAVAILABLE
                ),
                status=sources.lease.status if sources.lease else None,
                started_at=sources.lease.started_at if sources.lease else None,
                expires_at=sources.lease.expires_at if sources.lease else None,
                released_at=sources.lease.released_at if sources.lease else None,
                phase=lease_phase,
            ),
            heartbeat=HeartbeatStatus(
                availability=(
                    ProjectionAvailability.AVAILABLE
                    if sources.heartbeat
                    else ProjectionAvailability.UNAVAILABLE
                ),
                health=sources.heartbeat.health if sources.heartbeat else None,
                last_seen=sources.heartbeat.last_seen if sources.heartbeat else None,
                age_seconds=heartbeat_age,
            ),
            transport_session=TransportSessionStatus(
                availability=(
                    ProjectionAvailability.AVAILABLE
                    if transport_session
                    else ProjectionAvailability.UNAVAILABLE
                ),
                state=transport_session.state if transport_session else None,
                established_at=(
                    transport_session.established_at if transport_session else None
                ),
                expires_at=transport_session.expires_at if transport_session else None,
                last_contact_at=last_contact,
            ),
            result=ResultStatus(
                availability=(
                    ProjectionAvailability.AVAILABLE
                    if sources.result
                    else ProjectionAvailability.UNAVAILABLE
                ),
                status=sources.result.status if sources.result else None,
                validation_available=bool(
                    sources.result and sources.result.validation_available
                ),
                evidence_available=bool(
                    sources.result and sources.result.evidence_available
                ),
                output_reference_count=(
                    sources.result.output_reference_count if sources.result else 0
                ),
                failure_classification=(
                    sources.result.failure_classification
                    if sources.result
                    else execution.failure_classification
                    if execution
                    else None
                ),
                created_at=sources.result.created_at if sources.result else None,
            ),
            supervisor=SupervisorStatus(
                availability=(
                    ProjectionAvailability.AVAILABLE
                    if sources.supervisor
                    else ProjectionAvailability.UNAVAILABLE
                ),
                state=(
                    sources.supervisor.supervisor_state if sources.supervisor else None
                ),
                session_state=(
                    sources.supervisor.session_state if sources.supervisor else None
                ),
                runtime_state=(
                    sources.supervisor.runtime_state if sources.supervisor else None
                ),
                credential_status=(
                    sources.supervisor.credential_status
                    if sources.supervisor
                    else "unavailable"
                ),
                provider_ready=bool(
                    sources.supervisor and sources.supervisor.provider_ready
                ),
                ready=bool(sources.supervisor and sources.supervisor.ready),
                reconnecting=bool(
                    sources.supervisor
                    and sources.supervisor.supervisor_state == "reconnecting"
                ),
                recovering=bool(
                    sources.supervisor
                    and sources.supervisor.supervisor_state == "recovering"
                ),
                timed_out=bool(
                    sources.supervisor
                    and (
                        sources.supervisor.supervisor_state == "timed_out"
                        or sources.supervisor.session_state == "expired"
                    )
                ),
                cancelled=bool(
                    sources.supervisor
                    and (
                        sources.supervisor.supervisor_state == "cancelled"
                        or sources.supervisor.session_state == "cancelled"
                    )
                ),
                failed=bool(
                    sources.supervisor
                    and (
                        sources.supervisor.supervisor_state == "failed"
                        or sources.supervisor.session_state == "failed"
                    )
                ),
                updated_at=(
                    sources.supervisor.updated_at if sources.supervisor else None
                ),
                expires_at=(
                    sources.supervisor.expires_at if sources.supervisor else None
                ),
                failure_classification=(
                    sources.supervisor.failure_classification
                    if sources.supervisor
                    else None
                ),
                execution_active=bool(
                    sources.supervisor and sources.supervisor.execution_active
                ),
                command_id=(
                    sources.supervisor.command_id if sources.supervisor else None
                ),
                execution_offer_id=(
                    sources.supervisor.execution_offer_id
                    if sources.supervisor
                    else None
                ),
                provider_session_reference_present=bool(
                    sources.supervisor
                    and sources.supervisor.provider_session_reference_present
                ),
            ),
            timeline=tuple(timeline),
            terminal=terminal,
            polling_after_seconds=(
                None
                if terminal
                else 10
                if connection_state is ConnectionState.CONNECTED
                or lease_phase is LeasePhase.EXPIRING
                else 30
                if connection_state is ConnectionState.CONNECTING
                else 60
            ),
        )


def _progress_label(state: MonitoringState) -> str:
    return {
        MonitoringState.NOT_APPROVED: "Awaiting owner approval",
        MonitoringState.APPROVED_NOT_DISPATCHABLE: "Approved; dispatch unavailable",
        MonitoringState.DISCONNECTED: "Execution not connected",
        MonitoringState.QUEUED: "Queued",
        MonitoringState.STARTING: "Starting",
        MonitoringState.RUNNING: "Running",
        MonitoringState.COMPLETED: "Completed",
        MonitoringState.FAILED: "Failed",
        MonitoringState.CANCELLED: "Cancelled",
    }[state]


mobile_execution_status_service = MobileExecutionStatusService()
