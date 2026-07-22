from uuid import UUID


class JobError(Exception):
    """Base class for controlled Jobs domain failures."""


class JobNotFoundError(JobError):
    def __init__(self, job_id: UUID) -> None:
        super().__init__(f"Job {job_id} was not found.")


class JobReferenceNotFoundError(JobError):
    pass


class AppointmentNotFoundError(JobReferenceNotFoundError):
    def __init__(self, appointment_id: UUID) -> None:
        super().__init__(f"Appointment {appointment_id} was not found.")


class AppointmentAlreadyLinkedError(JobError):
    pass


class JobInvalidTransitionError(JobError):
    pass


class JobVersionConflictError(JobError):
    pass


class JobValidationError(JobError):
    pass


class JobQueryValidationError(JobError):
    pass


class JobCompletionBlockedError(JobError):
    pass


class JobCancellationBlockedError(JobError):
    pass


class JobReopeningBlockedError(JobError):
    pass
