class CommunicationError(Exception):
    """Base communications failure safe for API translation."""


class CommunicationValidationError(CommunicationError):
    pass


class CommunicationAuthorizationError(CommunicationError):
    pass


class CommunicationNotFoundError(CommunicationError):
    pass


class CommunicationConflictError(CommunicationError):
    pass
