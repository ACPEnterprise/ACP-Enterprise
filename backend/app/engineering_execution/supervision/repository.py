from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_execution.composition.models import (
    ExecutionComposition,
    ProviderExecutionAttempt,
)
from app.execution_providers.contracts import ProviderCapability
from app.worker_control.models import EngineeringWorker, WorkerLease

from .contracts import ProviderSessionState, RecoveryItem, SupervisorState
from .models import LiveClientSupervisorModel, ProviderSessionModel
from .records import LiveClientSupervisorRecord, ProviderSessionRecord


class SupervisionRepository:
    @staticmethod
    async def get_or_create_supervisor(
        session: AsyncSession,
        *,
        company_id: UUID,
        worker_id: UUID,
        now: datetime,
    ) -> LiveClientSupervisorRecord:
        worker = await session.scalar(
            select(EngineeringWorker)
            .where(
                EngineeringWorker.company_id == company_id,
                EngineeringWorker.id == worker_id,
            )
            .with_for_update()
        )
        if worker is None:
            raise ValueError("worker not found")
        entity = await session.scalar(
            select(LiveClientSupervisorModel)
            .where(
                LiveClientSupervisorModel.company_id == company_id,
                LiveClientSupervisorModel.worker_id == worker_id,
            )
            .with_for_update()
        )
        if entity is None:
            entity = LiveClientSupervisorModel(
                company_id=company_id,
                worker_id=worker_id,
                state=SupervisorState.STOPPED.value,
                version=1,
                last_transition_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(entity)
            await session.flush()
        return _supervisor(entity)

    @staticmethod
    async def transition_supervisor(
        session: AsyncSession,
        *,
        company_id: UUID,
        supervisor_id: UUID,
        expected_version: int,
        from_states: tuple[SupervisorState, ...],
        to_state: SupervisorState,
        now: datetime,
        failure_classification: str | None = None,
    ) -> LiveClientSupervisorRecord | None:
        values: dict[str, object] = {
            "state": to_state.value,
            "version": expected_version + 1,
            "last_transition_at": now,
            "updated_at": now,
            "failure_classification": failure_classification,
        }
        if to_state is SupervisorState.STARTING:
            values["started_at"] = now
        if (
            to_state is SupervisorState.READY
            and SupervisorState.RECOVERING in from_states
        ):
            values["recovered_at"] = now
        entity = await session.scalar(
            update(LiveClientSupervisorModel)
            .where(
                LiveClientSupervisorModel.company_id == company_id,
                LiveClientSupervisorModel.id == supervisor_id,
                LiveClientSupervisorModel.version == expected_version,
                LiveClientSupervisorModel.state.in_(
                    tuple(state.value for state in from_states)
                ),
            )
            .values(**values)
            .returning(LiveClientSupervisorModel)
        )
        await session.flush()
        return None if entity is None else _supervisor(entity)

    @staticmethod
    async def load_session_source_for_update(
        session: AsyncSession,
        *,
        company_id: UUID,
        worker_id: UUID,
        composition_id: UUID,
        attempt_id: UUID,
    ) -> (
        tuple[
            ExecutionComposition,
            ProviderExecutionAttempt,
            WorkerLease,
            EngineeringWorker,
        ]
        | None
    ):
        composition = await session.scalar(
            select(ExecutionComposition)
            .where(
                ExecutionComposition.company_id == company_id,
                ExecutionComposition.id == composition_id,
                ExecutionComposition.worker_id == worker_id,
            )
            .with_for_update()
        )
        attempt = await session.scalar(
            select(ProviderExecutionAttempt)
            .where(
                ProviderExecutionAttempt.company_id == company_id,
                ProviderExecutionAttempt.id == attempt_id,
                ProviderExecutionAttempt.composition_id == composition_id,
                ProviderExecutionAttempt.worker_id == worker_id,
            )
            .with_for_update()
        )
        if composition is None or attempt is None:
            return None
        worker = await session.scalar(
            select(EngineeringWorker)
            .where(
                EngineeringWorker.company_id == company_id,
                EngineeringWorker.id == worker_id,
            )
            .with_for_update()
        )
        lease = await session.scalar(
            select(WorkerLease)
            .where(
                WorkerLease.company_id == company_id,
                WorkerLease.id == composition.lease_id,
                WorkerLease.worker_id == worker_id,
            )
            .with_for_update()
        )
        if worker is None or lease is None:
            return None
        return composition, attempt, lease, worker

    @staticmethod
    async def create_session(
        session: AsyncSession,
        *,
        supervisor_id: UUID,
        composition: ExecutionComposition,
        attempt: ProviderExecutionAttempt,
        effective_capabilities: tuple[ProviderCapability, ...],
        expires_at: datetime,
        now: datetime,
    ) -> ProviderSessionRecord:
        existing = await session.scalar(
            select(ProviderSessionModel)
            .where(
                ProviderSessionModel.company_id == composition.company_id,
                ProviderSessionModel.composition_id == composition.id,
                ProviderSessionModel.attempt_id == attempt.id,
            )
            .with_for_update()
        )
        if existing is not None:
            return _provider_session(existing)
        entity = ProviderSessionModel(
            company_id=composition.company_id,
            supervisor_id=supervisor_id,
            composition_id=composition.id,
            attempt_id=attempt.id,
            worker_id=composition.worker_id,
            lease_id=composition.lease_id,
            provider_identifier=composition.provider_identifier,
            effective_capabilities=[item.value for item in effective_capabilities],
            approved_code_changes=composition.approved_code_changes,
            state=ProviderSessionState.CREATED.value,
            version=1,
            created_at=now,
            expires_at=expires_at,
            updated_at=now,
        )
        session.add(entity)
        await session.flush()
        return _provider_session(entity)

    @staticmethod
    async def transition_session(
        session: AsyncSession,
        *,
        company_id: UUID,
        session_id: UUID,
        expected_version: int,
        from_states: tuple[ProviderSessionState, ...],
        to_state: ProviderSessionState,
        now: datetime,
        failure_classification: str | None = None,
    ) -> ProviderSessionRecord | None:
        values: dict[str, object] = {
            "state": to_state.value,
            "version": expected_version + 1,
            "updated_at": now,
            "failure_classification": failure_classification,
        }
        timestamp_fields = {
            ProviderSessionState.OPENING: "opening_at",
            ProviderSessionState.READY: "ready_at",
            ProviderSessionState.ACTIVE: "active_at",
            ProviderSessionState.CLOSING: "closing_at",
            ProviderSessionState.CLOSED: "closed_at",
            ProviderSessionState.EXPIRED: "closed_at",
            ProviderSessionState.FAILED: "closed_at",
            ProviderSessionState.CANCELLED: "closed_at",
        }
        field = timestamp_fields.get(to_state)
        if field:
            values[field] = now
        entity = await session.scalar(
            update(ProviderSessionModel)
            .where(
                ProviderSessionModel.company_id == company_id,
                ProviderSessionModel.id == session_id,
                ProviderSessionModel.version == expected_version,
                ProviderSessionModel.state.in_(
                    tuple(state.value for state in from_states)
                ),
            )
            .values(**values)
            .returning(ProviderSessionModel)
        )
        await session.flush()
        return None if entity is None else _provider_session(entity)

    @staticmethod
    async def recovery_items(
        session: AsyncSession,
        *,
        company_id: UUID,
        worker_id: UUID,
        now: datetime,
    ) -> tuple[RecoveryItem, ...]:
        rows = (
            await session.execute(
                select(ExecutionComposition, ProviderExecutionAttempt)
                .outerjoin(
                    ProviderExecutionAttempt,
                    (
                        ProviderExecutionAttempt.company_id
                        == ExecutionComposition.company_id
                    )
                    & (
                        ProviderExecutionAttempt.composition_id
                        == ExecutionComposition.id
                    ),
                )
                .where(
                    ExecutionComposition.company_id == company_id,
                    ExecutionComposition.worker_id == worker_id,
                    ExecutionComposition.expires_at > now,
                    ExecutionComposition.state == "created",
                )
                .order_by(ExecutionComposition.created_at, ExecutionComposition.id)
            )
        ).all()
        return tuple(
            RecoveryItem(
                composition_id=composition.id,
                attempt_id=attempt.id if attempt else None,
                composition_state=composition.state,
                attempt_state=attempt.state if attempt else None,
                cancellation_requested=bool(
                    attempt and attempt.cancellation_requested_at is not None
                ),
            )
            for composition, attempt in rows
            if attempt is None
            or attempt.state in {"prepared", "starting", "running"}
            or attempt.cancellation_requested_at is not None
        )


def _supervisor(entity: LiveClientSupervisorModel) -> LiveClientSupervisorRecord:
    return LiveClientSupervisorRecord(
        id=entity.id,
        company_id=entity.company_id,
        worker_id=entity.worker_id,
        state=SupervisorState(entity.state),
        version=entity.version,
        started_at=entity.started_at,
        recovered_at=entity.recovered_at,
        last_transition_at=entity.last_transition_at,
        failure_classification=entity.failure_classification,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def _provider_session(entity: ProviderSessionModel) -> ProviderSessionRecord:
    return ProviderSessionRecord(
        id=entity.id,
        company_id=entity.company_id,
        supervisor_id=entity.supervisor_id,
        composition_id=entity.composition_id,
        attempt_id=entity.attempt_id,
        worker_id=entity.worker_id,
        lease_id=entity.lease_id,
        provider_identifier=entity.provider_identifier,
        effective_capabilities=tuple(
            ProviderCapability(value) for value in entity.effective_capabilities
        ),
        approved_code_changes=entity.approved_code_changes,
        state=ProviderSessionState(entity.state),
        version=entity.version,
        created_at=entity.created_at,
        opening_at=entity.opening_at,
        ready_at=entity.ready_at,
        active_at=entity.active_at,
        closing_at=entity.closing_at,
        closed_at=entity.closed_at,
        expires_at=entity.expires_at,
        failure_classification=entity.failure_classification,
        updated_at=entity.updated_at,
    )
