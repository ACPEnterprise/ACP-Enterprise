from enum import Enum


class RepositoryOperationType(str, Enum):
    COMMIT = "commit"


class RepositoryAuthorizationState(str, Enum):
    AUTHORIZED = "authorized"
    EXPIRED = "expired"
    REVOKED = "revoked"
    CONSUMED = "consumed"


class RepositoryAuthorizationEventType(str, Enum):
    REQUESTED = "requested"
    GRANTED = "granted"
    REVOKED = "revoked"
    EXPIRED = "expired"
    CONSUMED = "consumed"
