from datetime import datetime
from types import MappingProxyType
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.worker_control.contracts import (
    WorkerCapability,
    WorkerFailureClassification,
    WorkerHealth,
    WorkerLeaseStatus,
    WorkerLifecycleState,
    WorkerResultStatus,
)
from app.worker_control.models import (
    EngineeringWorker,
    WorkerHeartbeat,
    WorkerLease,
    WorkerResult,
)
from app.worker_control.records import (
    RegisterWorker,
    WorkerHeartbeatRecord,
    WorkerIdentity,
    WorkerLeaseRecord,
    WorkerResultRecord,
)


class WorkerControlRepository:
    @staticmethod
    def snapshot_worker(worker: EngineeringWorker) -> WorkerIdentity:
        return _worker_record(worker)

    @staticmethod
    async def create_worker(
        session: AsyncSession, *, worker: RegisterWorker
    ) -> WorkerIdentity:
        entity = EngineeringWorker(
            company_id=worker.company_id,
            provider_identifier=worker.provider_identifier,
            name=worker.name,
            worker_version=worker.worker_version,
            capabilities=[capability.value for capability in worker.capabilities],
            lifecycle_state=WorkerLifecycleState.REGISTERED.value,
            registered_by_user_id=worker.registered_by_user_id,
            registered_at=worker.registered_at,
            version=1,
            created_at=worker.registered_at,
            updated_at=worker.registered_at,
        )
        session.add(entity)
        await session.flush()
        return _worker_record(entity)

    @staticmethod
    async def get_worker(
        session: AsyncSession, *, company_id: UUID, worker_id: UUID
    ) -> WorkerIdentity | None:
        entity = await session.scalar(
            select(EngineeringWorker).where(
                EngineeringWorker.company_id == company_id,
                EngineeringWorker.id == worker_id,
            )
        )
        return None if entity is None else _worker_record(entity)

    @staticmethod
    async def get_worker_for_update(
        session: AsyncSession, *, company_id: UUID, worker_id: UUID
    ) -> EngineeringWorker | None:
        return await session.scalar(
            select(EngineeringWorker)
            .where(
                EngineeringWorker.company_id == company_id,
                EngineeringWorker.id == worker_id,
            )
            .with_for_update()
        )

    @staticmethod
    async def list_workers(
        session: AsyncSession, *, company_id: UUID, limit: int = 100
    ) -> tuple[WorkerIdentity, ...]:
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")
        entities = (
            await session.scalars(
                select(EngineeringWorker)
                .where(EngineeringWorker.company_id == company_id)
                .order_by(
                    EngineeringWorker.registered_at.desc(),
                    EngineeringWorker.id.desc(),
                )
                .limit(limit)
            )
        ).all()
        return tuple(_worker_record(entity) for entity in entities)

    @staticmethod
    async def record_heartbeat(
        session: AsyncSession,
        *,
        worker: EngineeringWorker,
        health: WorkerHealth,
        occurred_at: datetime,
    ) -> tuple[WorkerIdentity, WorkerHeartbeatRecord]:
        worker.last_heartbeat_at = occurred_at
        worker.version += 1
        worker.updated_at = occurred_at
        if worker.lifecycle_state in {
            WorkerLifecycleState.REGISTERED.value,
            WorkerLifecycleState.OFFLINE.value,
        }:
            worker.lifecycle_state = WorkerLifecycleState.AVAILABLE.value
        heartbeat = WorkerHeartbeat(
            company_id=worker.company_id,
            worker_id=worker.id,
            last_seen=occurred_at,
            health=health.value,
            worker_version=worker.version,
            created_at=occurred_at,
        )
        session.add(heartbeat)
        await session.flush()
        return _worker_record(worker), _heartbeat_record(heartbeat)

    @staticmethod
    async def set_worker_state(
        session: AsyncSession,
        *,
        worker: EngineeringWorker,
        lifecycle_state: WorkerLifecycleState,
        occurred_at: datetime,
    ) -> WorkerIdentity:
        worker.lifecycle_state = lifecycle_state.value
        worker.version += 1
        worker.updated_at = occurred_at
        await session.flush()
        return _worker_record(worker)

    @staticmethod
    async def create_lease(
        session: AsyncSession,
        *,
        worker: EngineeringWorker,
        execution_id: UUID,
        capability: WorkerCapability,
        started_at: datetime,
        expires_at: datetime,
    ) -> WorkerLeaseRecord:
        entity = WorkerLease(
            company_id=worker.company_id,
            worker_id=worker.id,
            execution_id=execution_id,
            capability_required=capability.value,
            started_at=started_at,
            expires_at=expires_at,
            status=WorkerLeaseStatus.ACTIVE.value,
            version=1,
            created_at=started_at,
            updated_at=started_at,
        )
        worker.lifecycle_state = WorkerLifecycleState.LEASED.value
        worker.version += 1
        worker.updated_at = started_at
        session.add(entity)
        await session.flush()
        return _lease_record(entity)

    @staticmethod
    async def get_lease_for_update(
        session: AsyncSession, *, company_id: UUID, lease_id: UUID
    ) -> WorkerLease | None:
        return await session.scalar(
            select(WorkerLease)
            .where(
                WorkerLease.company_id == company_id,
                WorkerLease.id == lease_id,
            )
            .with_for_update()
        )

    @staticmethod
    async def renew_lease(
        session: AsyncSession,
        *,
        lease: WorkerLease,
        expires_at: datetime,
        occurred_at: datetime,
    ) -> WorkerLeaseRecord:
        lease.expires_at = expires_at
        lease.version += 1
        lease.updated_at = occurred_at
        await session.flush()
        return _lease_record(lease)

    @staticmethod
    async def finish_lease(
        session: AsyncSession,
        *,
        lease: WorkerLease,
        worker: EngineeringWorker,
        status: WorkerLeaseStatus,
        occurred_at: datetime,
    ) -> WorkerLeaseRecord:
        lease.status = status.value
        lease.released_at = occurred_at
        lease.version += 1
        lease.updated_at = occurred_at
        worker.lifecycle_state = WorkerLifecycleState.AVAILABLE.value
        worker.version += 1
        worker.updated_at = occurred_at
        await session.flush()
        return _lease_record(lease)

    @staticmethod
    async def create_result(
        session: AsyncSession,
        *,
        lease: WorkerLease,
        status: WorkerResultStatus,
        validation_summary: dict[str, object],
        evidence_summary: dict[str, object],
        output_references: tuple[str, ...],
        failure_classification: WorkerFailureClassification,
        correlation_id: UUID,
        occurred_at: datetime,
    ) -> WorkerResultRecord:
        entity = WorkerResult(
            company_id=lease.company_id,
            lease_id=lease.id,
            worker_id=lease.worker_id,
            execution_id=lease.execution_id,
            status=status.value,
            validation_summary=validation_summary,
            evidence_summary=evidence_summary,
            output_references=list(output_references),
            failure_classification=failure_classification.value,
            correlation_id=correlation_id,
            created_at=occurred_at,
        )
        session.add(entity)
        await session.flush()
        return _result_record(entity)


def _worker_record(entity: EngineeringWorker) -> WorkerIdentity:
    return WorkerIdentity(
        id=entity.id,
        company_id=entity.company_id,
        provider_identifier=entity.provider_identifier,
        name=entity.name,
        worker_version=entity.worker_version,
        capabilities=tuple(WorkerCapability(value) for value in entity.capabilities),
        registered_at=entity.registered_at,
        last_heartbeat_at=entity.last_heartbeat_at,
        lifecycle_state=WorkerLifecycleState(entity.lifecycle_state),
        version=entity.version,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def _lease_record(entity: WorkerLease) -> WorkerLeaseRecord:
    return WorkerLeaseRecord(
        id=entity.id,
        company_id=entity.company_id,
        worker_id=entity.worker_id,
        execution_id=entity.execution_id,
        capability_required=WorkerCapability(entity.capability_required),
        started_at=entity.started_at,
        expires_at=entity.expires_at,
        released_at=entity.released_at,
        status=WorkerLeaseStatus(entity.status),
        version=entity.version,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def _heartbeat_record(entity: WorkerHeartbeat) -> WorkerHeartbeatRecord:
    return WorkerHeartbeatRecord(
        id=entity.id,
        company_id=entity.company_id,
        worker_id=entity.worker_id,
        last_seen=entity.last_seen,
        health=WorkerHealth(entity.health),
        worker_version=entity.worker_version,
        created_at=entity.created_at,
    )


def _result_record(entity: WorkerResult) -> WorkerResultRecord:
    return WorkerResultRecord(
        id=entity.id,
        company_id=entity.company_id,
        lease_id=entity.lease_id,
        worker_id=entity.worker_id,
        execution_id=entity.execution_id,
        status=WorkerResultStatus(entity.status),
        validation_summary=MappingProxyType(dict(entity.validation_summary)),
        evidence_summary=MappingProxyType(dict(entity.evidence_summary)),
        output_references=tuple(entity.output_references),
        failure_classification=WorkerFailureClassification(
            entity.failure_classification
        ),
        correlation_id=entity.correlation_id,
        created_at=entity.created_at,
    )
