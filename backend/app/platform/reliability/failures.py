from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class ClientRecovery(StrEnum):
    RETRY_SAFE = "RETRY_SAFE"
    RETRY_AFTER_REFRESH = "RETRY_AFTER_REFRESH"
    USER_CORRECTION_REQUIRED = "USER_CORRECTION_REQUIRED"
    OWNER_ADMIN_ACTION_REQUIRED = "OWNER_ADMIN_ACTION_REQUIRED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    TEMPORARILY_UNAVAILABLE = "TEMPORARILY_UNAVAILABLE"
    TERMINAL_FAILURE = "TERMINAL_FAILURE"


class FailureCode(StrEnum):
    AUTHENTICATION_REQUIRED = "authentication_required"
    FORBIDDEN = "forbidden"
    VALIDATION = "validation"
    STALE_VERSION = "stale_version"
    CONCURRENCY_CONFLICT = "concurrency_conflict"
    SCHEDULING_CALENDAR_MISSING = "scheduling_calendar_missing"
    SCHEDULING_CALENDAR_UNAVAILABLE = "scheduling_calendar_unavailable"
    SCHEDULING_CALENDAR_CLOSED = "scheduling_calendar_closed"
    SCHEDULING_INTERVAL_UNAVAILABLE = "scheduling_interval_unavailable"
    SCHEDULING_CAPACITY_EXHAUSTED = "scheduling_capacity_exhausted"
    SCHEDULING_INVALID_TIMEZONE = "scheduling_invalid_timezone"
    SCHEDULING_MINIMUM_NOTICE = "scheduling_minimum_notice"
    SCHEDULING_BOOKING_HORIZON = "scheduling_booking_horizon"
    SCHEDULING_CROSS_DAY = "scheduling_cross_day"
    SCHEDULING_SLOT_ALIGNMENT = "scheduling_slot_alignment"
    SCHEDULING_INVALID_WINDOW = "scheduling_invalid_window"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_UNCERTAIN = "provider_uncertain"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    NOT_FOUND = "not_found"
    RESOURCE_STATE_CONFLICT = "resource_state_conflict"
    RATE_LIMITED = "rate_limited"
    INTERNAL_FAILURE = "internal_failure"


@dataclass(frozen=True, slots=True)
class SafeFailure:
    code: FailureCode
    message: str
    recovery: ClientRecovery
    correlation_id: UUID | None = None

    def detail(self) -> dict[str, str | None]:
        return {
            "code": self.code.value,
            "message": self.message,
            "recovery": self.recovery.value,
            "correlation_id": str(self.correlation_id) if self.correlation_id else None,
        }
