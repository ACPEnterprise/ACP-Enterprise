from uuid import uuid4

from app.price_book.errors import (
    PriceBookConflict,
    PriceBookError,
    PriceBookNotFound,
    PriceBookValidation,
)
from app.price_book.router import http_error


def test_price_book_errors_use_safe_recovery_envelopes_without_reflection() -> None:
    secret = f"sql-provider-secret-{uuid4()}"
    cases = (
        (PriceBookNotFound(secret), 404, "not_found", "TERMINAL_FAILURE"),
        (
            PriceBookConflict(secret),
            409,
            "resource_state_conflict",
            "RETRY_AFTER_REFRESH",
        ),
        (
            PriceBookValidation(secret),
            422,
            "validation",
            "USER_CORRECTION_REQUIRED",
        ),
        (
            PriceBookError(secret),
            500,
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
