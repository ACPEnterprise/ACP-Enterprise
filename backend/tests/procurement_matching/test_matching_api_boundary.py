from uuid import uuid4

from app.procurement_matching.errors import (
    ProcurementMatchingConflict,
    ProcurementMatchingNotFound,
    ProcurementMatchingValidation,
)
from app.procurement_matching.router import http_error


def test_matching_errors_use_safe_recovery_envelopes_without_reflection() -> None:
    secret = f"sql-provider-secret-{uuid4()}"
    cases = (
        (ProcurementMatchingNotFound(secret), 404, "not_found", "TERMINAL_FAILURE"),
        (
            ProcurementMatchingConflict(secret),
            409,
            "resource_state_conflict",
            "RETRY_AFTER_REFRESH",
        ),
        (
            ProcurementMatchingValidation(secret),
            422,
            "validation",
            "USER_CORRECTION_REQUIRED",
        ),
    )
    for error, status, code, recovery in cases:
        response = http_error(error)
        assert response.status_code == status
        assert response.detail["code"] == code
        assert response.detail["recovery"] == recovery
        assert secret not in str(response.detail)
