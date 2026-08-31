from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.idempotency.contracts import IdempotencyIdentity
from app.platform.idempotency.models import MutationReceipt

T = TypeVar("T")


class MutationReliabilityError(RuntimeError):
    code = "mutation_reliability_error"


class IdempotencyConflict(MutationReliabilityError):
    code = "idempotency_conflict"


class MutationInProgress(MutationReliabilityError):
    code = "mutation_in_progress"


class MutationReconciliationRequired(MutationReliabilityError):
    code = "reconciliation_required"


class RetentionClass(StrEnum):
    TRANSPORT = "transport"
    OPERATIONAL = "operational"
    FINANCIAL_AUDIT = "financial_audit"


class MutationDisposition(StrEnum):
    EXECUTED = "executed"
    REPLAYED = "replayed"


@dataclass(frozen=True, slots=True)
class AuthoritativeOutcome(Generic[T]):
    value: T
    result_type: str
    result_id: UUID
    response_status: int


@dataclass(frozen=True, slots=True)
class MutationResult(Generic[T]):
    value: T
    disposition: MutationDisposition
    receipt_id: UUID

    def safe_diagnostic(self) -> dict[str, str]:
        return {
            "schema_version": "mutation-reliability-diagnostic/v1",
            "disposition": self.disposition.value,
            "receipt_id": str(self.receipt_id),
        }


Mutation = Callable[[], Awaitable[AuthoritativeOutcome[T]]]
Recovery = Callable[[UUID], Awaitable[T | None]]


class MutationReliabilityService:
    """Compose a domain mutation and durable replay receipt in one transaction."""

    async def execute(
        self,
        session: AsyncSession,
        *,
        identity: IdempotencyIdentity,
        actor_user_id: UUID,
        request_digest: str,
        retention_class: RetentionClass,
        mutate: Mutation[T],
        recover: Recovery[T],
        expires_at: datetime | None = None,
    ) -> MutationResult[T]:
        lock_identity = ":".join(map(str, identity.tenant_key))
        lock_key = int.from_bytes(
            hashlib.sha256(lock_identity.encode()).digest()[:8], "big", signed=True
        )
        async with session.begin():
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key}
            )
            receipt = await session.scalar(
                select(MutationReceipt)
                .where(
                    MutationReceipt.company_id == identity.company_id,
                    MutationReceipt.operation == identity.operation,
                    MutationReceipt.idempotency_key == identity.idempotency_key,
                )
                .with_for_update()
            )
            if receipt is not None:
                if receipt.branch_id != identity.branch_id:
                    raise IdempotencyConflict(
                        "idempotency identity conflicts with Branch authority"
                    )
                if receipt.request_digest != request_digest:
                    raise IdempotencyConflict(
                        "idempotency identity conflicts with the original request"
                    )
                if receipt.state == "reconciliation_required":
                    raise MutationReconciliationRequired(
                        "authoritative outcome requires reconciliation"
                    )
                if receipt.state != "completed" or receipt.result_id is None:
                    raise MutationInProgress("mutation outcome is not yet recoverable")
                value = await recover(receipt.result_id)
                if value is None:
                    receipt.state = "reconciliation_required"
                    raise MutationReconciliationRequired(
                        "authoritative result referenced by receipt is unavailable"
                    )
                return MutationResult(value, MutationDisposition.REPLAYED, receipt.id)

            receipt = MutationReceipt(
                company_id=identity.company_id,
                branch_id=identity.branch_id,
                actor_user_id=actor_user_id,
                operation=identity.operation,
                idempotency_key=identity.idempotency_key,
                request_digest=request_digest,
                state="in_progress",
                retention_class=retention_class.value,
                expires_at=expires_at,
            )
            session.add(receipt)
            await session.flush()
            outcome = await mutate()
            receipt.state = "completed"
            receipt.result_type = outcome.result_type
            receipt.result_id = outcome.result_id
            receipt.response_status = outcome.response_status
            receipt.completed_at = datetime.now(timezone.utc)
            await session.flush()
            return MutationResult(
                outcome.value, MutationDisposition.EXECUTED, receipt.id
            )


mutation_reliability_service = MutationReliabilityService()
