class EngineeringExecutionError(Exception):
    pass


class EngineeringExecutionPermissionError(EngineeringExecutionError):
    pass


class EngineeringExecutionCommandNotFoundError(EngineeringExecutionError):
    pass


class EngineeringExecutionIneligibleError(EngineeringExecutionError):
    pass


class EngineeringExecutionConflictError(EngineeringExecutionError):
    pass
