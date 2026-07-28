class ControlledExecutionError(Exception):
    pass


class ControlledExecutionNotFoundError(ControlledExecutionError):
    pass


class ControlledExecutionIneligibleError(ControlledExecutionError):
    pass


class ControlledExecutionConflictError(ControlledExecutionError):
    pass


class ControlledExecutionPayloadError(ControlledExecutionError):
    pass
