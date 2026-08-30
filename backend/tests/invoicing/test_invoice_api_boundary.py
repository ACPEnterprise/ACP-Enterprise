from uuid import uuid4

from app.invoicing.errors import InvoiceConflict, InvoiceNotFound, InvoiceValidation
from app.invoicing.router import _error


def test_invoice_errors_use_safe_recovery_envelopes_without_reflection() -> None:
    secret = f"sql-provider-secret-{uuid4()}"
    cases = (
        (InvoiceNotFound(secret), 404, "not_found", "TERMINAL_FAILURE"),
        (InvoiceConflict(secret), 409, "resource_state_conflict", "RETRY_AFTER_REFRESH"),
        (InvoiceValidation(secret), 422, "validation", "USER_CORRECTION_REQUIRED"),
    )
    for error, status, code, recovery in cases:
        response = _error(error)
        assert response.status_code == status
        assert response.detail["code"] == code
        assert response.detail["recovery"] == recovery
        assert secret not in str(response.detail)
