from uuid import uuid4

from app.field_service.errors import (
    FieldServiceConflict,
    FieldServiceNotFound,
    FieldServiceValidation,
)
from app.field_service.router import field_error


def test_field_service_errors_use_safe_recovery_envelopes_without_reflection() -> None:
    secret = f"sql-provider-secret-{uuid4()}"
    cases = (
        (FieldServiceNotFound(secret), 404, "not_found", "TERMINAL_FAILURE"),
        (
            FieldServiceConflict(secret),
            409,
            "resource_state_conflict",
            "RETRY_AFTER_REFRESH",
        ),
        (
            FieldServiceValidation(secret),
            422,
            "validation",
            "USER_CORRECTION_REQUIRED",
        ),
    )
    for error, status, code, recovery in cases:
        response = field_error(error)
        assert response.status_code == status
        assert response.detail["code"] == code
        assert response.detail["recovery"] == recovery
        assert secret not in str(response.detail)
