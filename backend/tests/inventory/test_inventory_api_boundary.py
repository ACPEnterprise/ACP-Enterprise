from uuid import uuid4

from app.inventory.errors import (
    InventoryConflict,
    InventoryNotFound,
    InventoryValidation,
)
from app.inventory.router import translate


def test_inventory_errors_use_safe_recovery_envelopes_without_reflection() -> None:
    secret = f"sql-provider-secret-{uuid4()}"
    cases = (
        (InventoryNotFound(secret), 404, "not_found", "TERMINAL_FAILURE"),
        (
            InventoryConflict(secret),
            409,
            "resource_state_conflict",
            "RETRY_AFTER_REFRESH",
        ),
        (
            InventoryValidation(secret),
            422,
            "validation",
            "USER_CORRECTION_REQUIRED",
        ),
    )
    for error, status, code, recovery in cases:
        response = translate(error)
        assert response.status_code == status
        assert response.detail["code"] == code
        assert response.detail["recovery"] == recovery
        assert secret not in str(response.detail)
