from uuid import uuid4

from app.accounts_payable.errors import APConflict, APNotFound, APValidation
from app.accounts_payable.router import _error


def test_ap_errors_use_safe_recovery_envelopes_without_reflection() -> None:
    secret = f"constraint-secret-{uuid4()}"
    cases = (
        (APNotFound(secret), 404, "not_found", "TERMINAL_FAILURE"),
        (APConflict(secret), 409, "resource_state_conflict", "RETRY_AFTER_REFRESH"),
        (APValidation(secret), 422, "validation", "USER_CORRECTION_REQUIRED"),
    )
    for error, status, code, recovery in cases:
        response = _error(error)
        assert response.status_code == status
        assert response.detail["code"] == code
        assert response.detail["recovery"] == recovery
        assert secret not in str(response.detail)
