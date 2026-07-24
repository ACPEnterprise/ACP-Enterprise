from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.permissions.authorization import (
    AuthorizationContext,
    AuthorizationError,
    authorization_service,
)
from app.platform.permissions.codes import EngineeringCommandPermission

from .contracts import (
    ExecutionStatusProvider,
    ExecutionStatusSources,
    MonitoringState,
    ProjectionAvailability,
)
from .repository import SqlExecutionStatusProvider
from .schemas import (
    HeartbeatStatus,
    LeaseStatus,
    MobileExecutionStatus,
    ResultStatus,
    TimelineEntry,
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
    ) -> MobileExecutionStatus:
        self._authorize(context)
        sources = await self.provider.load(
            session, company_id=context.company.id, command_id=command_id
        )
        if sources is None:
            raise ExecutionStatusNotFoundError
        return self._project(sources)

    @staticmethod
    def _authorize(context: AuthorizationContext) -> None:
        if context.membership.status != "active":
            raise AuthorizationError("Active membership required")
        authorization_service.require_permission(
            context, EngineeringCommandPermission.READ
        )

    @staticmethod
    def _project(sources: ExecutionStatusSources) -> MobileExecutionStatus:
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
        timeline.sort(key=lambda item: (item.occurred_at, item.event))

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
            execution_connected=False,
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
            ),
            heartbeat=HeartbeatStatus(
                availability=(
                    ProjectionAvailability.AVAILABLE
                    if sources.heartbeat
                    else ProjectionAvailability.UNAVAILABLE
                ),
                health=sources.heartbeat.health if sources.heartbeat else None,
                last_seen=sources.heartbeat.last_seen if sources.heartbeat else None,
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
            timeline=tuple(timeline),
            terminal=terminal,
            polling_after_seconds=None if terminal else 30,
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
