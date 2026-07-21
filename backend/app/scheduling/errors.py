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


class SchedulingCapacityError(SchedulingConflictError):
    pass


class SchedulingVersionConflictError(SchedulingConflictError):
    pass
