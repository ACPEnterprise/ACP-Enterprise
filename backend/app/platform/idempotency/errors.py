from dataclasses import dataclass
from enum import StrEnum

from fastapi import HTTPException, status

from app.platform.idempotency.reliability import (
    IdempotencyConflict,
    MutationInProgress,
    MutationReconciliationRequired,
    MutationReliabilityError,
)


class MutationErrorClass(StrEnum):
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    VALIDATION = "validation"
    STALE_VERSION = "stale_version"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    CONCURRENCY_CONFLICT = "concurrency_conflict"
    DEPENDENCY_CONFLICT = "dependency_conflict"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    INTERNAL_FAILURE = "internal_failure"


@dataclass(frozen=True, slots=True)
class SafeMutationError:
    code: MutationErrorClass
    message: str
    retryable: bool

    def detail(self) -> dict[str, object]:
        return {"code": self.code.value, "message": self.message, "retryable": self.retryable}


def reliability_http_error(error: MutationReliabilityError) -> HTTPException:
    if isinstance(error, IdempotencyConflict):
        safe = SafeMutationError(
            MutationErrorClass.IDEMPOTENCY_CONFLICT,
            "The idempotency identity conflicts with an earlier request.",
            False,
        )
        return HTTPException(status.HTTP_409_CONFLICT, detail=safe.detail())
    if isinstance(error, MutationInProgress):
        safe = SafeMutationError(
            MutationErrorClass.CONCURRENCY_CONFLICT,
            "The mutation is already in progress.",
            True,
        )
        return HTTPException(status.HTTP_409_CONFLICT, detail=safe.detail())
    if isinstance(error, MutationReconciliationRequired):
        safe = SafeMutationError(
            MutationErrorClass.RECONCILIATION_REQUIRED,
            "The authoritative outcome requires reconciliation.",
            False,
        )
        return HTTPException(status.HTTP_409_CONFLICT, detail=safe.detail())
    return HTTPException(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=SafeMutationError(
            MutationErrorClass.INTERNAL_FAILURE,
            "The mutation could not be completed safely.",
            False,
        ).detail(),
    )
