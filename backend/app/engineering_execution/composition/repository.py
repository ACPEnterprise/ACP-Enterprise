from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_control.models import EngineeringCommand
from app.engineering_execution.composition.contracts import (
    CompositionIntegrityEvidence,
    CompositionReceiptStatus,
    CompositionState,
    ProviderAttemptState,
    ProviderProgressPhase,
    ProviderResultDisposition,
    ProviderResultStatus,
)
from app.engineering_execution.composition.models import (
    CompositionReceipt,
    ExecutionComposition,
    NormalizedProviderResult,
    ProviderExecutionAttempt,
    ProviderProgressEvent,
)
from app.engineering_execution.composition.records import (
    AppendProviderProgress,
    CompositionBundle,
    CompositionReceiptRecord,
    CreateExecutionComposition,
    ExecutionCompositionRecord,
    NormalizedProviderResultRecord,
    PrepareProviderAttempt,
    ProviderExecutionAttemptRecord,
    ProviderProgressEventRecord,
    StoreProviderResult,
)
from app.engineering_execution.models import EngineeringExecution
from app.worker_control.models import EngineeringWorker, WorkerLease


@dataclass(frozen=True)
class CompositionSource:
    company_id: UUID
    command_id: UUID
    execution_id: UUID
    execution_state: str
    execution_instruction_digest: str
    command_approval_state: str
    command_expires_at: datetime
    command_instruction_digest: str
    command_request_digest: str
    repository_key: str
    expected_branch: str
    expected_head: str
    requested_code_changes: bool
    worker_id: UUID
    worker_state: str
    worker_provider_identifier: str
    worker_capabilities: tuple[str, ...]
    lease_id: UUID
    lease_execution_id: UUID
    lease_worker_id: UUID
    lease_capability: str
    lease_state: str
    lease_expires_at: datetime


class ExecutionCompositionRepository:
    @staticmethod
    async def load_source_for_update(
        session: AsyncSession,
        *,
        company_id: UUID,
        execution_id: UUID,
        lease_id: UUID,
    ) -> CompositionSource | None:
        """Lock authoritative rows in execution, command, worker, lease order."""
        execution = await session.scalar(
            select(EngineeringExecution)
            .where(
                EngineeringExecution.company_id == company_id,
                EngineeringExecution.id == execution_id,
            )
            .with_for_update()
        )
        if execution is None:
            return None
        command = await session.scalar(
            select(EngineeringCommand)
            .where(
                EngineeringCommand.company_id == company_id,
                EngineeringCommand.id == execution.command_id,
            )
            .with_for_update()
        )
        lease = await session.scalar(
            select(WorkerLease).where(
                WorkerLease.company_id == company_id,
                WorkerLease.id == lease_id,
            )
        )
        if command is None or lease is None:
            return None
        worker = await session.scalar(
            select(EngineeringWorker)
            .where(
                EngineeringWorker.company_id == company_id,
                EngineeringWorker.id == lease.worker_id,
            )
            .with_for_update()
        )
        if worker is None:
            return None
        locked_lease = await session.scalar(
            select(WorkerLease)
            .where(
                WorkerLease.company_id == company_id,
                WorkerLease.id == lease_id,
            )
            .with_for_update()
        )
        if locked_lease is None:
            return None
        return CompositionSource(
            company_id=company_id,
            command_id=command.id,
            execution_id=execution.id,
            execution_state=execution.state,
            execution_instruction_digest=execution.instruction_digest,
            command_approval_state=command.approval_state,
            command_expires_at=command.expires_at,
            command_instruction_digest=command.instruction_digest,
            command_request_digest=command.request_digest,
            repository_key=command.repository_key,
            expected_branch=command.expected_branch,
            expected_head=command.expected_head,
            requested_code_changes=command.requested_code_changes,
            worker_id=worker.id,
            worker_state=worker.lifecycle_state,
            worker_provider_identifier=worker.provider_identifier,
            worker_capabilities=tuple(worker.capabilities),
            lease_id=locked_lease.id,
            lease_execution_id=locked_lease.execution_id,
            lease_worker_id=locked_lease.worker_id,
            lease_capability=locked_lease.capability_required,
            lease_state=locked_lease.status,
            lease_expires_at=locked_lease.expires_at,
        )

    @staticmethod
    async def get_bundle(
        session: AsyncSession,
        *,
        company_id: UUID,
        execution_id: UUID,
        lease_id: UUID,
    ) -> CompositionBundle | None:
        entity = await session.scalar(
            select(ExecutionComposition).where(
                ExecutionComposition.company_id == company_id,
                ExecutionComposition.execution_id == execution_id,
                ExecutionComposition.lease_id == lease_id,
            )
        )
        if entity is None:
            return None
        receipt = await session.scalar(
            select(CompositionReceipt).where(
                CompositionReceipt.company_id == company_id,
                CompositionReceipt.composition_id == entity.id,
            )
        )
        if receipt is None:
            raise ValueError("Composition receipt invariant is broken.")
        return CompositionBundle(_composition_record(entity), _receipt_record(receipt))

    @staticmethod
    async def create_bundle(
        session: AsyncSession,
        *,
        composition: CreateExecutionComposition,
        integrity: CompositionIntegrityEvidence,
    ) -> CompositionBundle:
        entity = ExecutionComposition(
            company_id=composition.company_id,
            command_id=composition.command_id,
            execution_id=composition.execution_id,
            worker_id=composition.worker_id,
            lease_id=composition.lease_id,
            provider_identifier=composition.provider_identifier,
            required_capabilities=list(composition.required_capabilities),
            effective_capabilities=list(composition.effective_capabilities),
            approved_code_changes=composition.approved_code_changes,
            repository_key=composition.repository_key,
            expected_branch=composition.expected_branch,
            expected_head=composition.expected_head,
            instruction_digest=composition.instruction_digest,
            request_digest=composition.request_digest,
            expires_at=composition.expires_at,
            composition_digest=composition.composition_digest,
            state=CompositionState.CREATED.value,
            version=1,
            created_at=composition.created_at,
            updated_at=composition.created_at,
        )
        session.add(entity)
        await session.flush()
        receipt = CompositionReceipt(
            composition_id=entity.id,
            company_id=entity.company_id,
            execution_id=entity.execution_id,
            worker_id=entity.worker_id,
            lease_id=entity.lease_id,
            provider_identifier=entity.provider_identifier,
            instruction_digest=entity.instruction_digest,
            request_digest=entity.request_digest,
            composition_digest=entity.composition_digest,
            status=CompositionReceiptStatus.ACCEPTED.value,
            created_at=entity.created_at,
            expires_at=entity.expires_at,
            version=1,
            integrity_method=integrity.method,
            integrity_key_reference=integrity.key_reference,
            integrity_proof=integrity.proof,
        )
        session.add(receipt)
        await session.flush()
        return CompositionBundle(_composition_record(entity), _receipt_record(receipt))

    @staticmethod
    async def prepare_attempt(
        session: AsyncSession, *, attempt: PrepareProviderAttempt
    ) -> ProviderExecutionAttemptRecord:
        composition = await session.scalar(
            select(ExecutionComposition)
            .where(
                ExecutionComposition.company_id == attempt.company_id,
                ExecutionComposition.id == attempt.composition_id,
            )
            .with_for_update()
        )
        if composition is None:
            raise ValueError("Composition was not found.")
        existing = await session.scalar(
            select(ProviderExecutionAttempt).where(
                ProviderExecutionAttempt.company_id == attempt.company_id,
                ProviderExecutionAttempt.idempotency_key == attempt.idempotency_key,
            )
        )
        if existing is not None:
            return _attempt_record(existing)
        ordinal = (
            await session.scalar(
                select(func.max(ProviderExecutionAttempt.attempt_ordinal)).where(
                    ProviderExecutionAttempt.company_id == attempt.company_id,
                    ProviderExecutionAttempt.composition_id == attempt.composition_id,
                )
            )
            or 0
        ) + 1
        entity = ProviderExecutionAttempt(
            company_id=attempt.company_id,
            composition_id=attempt.composition_id,
            worker_id=attempt.worker_id,
            lease_id=attempt.lease_id,
            provider_identifier=attempt.provider_identifier,
            attempt_ordinal=ordinal,
            idempotency_key=attempt.idempotency_key,
            state=ProviderAttemptState.PREPARED.value,
            version=1,
            prepared_at=attempt.prepared_at,
            created_at=attempt.prepared_at,
            updated_at=attempt.prepared_at,
        )
        session.add(entity)
        await session.flush()
        return _attempt_record(entity)

    @staticmethod
    async def transition_attempt(
        session: AsyncSession,
        *,
        company_id: UUID,
        attempt_id: UUID,
        expected_version: int,
        from_states: tuple[ProviderAttemptState, ...],
        to_state: ProviderAttemptState,
        occurred_at: datetime,
        failure_classification: str | None = None,
    ) -> ProviderExecutionAttemptRecord | None:
        values: dict[str, object] = {
            "state": to_state.value,
            "version": expected_version + 1,
            "updated_at": occurred_at,
            "failure_classification": failure_classification,
        }
        if to_state is ProviderAttemptState.STARTING:
            values["started_at"] = occurred_at
        if to_state in {
            ProviderAttemptState.COMPLETED,
            ProviderAttemptState.FAILED,
            ProviderAttemptState.CANCELLED,
            ProviderAttemptState.TIMED_OUT,
            ProviderAttemptState.QUARANTINED,
        }:
            values["finished_at"] = occurred_at
        entity = await session.scalar(
            update(ProviderExecutionAttempt)
            .where(
                ProviderExecutionAttempt.company_id == company_id,
                ProviderExecutionAttempt.id == attempt_id,
                ProviderExecutionAttempt.version == expected_version,
                ProviderExecutionAttempt.state.in_(
                    tuple(state.value for state in from_states)
                ),
            )
            .values(**values)
            .returning(ProviderExecutionAttempt)
        )
        await session.flush()
        return None if entity is None else _attempt_record(entity)

    @staticmethod
    async def append_progress(
        session: AsyncSession, *, progress: AppendProviderProgress
    ) -> ProviderProgressEventRecord:
        attempt = await session.scalar(
            select(ProviderExecutionAttempt)
            .where(
                ProviderExecutionAttempt.company_id == progress.company_id,
                ProviderExecutionAttempt.id == progress.attempt_id,
            )
            .with_for_update()
        )
        if attempt is None:
            raise ValueError("Attempt was not found.")
        sequence = (
            await session.scalar(
                select(func.max(ProviderProgressEvent.sequence_number)).where(
                    ProviderProgressEvent.company_id == progress.company_id,
                    ProviderProgressEvent.attempt_id == progress.attempt_id,
                )
            )
            or 0
        ) + 1
        entity = ProviderProgressEvent(
            company_id=progress.company_id,
            attempt_id=progress.attempt_id,
            sequence_number=sequence,
            phase=progress.phase.value,
            message_code=progress.message_code,
            summary=progress.summary,
            percentage=progress.percentage,
            created_at=progress.created_at,
        )
        session.add(entity)
        await session.flush()
        return _progress_record(entity)

    @staticmethod
    async def store_result(
        session: AsyncSession, *, result: StoreProviderResult
    ) -> NormalizedProviderResultRecord:
        entity = NormalizedProviderResult(
            company_id=result.company_id,
            attempt_id=result.attempt_id,
            composition_id=result.composition_id,
            status=result.status.value,
            evidence_summary=result.evidence_summary,
            validation_summary=result.validation_summary,
            output_references=list(result.output_references),
            failure_classification=result.failure_classification,
            repository_mutated=False,
            received_at=result.received_at,
            disposition=result.disposition.value,
            disposition_reason=result.disposition_reason,
            created_at=result.received_at,
        )
        session.add(entity)
        await session.flush()
        return _result_record(entity)

    @staticmethod
    async def get_attempt_for_update(
        session: AsyncSession, *, company_id: UUID, attempt_id: UUID
    ) -> ProviderExecutionAttemptRecord | None:
        entity = await session.scalar(
            select(ProviderExecutionAttempt)
            .where(
                ProviderExecutionAttempt.company_id == company_id,
                ProviderExecutionAttempt.id == attempt_id,
            )
            .with_for_update()
        )
        return None if entity is None else _attempt_record(entity)

    @staticmethod
    async def get_composition(
        session: AsyncSession, *, company_id: UUID, composition_id: UUID
    ) -> ExecutionCompositionRecord | None:
        entity = await session.scalar(
            select(ExecutionComposition).where(
                ExecutionComposition.company_id == company_id,
                ExecutionComposition.id == composition_id,
            )
        )
        return None if entity is None else _composition_record(entity)


def _composition_record(entity: ExecutionComposition) -> ExecutionCompositionRecord:
    return ExecutionCompositionRecord(
        id=entity.id,
        company_id=entity.company_id,
        command_id=entity.command_id,
        execution_id=entity.execution_id,
        worker_id=entity.worker_id,
        lease_id=entity.lease_id,
        provider_identifier=entity.provider_identifier,
        required_capabilities=tuple(entity.required_capabilities),
        effective_capabilities=tuple(entity.effective_capabilities),
        approved_code_changes=entity.approved_code_changes,
        repository_key=entity.repository_key,
        expected_branch=entity.expected_branch,
        expected_head=entity.expected_head,
        instruction_digest=entity.instruction_digest,
        request_digest=entity.request_digest,
        expires_at=entity.expires_at,
        composition_digest=entity.composition_digest,
        state=CompositionState(entity.state),
        version=entity.version,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def _receipt_record(entity: CompositionReceipt) -> CompositionReceiptRecord:
    return CompositionReceiptRecord(
        id=entity.id,
        composition_id=entity.composition_id,
        company_id=entity.company_id,
        execution_id=entity.execution_id,
        worker_id=entity.worker_id,
        lease_id=entity.lease_id,
        provider_identifier=entity.provider_identifier,
        instruction_digest=entity.instruction_digest,
        request_digest=entity.request_digest,
        composition_digest=entity.composition_digest,
        status=CompositionReceiptStatus(entity.status),
        created_at=entity.created_at,
        expires_at=entity.expires_at,
        version=entity.version,
        integrity=CompositionIntegrityEvidence(
            method=entity.integrity_method,
            key_reference=entity.integrity_key_reference,
            proof=entity.integrity_proof,
        ),
    )


def _attempt_record(entity: ProviderExecutionAttempt) -> ProviderExecutionAttemptRecord:
    return ProviderExecutionAttemptRecord(
        id=entity.id,
        company_id=entity.company_id,
        composition_id=entity.composition_id,
        worker_id=entity.worker_id,
        lease_id=entity.lease_id,
        provider_identifier=entity.provider_identifier,
        attempt_ordinal=entity.attempt_ordinal,
        idempotency_key=entity.idempotency_key,
        state=ProviderAttemptState(entity.state),
        version=entity.version,
        prepared_at=entity.prepared_at,
        started_at=entity.started_at,
        finished_at=entity.finished_at,
        failure_classification=entity.failure_classification,
        cancellation_requested_at=entity.cancellation_requested_at,
        cancellation_acknowledged_at=entity.cancellation_acknowledged_at,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def _progress_record(entity: ProviderProgressEvent) -> ProviderProgressEventRecord:
    return ProviderProgressEventRecord(
        id=entity.id,
        company_id=entity.company_id,
        attempt_id=entity.attempt_id,
        sequence_number=entity.sequence_number,
        phase=ProviderProgressPhase(entity.phase),
        message_code=entity.message_code,
        summary=entity.summary,
        percentage=entity.percentage,
        created_at=entity.created_at,
    )


def _result_record(entity: NormalizedProviderResult) -> NormalizedProviderResultRecord:
    return NormalizedProviderResultRecord(
        id=entity.id,
        company_id=entity.company_id,
        attempt_id=entity.attempt_id,
        composition_id=entity.composition_id,
        status=ProviderResultStatus(entity.status),
        evidence_summary=MappingProxyType(dict(entity.evidence_summary)),
        validation_summary=MappingProxyType(dict(entity.validation_summary)),
        output_references=tuple(entity.output_references),
        failure_classification=entity.failure_classification,
        repository_mutated=entity.repository_mutated,
        received_at=entity.received_at,
        disposition=ProviderResultDisposition(entity.disposition),
        disposition_reason=entity.disposition_reason,
        created_at=entity.created_at,
    )
