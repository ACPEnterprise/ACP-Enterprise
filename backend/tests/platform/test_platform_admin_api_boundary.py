from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.platform.auth.errors import PasswordPolicyError
from app.platform.auth.router import confirm_password_reset, recovery_service
from app.platform.auth.schemas import PasswordResetConfirmRequest
from app.platform.company.admin_router import translate_admin_error
from app.platform.company.admin_service import (
    AccessPolicyAdministrationError,
    AccessPolicyConflictError,
    AccessPolicyNotFoundError,
)


def test_company_admin_errors_do_not_reflect_identity_details() -> None:
    protected = f"user-email-role-secret-{uuid4()}"
    cases = (
        (AccessPolicyNotFoundError(protected), 404, "not_found", "TERMINAL_FAILURE"),
        (
            AccessPolicyConflictError(protected),
            409,
            "resource_state_conflict",
            "RETRY_AFTER_REFRESH",
        ),
        (
            AccessPolicyAdministrationError(protected),
            400,
            "validation",
            "USER_CORRECTION_REQUIRED",
        ),
    )
    for error, status, code, recovery in cases:
        response = translate_admin_error(error)
        assert response.status_code == status
        assert response.detail["code"] == code
        assert response.detail["recovery"] == recovery
        assert protected not in str(response.detail)


@pytest.mark.asyncio
async def test_password_policy_error_is_safe_and_correctable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protected = f"password-policy-secret-{uuid4()}"

    async def reject(*_args, **_kwargs):
        raise PasswordPolicyError(protected)

    monkeypatch.setattr(recovery_service, "confirm_password_reset", reject)
    with pytest.raises(HTTPException) as captured:
        await confirm_password_reset(
            data=PasswordResetConfirmRequest(
                token="qualification-reset-token-0123456789abcdef",
                new_password="qualification-password-0123456789",
            ),
            session=object(),
        )
    response = captured.value
    assert response.status_code == 422
    assert response.detail["code"] == "validation"
    assert response.detail["recovery"] == "USER_CORRECTION_REQUIRED"
    assert protected not in str(response.detail)
