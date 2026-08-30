from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.purchasing.errors import (
    PurchasingConflict,
    PurchasingError,
    PurchasingNotFound,
    PurchasingValidation,
)
from app.purchasing.router import decide_requisition, http_error
from app.purchasing.schemas import PurchaseRequisitionTransition


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


@pytest.mark.asyncio
async def test_unsupported_requisition_action_uses_concealed_not_found_contract() -> None:
    with pytest.raises(HTTPException) as captured:
        await decide_requisition(
            uuid4(),
            "protected-action-canary",
            PurchaseRequisitionTransition(
                idempotency_key="unsupported-action-contract",
                expected_version=1,
                reason="Synthetic unsupported action",
            ),
            object(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
        )

    assert captured.value.status_code == 404
    assert captured.value.detail["code"] == "not_found"
    assert captured.value.detail["recovery"] == "TERMINAL_FAILURE"
    assert "protected-action-canary" not in str(captured.value.detail)
