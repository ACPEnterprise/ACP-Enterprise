from uuid import uuid4

from app.purchasing.errors import (
    PurchasingConflict,
    PurchasingError,
    PurchasingNotFound,
    PurchasingValidation,
)
from app.purchasing.router import http_error


def test_purchasing_errors_use_safe_recovery_envelopes_without_reflection() -> None:
    secret = f"constraint-provider-secret-{uuid4()}"
    cases = (
        (PurchasingNotFound(secret), 404, "not_found", "TERMINAL_FAILURE"),
        (
            PurchasingConflict(secret),
            409,
            "resource_state_conflict",
            "RETRY_AFTER_REFRESH",
        ),
        (
            PurchasingValidation(secret),
            422,
            "validation",
            "USER_CORRECTION_REQUIRED",
        ),
        (
            PurchasingError(secret),
            400,
            "internal_failure",
            "OWNER_ADMIN_ACTION_REQUIRED",
        ),
    )
    for error, status, code, recovery in cases:
        response = http_error(error)
        assert response.status_code == status
        assert response.detail["code"] == code
        assert response.detail["recovery"] == recovery
        assert secret not in str(response.detail)
