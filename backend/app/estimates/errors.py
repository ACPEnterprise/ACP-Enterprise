class EstimateError(Exception):
    """Base Estimate domain error."""


class EstimateValidationError(EstimateError):
    pass


class EstimateNotFoundError(EstimateError):
    pass


class EstimateConflictError(EstimateError):
    pass
