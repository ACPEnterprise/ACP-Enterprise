from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_control.models import EngineeringCommand
from app.engineering_execution.composition.models import (
    ExecutionComposition,
    ProviderExecutionAttempt,
)
from app.engineering_execution.models import EngineeringExecution
from app.engineering_execution.supervision.models import (
    LiveClientSupervisorModel,
    ProviderSessionModel,
)
from app.worker_control.models import (
    EngineeringWorker,
    WorkerHeartbeat,
    WorkerLease,
    WorkerResult,
)
from app.worker_control.transport.persistence.models import (
    WorkerTransportReceipt,
    WorkerTransportSession,
)
from app.worker_identity.contracts import (
    WorkerCredentialState,
    WorkerIdentityState,
)
from app.worker_identity.models import WorkerCredential, WorkerIdentity

from .contracts import (
    CommandStatusSource,
    ExecutionStatusSource,
    ExecutionStatusSources,
    HeartbeatStatusSource,
    LeaseStatusSource,
    ResultStatusSource,
    SupervisorStatusSource,
    TransportSessionStatusSource,
)


class SqlExecutionStatusProvider:
    """Company-scoped read projection over existing authoritative tables."""

    async def load(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        command_id: UUID,
    ) -> ExecutionStatusSources | None:
        command = await session.scalar(
            select(EngineeringCommand).where(
                EngineeringCommand.company_id == company_id,
                EngineeringCommand.id == command_id,
            )
        )
        if command is None:
            return None

        execution = await session.scalar(
            select(EngineeringExecution).where(
                EngineeringExecution.company_id == company_id,
                EngineeringExecution.command_id == command_id,
            )
        )
        lease: WorkerLease | None = None
        heartbeat: WorkerHeartbeat | None = None
        result: WorkerResult | None = None
        transport_session: WorkerTransportSession | None = None
        supervisor_source: SupervisorStatusSource | None = None
        if execution is not None:
            lease = await session.scalar(
                select(WorkerLease)
                .where(
                    WorkerLease.company_id == company_id,
                    WorkerLease.execution_id == execution.id,
                )
                .order_by(WorkerLease.created_at.desc(), WorkerLease.id.desc())
                .limit(1)
            )
            result = await session.scalar(
                select(WorkerResult)
                .where(
                    WorkerResult.company_id == company_id,
                    WorkerResult.execution_id == execution.id,
                )
                .order_by(WorkerResult.created_at.desc(), WorkerResult.id.desc())
                .limit(1)
            )
            if lease is not None:
                worker_exists = await session.scalar(
                    select(EngineeringWorker.id).where(
                        EngineeringWorker.company_id == company_id,
                        EngineeringWorker.id == lease.worker_id,
                    )
                )
                if worker_exists is not None:
                    heartbeat = await session.scalar(
                        select(WorkerHeartbeat)
                        .where(
                            WorkerHeartbeat.company_id == company_id,
                            WorkerHeartbeat.worker_id == lease.worker_id,
                        )
                        .order_by(
                            WorkerHeartbeat.last_seen.desc(),
                            WorkerHeartbeat.id.desc(),
                        )
                        .limit(1)
                    )
                    transport_session = await session.scalar(
                        select(WorkerTransportSession)
                        .join(
                            WorkerIdentity,
                            WorkerIdentity.id
                            == WorkerTransportSession.worker_identity_id,
                        )
                        .join(
                            WorkerCredential,
                            WorkerCredential.id == WorkerTransportSession.credential_id,
                        )
                        .where(
                            WorkerTransportSession.company_id == company_id,
                            WorkerTransportSession.worker_id == lease.worker_id,
                            WorkerIdentity.company_id == company_id,
                            WorkerIdentity.orchestration_worker_id == lease.worker_id,
                            WorkerIdentity.state == WorkerIdentityState.ACTIVE.value,
                            WorkerCredential.company_id == company_id,
                            WorkerCredential.identity_id
                            == WorkerTransportSession.worker_identity_id,
                            WorkerCredential.version
                            == WorkerTransportSession.credential_version,
                            WorkerCredential.state
                            == WorkerCredentialState.ACTIVE.value,
                            WorkerCredential.expires_at > func.now(),
                        )
                        .order_by(
                            WorkerTransportSession.established_at.desc(),
                            WorkerTransportSession.id.desc(),
                        )
                        .limit(1)
                    )
                    composition = await session.scalar(
                        select(ExecutionComposition)
                        .where(
                            ExecutionComposition.company_id == company_id,
                            ExecutionComposition.execution_id == execution.id,
                            ExecutionComposition.worker_id == lease.worker_id,
                        )
                        .order_by(
                            ExecutionComposition.created_at.desc(),
                            ExecutionComposition.id.desc(),
                        )
                        .limit(1)
                    )
                    supervisor = await session.scalar(
                        select(LiveClientSupervisorModel)
                        .where(
                            LiveClientSupervisorModel.company_id == company_id,
                            LiveClientSupervisorModel.worker_id == lease.worker_id,
                        )
                        .limit(1)
                    )
                    provider_session = (
                        None
                        if composition is None
                        else await session.scalar(
                            select(ProviderSessionModel)
                            .where(
                                ProviderSessionModel.company_id == company_id,
                                ProviderSessionModel.composition_id == composition.id,
                            )
                            .order_by(
                                ProviderSessionModel.created_at.desc(),
                                ProviderSessionModel.id.desc(),
                            )
                            .limit(1)
                        )
                    )
                    provider_attempt = (
                        None
                        if provider_session is None
                        else await session.scalar(
                            select(ProviderExecutionAttempt).where(
                                ProviderExecutionAttempt.company_id == company_id,
                                ProviderExecutionAttempt.id
                                == provider_session.attempt_id,
                            )
                        )
                    )
                    if supervisor is not None:
                        supervisor_source = SupervisorStatusSource(
                            supervisor_state=supervisor.state,
                            session_state=(
                                provider_session.state
                                if provider_session is not None
                                else None
                            ),
                            runtime_state=(
                                provider_session.runtime_state
                                if provider_session is not None
                                else None
                            ),
                            credential_status=(
                                provider_session.credential_status
                                if provider_session is not None
                                else "unavailable"
                            ),
                            provider_ready=bool(
                                provider_session and provider_session.provider_ready
                            ),
                            ready=supervisor.state == "ready"
                            and bool(
                                provider_session and provider_session.provider_ready
                            ),
                            updated_at=max(
                                supervisor.updated_at,
                                provider_session.updated_at
                                if provider_session is not None
                                else supervisor.updated_at,
                            ),
                            expires_at=(
                                provider_session.expires_at
                                if provider_session is not None
                                else None
                            ),
                            failure_classification=(
                                provider_session.failure_classification
                                if provider_session is not None
                                else supervisor.failure_classification
                            ),
                            execution_active=bool(
                                provider_attempt
                                and provider_attempt.state in {"starting", "running"}
                            ),
                            command_id=command.id,
                            execution_offer_id=(
                                provider_attempt.idempotency_key
                                if provider_attempt is not None
                                else None
                            ),
                            provider_session_reference_present=bool(
                                provider_session
                                and provider_session.provider_session_reference
                            ),
                        )

        return ExecutionStatusSources(
            command=CommandStatusSource(
                command_id=command.id,
                ecid=command.ecid,
                approval_state=command.approval_state,
                command_updated_at=command.updated_at,
            ),
            execution=(
                None
                if execution is None
                else ExecutionStatusSource(
                    execution_id=execution.id,
                    state=execution.state,
                    status=execution.status,
                    requested_at=execution.requested_at,
                    started_at=execution.started_at,
                    finished_at=execution.finished_at,
                    updated_at=execution.updated_at,
                    failure_classification=execution.failure_classification,
                    validation_available=bool(execution.validation_summary),
                    evidence_available=bool(execution.evidence_summary),
                    output_reference_count=len(execution.output_references),
                )
            ),
            lease=(
                None
                if lease is None
                else LeaseStatusSource(
                    lease_id=lease.id,
                    worker_id=lease.worker_id,
                    status=lease.status,
                    started_at=lease.started_at,
                    expires_at=lease.expires_at,
                    released_at=lease.released_at,
                )
            ),
            heartbeat=(
                None
                if heartbeat is None
                else HeartbeatStatusSource(
                    health=heartbeat.health,
                    last_seen=heartbeat.last_seen,
                )
            ),
            transport_session=(
                None
                if transport_session is None
                else TransportSessionStatusSource(
                    state=transport_session.state,
                    established_at=transport_session.established_at,
                    expires_at=transport_session.expires_at,
                    last_message_at=await session.scalar(
                        select(WorkerTransportReceipt.accepted_at)
                        .where(
                            WorkerTransportReceipt.company_id == company_id,
                            WorkerTransportReceipt.session_id == transport_session.id,
                        )
                        .order_by(
                            WorkerTransportReceipt.accepted_at.desc(),
                            WorkerTransportReceipt.message_id.desc(),
                        )
                        .limit(1)
                    ),
                )
            ),
            result=(
                None
                if result is None
                else ResultStatusSource(
                    status=result.status,
                    failure_classification=result.failure_classification,
                    validation_available=bool(result.validation_summary),
                    evidence_available=bool(result.evidence_summary),
                    output_reference_count=len(result.output_references),
                    created_at=result.created_at,
                )
            ),
            supervisor=supervisor_source,
        )
