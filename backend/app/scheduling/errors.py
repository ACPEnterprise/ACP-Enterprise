from enum import StrEnum
from uuid import UUID


class SchedulingError(Exception):
    """Base class for controlled Scheduling domain failures."""


class SchedulingNotFoundError(SchedulingError):
    def __init__(self, resource: str, resource_id: UUID) -> None:
        super().__init__(f"{resource} {resource_id} was not found.")


class SchedulingValidationFailure(StrEnum):
    GENERIC = "generic"
    INVALID_TIMEZONE = "invalid_timezone"
    MINIMUM_NOTICE = "minimum_notice"
    BOOKING_HORIZON = "booking_horizon"
    CROSS_DAY = "cross_day"
    SLOT_ALIGNMENT = "slot_alignment"
    INVALID_WINDOW = "invalid_window"


class SchedulingValidationError(SchedulingError):
    def __init__(
        self,
        message: str,
        failure: SchedulingValidationFailure = SchedulingValidationFailure.GENERIC,
    ) -> None:
        self.failure = failure
        super().__init__(message)


class SchedulingConflictError(SchedulingError):
    pass


class SchedulingCapacityFailure(StrEnum):
    CALENDAR_MISSING = "calendar_missing"
    CALENDAR_UNAVAILABLE = "calendar_unavailable"
    CALENDAR_CLOSED = "calendar_closed"
    INTERVAL_UNAVAILABLE = "interval_unavailable"
    CAPACITY_EXHAUSTED = "capacity_exhausted"


class SchedulingCapacityError(SchedulingConflictError):
    def __init__(self, failure: SchedulingCapacityFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


class SchedulingVersionConflictError(SchedulingConflictError):
    pass
