class WorkerControlError(Exception):
    """Base class for fail-closed Worker Control errors."""


class WorkerControlPermissionError(WorkerControlError):
    pass


class WorkerAuthenticationError(WorkerControlError):
    pass


class WorkerValidationError(WorkerControlError):
    pass


class WorkerNotFoundError(WorkerControlError):
    pass


class WorkerConflictError(WorkerControlError):
    pass


class WorkerLifecycleError(WorkerControlError):
    pass


class WorkerLeaseError(WorkerControlError):
    pass
