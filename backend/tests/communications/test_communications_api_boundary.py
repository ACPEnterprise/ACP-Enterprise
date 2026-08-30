from uuid import uuid4

from app.communications.errors import (
    CommunicationAuthorizationError,
    CommunicationConflictError,
    CommunicationError,
    CommunicationNotFoundError,
    CommunicationValidationError,
)
from app.communications.router import communication_http


def test_communication_errors_use_safe_recovery_without_reflection() -> None:
    secret = f"recipient-provider-secret-{uuid4()}"
    cases = (
        (CommunicationAuthorizationError(secret), 403, "forbidden", "TERMINAL_FAILURE"),
        (CommunicationNotFoundError(secret), 404, "not_found", "TERMINAL_FAILURE"),
        (
            CommunicationConflictError(secret),
            409,
            "resource_state_conflict",
            "RETRY_AFTER_REFRESH",
        ),
        (
            CommunicationValidationError(secret),
            422,
            "validation",
            "USER_CORRECTION_REQUIRED",
        ),
        (
            CommunicationError(secret),
            400,
            "internal_failure",
            "OWNER_ADMIN_ACTION_REQUIRED",
        ),
    )
    for error, status, code, recovery in cases:
        response = communication_http(error)
        assert response.status_code == status
        assert response.detail["code"] == code
        assert response.detail["recovery"] == recovery
        assert secret not in str(response.detail)
