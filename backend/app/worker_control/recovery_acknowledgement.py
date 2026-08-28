import hashlib
import json
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.engineering_execution.controlled.models import (
    ControlledExecutionOfferModel,
    ControlledExecutionResultModel,
)
from app.engineering_execution.models import EngineeringExecution
from app.platform.audit.service import AuditEntry, audit_service
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import WorkerControlPermission
from app.platform.permissions.dependencies import require_permission
from app.worker_control.models import (
    EngineeringWorker,
    WorkerLease,
    WorkerRecoveryAcknowledgement,
)
from app.worker_control.transport.http.dependencies import (
    WorkerHttpIdentity,
    get_worker_http_identity,
)


class RecoveryAcknowledgementError(ValueError):
    pass


class RecoveryAcknowledgementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    worker_id: UUID
    command_id: UUID
    execution_id: UUID
    offer_id: UUID
    lease_id: UUID
    journal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reconciliation_reason: str = Field(min_length=1, max_length=200)
    acknowledgement_reason: str = Field(min_length=1, max_length=500)
    acknowledgement_version: int = Field(default=1, ge=1)


class RecoveryAcknowledgementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    worker_id: UUID
    command_id: UUID
    execution_id: UUID
    offer_id: UUID
    lease_id: UUID
    journal_digest: str
    audit_digest: str
    acknowledgement_version: int
    historical_execution_unresolved: bool
    acknowledged_at: datetime
    applied_at: datetime | None
    active_block_released: bool


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class RecoveryAcknowledgementService:
    async def acknowledge(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        request: RecoveryAcknowledgementRequest,
    ) -> WorkerRecoveryAcknowledgement:
        company_id = context.company.id
        existing = await session.scalar(
            select(WorkerRecoveryAcknowledgement).where(
                WorkerRecoveryAcknowledgement.company_id == company_id,
                WorkerRecoveryAcknowledgement.worker_id == request.worker_id,
                WorkerRecoveryAcknowledgement.journal_digest == request.journal_digest,
            )
        )
        identity = (
            request.command_id,
            request.execution_id,
            request.offer_id,
            request.lease_id,
            request.reconciliation_reason,
            request.acknowledgement_reason,
            request.acknowledgement_version,
        )
        if existing is not None:
            persisted = (
                existing.command_id,
                existing.execution_id,
                existing.offer_id,
                existing.lease_id,
                existing.reconciliation_reason,
                existing.acknowledgement_reason,
                existing.acknowledgement_version,
            )
            if persisted != identity:
                raise RecoveryAcknowledgementError(
                    "Recovery acknowledgement conflicts with immutable evidence."
                )
            return existing

        worker = await session.scalar(
            select(EngineeringWorker).where(
                EngineeringWorker.company_id == company_id,
                EngineeringWorker.id == request.worker_id,
            )
        )
        execution = await session.scalar(
            select(EngineeringExecution).where(
                EngineeringExecution.company_id == company_id,
                EngineeringExecution.id == request.execution_id,
                EngineeringExecution.command_id == request.command_id,
            )
        )
        offer = await session.scalar(
            select(ControlledExecutionOfferModel).where(
                ControlledExecutionOfferModel.company_id == company_id,
                ControlledExecutionOfferModel.id == request.offer_id,
                ControlledExecutionOfferModel.execution_id == request.execution_id,
                ControlledExecutionOfferModel.command_id == request.command_id,
                ControlledExecutionOfferModel.worker_id == request.worker_id,
                ControlledExecutionOfferModel.lease_id == request.lease_id,
            )
        )
        lease = await session.scalar(
            select(WorkerLease).where(
                WorkerLease.company_id == company_id,
                WorkerLease.id == request.lease_id,
                WorkerLease.worker_id == request.worker_id,
                WorkerLease.execution_id == request.execution_id,
            )
        )
        if worker is None or execution is None or offer is None or lease is None:
            raise RecoveryAcknowledgementError(
                "Recovery acknowledgement lineage does not match."
            )
        if lease.status == "active" or lease.released_at is None:
            raise RecoveryAcknowledgementError(
                "An active or unreleased lease cannot be acknowledged."
            )
        active = await session.scalar(
            select(WorkerLease.id).where(
                WorkerLease.company_id == company_id,
                WorkerLease.worker_id == request.worker_id,
                WorkerLease.status == "active",
            )
        )
        if active is not None:
            raise RecoveryAcknowledgementError("Worker has another active lease.")
        if execution.evidence_summary.get("reconciliation_required") is not True:
            raise RecoveryAcknowledgementError(
                "Execution is not unresolved reconciliation evidence."
            )
        if (
            execution.evidence_summary.get("reconciliation_reason")
            != request.reconciliation_reason
        ):
            raise RecoveryAcknowledgementError(
                "Reconciliation reason does not match durable execution evidence."
            )
        result = await session.scalar(
            select(ControlledExecutionResultModel.id).where(
                ControlledExecutionResultModel.company_id == company_id,
                ControlledExecutionResultModel.execution_id == request.execution_id,
            )
        )
        if result is not None:
            raise RecoveryAcknowledgementError(
                "A deliverable controlled result exists."
            )

        now = datetime.now(timezone.utc)
        authority = {
            "permission": WorkerControlPermission.RECOVERY_ACKNOWLEDGE,
            "authorization_version": context.authorization_version,
            "credential_version": context.credential_version,
        }
        audit_digest = _digest(
            {
                "company_id": company_id,
                "worker_id": request.worker_id,
                "command_id": request.command_id,
                "execution_id": request.execution_id,
                "offer_id": request.offer_id,
                "lease_id": request.lease_id,
                "journal_digest": request.journal_digest,
                "reason": request.acknowledgement_reason,
                "operator": context.user.id,
                "acknowledged_at": now,
                "version": request.acknowledgement_version,
            }
        )
        record = WorkerRecoveryAcknowledgement(
            company_id=company_id,
            worker_id=request.worker_id,
            command_id=request.command_id,
            execution_id=request.execution_id,
            offer_id=request.offer_id,
            lease_id=request.lease_id,
            journal_digest=request.journal_digest,
            reconciliation_reason=request.reconciliation_reason,
            acknowledgement_reason=request.acknowledgement_reason,
            operator_user_id=context.user.id,
            authorization_context=authority,
            acknowledgement_version=request.acknowledgement_version,
            audit_digest=audit_digest,
            historical_execution_unresolved=True,
            acknowledged_at=now,
            active_block_released=False,
        )
        session.add(record)
        await session.flush()
        audit_service.stage(
            session,
            AuditEntry(
                action="engineering_worker.recovery_block_acknowledged",
                resource_type="engineering_worker_recovery_acknowledgement",
                actor_user_id=context.user.id,
                company_id=company_id,
                resource_id=record.id,
                reason_code="historical_outcome_remains_unresolved",
                details={
                    "worker_id": str(request.worker_id),
                    "execution_id": str(request.execution_id),
                    "lease_id": str(request.lease_id),
                    "audit_digest": audit_digest,
                },
            ),
        )
        await session.commit()
        return record

    async def pending(
        self, session: AsyncSession, *, company_id: UUID, worker_id: UUID
    ) -> tuple[WorkerRecoveryAcknowledgement, ...]:
        return tuple(
            (
                await session.scalars(
                    select(WorkerRecoveryAcknowledgement)
                    .where(
                        WorkerRecoveryAcknowledgement.company_id == company_id,
                        WorkerRecoveryAcknowledgement.worker_id == worker_id,
                        WorkerRecoveryAcknowledgement.applied_at.is_(None),
                    )
                    .order_by(WorkerRecoveryAcknowledgement.acknowledged_at)
                )
            ).all()
        )

    async def applied(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        worker_id: UUID,
        acknowledgement_id: UUID,
        local_archive_digest: str,
    ) -> WorkerRecoveryAcknowledgement:
        record = await session.scalar(
            select(WorkerRecoveryAcknowledgement)
            .where(
                WorkerRecoveryAcknowledgement.company_id == company_id,
                WorkerRecoveryAcknowledgement.worker_id == worker_id,
                WorkerRecoveryAcknowledgement.id == acknowledgement_id,
            )
            .with_for_update()
        )
        if record is None:
            raise RecoveryAcknowledgementError(
                "Recovery acknowledgement was not found."
            )
        if record.applied_at is not None:
            if record.local_archive_digest != local_archive_digest:
                raise RecoveryAcknowledgementError(
                    "Applied acknowledgement digest conflicts."
                )
            return record
        record.local_archive_digest = local_archive_digest
        record.applied_at = datetime.now(timezone.utc)
        record.active_block_released = True
        audit_service.stage(
            session,
            AuditEntry(
                action="engineering_worker.recovery_block_released",
                resource_type="engineering_worker_recovery_acknowledgement",
                company_id=company_id,
                resource_id=record.id,
                reason_code="local_evidence_archived",
                details={
                    "worker_id": str(worker_id),
                    "execution_id": str(record.execution_id),
                    "archive_digest": local_archive_digest,
                },
            ),
        )
        await session.commit()
        return record


service = RecoveryAcknowledgementService()
router = APIRouter(
    prefix="/api/v1/engineering/worker-recovery", tags=["Engineering Worker Recovery"]
)
worker_router = APIRouter(
    prefix="/api/v1/worker-transport", tags=["Authenticated Worker Transport"]
)
Database = Annotated[AsyncSession, Depends(get_database_session)]
RecoveryContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(WorkerControlPermission.RECOVERY_ACKNOWLEDGE)),
]
WorkerIdentity = Annotated[WorkerHttpIdentity, Depends(get_worker_http_identity)]


@router.post("/acknowledgements", response_model=RecoveryAcknowledgementResponse)
async def acknowledge_recovery(
    data: RecoveryAcknowledgementRequest,
    context: RecoveryContext,
    session: Database,
) -> WorkerRecoveryAcknowledgement:
    try:
        return await service.acknowledge(session, context=context, request=data)
    except RecoveryAcknowledgementError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "worker_recovery_acknowledgement_rejected",
                "message": str(error),
            },
        ) from error


class AppliedRequest(BaseModel):
    local_archive_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


@worker_router.get(
    "/sessions/{session_id}/recovery-acknowledgements",
    response_model=tuple[RecoveryAcknowledgementResponse, ...],
)
async def pending_recovery_acknowledgements(
    session_id: UUID,
    identity: WorkerIdentity,
    session: Database,
) -> tuple[WorkerRecoveryAcknowledgement, ...]:
    if session_id != identity.session_id:
        raise HTTPException(
            status_code=401, detail={"code": "worker_authentication_required"}
        )
    return await service.pending(
        session,
        company_id=identity.context.company_id,
        worker_id=identity.context.worker_id,
    )


@worker_router.post(
    "/recovery-acknowledgements/{acknowledgement_id}/applied",
    response_model=RecoveryAcknowledgementResponse,
)
async def recovery_acknowledgement_applied(
    acknowledgement_id: UUID,
    data: AppliedRequest,
    identity: WorkerIdentity,
    session: Database,
) -> WorkerRecoveryAcknowledgement:
    try:
        return await service.applied(
            session,
            company_id=identity.context.company_id,
            worker_id=identity.context.worker_id,
            acknowledgement_id=acknowledgement_id,
            local_archive_digest=data.local_archive_digest,
        )
    except RecoveryAcknowledgementError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "worker_recovery_acknowledgement_rejected",
                "message": str(error),
            },
        ) from error
