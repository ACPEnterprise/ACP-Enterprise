class WorkerIdentityError(Exception):
    pass


class WorkerIdentityPermissionError(WorkerIdentityError):
    pass


class WorkerIdentityNotFoundError(WorkerIdentityError):
    pass


class WorkerIdentityConflictError(WorkerIdentityError):
    pass


class WorkerIdentityLifecycleError(WorkerIdentityError):
    pass


class WorkerIdentityValidationError(WorkerIdentityError):
    pass
