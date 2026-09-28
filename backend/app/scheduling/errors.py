from enum import StrEnum
from uuid import UUID


class SchedulingError(Exception):
    """Base class for controlled Scheduling domain failures."""


class SchedulingNotFoundError(SchedulingError):
    def __init__(self, resource: str, resource_id: UUID) -> None:
        super().__init__(f"{resource} {resource_id} was not found.")


class SchedulingValidationError(SchedulingError):
    pass


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
