class EngineeringControlError(Exception):
    """Base error for safe Engineering Control service failures."""


class EngineeringCommandNotFoundError(EngineeringControlError):
    pass


class EngineeringCommandPermissionError(EngineeringControlError):
    pass


class EngineeringCommandValidationError(EngineeringControlError):
    pass


class EngineeringCommandUnsafeInstructionError(EngineeringCommandValidationError):
    pass


class EngineeringCommandRepositoryPolicyError(EngineeringCommandValidationError):
    pass


class EngineeringCommandExpirationError(EngineeringCommandValidationError):
    pass


class EngineeringCommandIdempotencyConflictError(EngineeringControlError):
    pass


class EngineeringCommandLifecycleError(EngineeringControlError):
    pass


class EngineeringCommandStaleVersionError(EngineeringCommandLifecycleError):
    pass


class EngineeringCommandApprovalMismatchError(EngineeringCommandLifecycleError):
    pass


class EngineeringCommandExpiredError(EngineeringCommandLifecycleError):
    pass


class EngineeringCommandExecutionUnavailableError(EngineeringControlError):
    pass


class ProviderRepositoryReadinessNotCurrentError(EngineeringControlError):
    """The assigned provider readiness is not current for Start."""
