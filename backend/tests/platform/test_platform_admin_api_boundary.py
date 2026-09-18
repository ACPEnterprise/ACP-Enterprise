from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.platform.auth.errors import PasswordPolicyError
from app.platform.auth.router import (
    MAX_RETAINED_USER_AGENT_LENGTH,
    bounded_user_agent,
    client_metadata,
    confirm_password_reset,
    recovery_service,
)
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


def test_authentication_metadata_is_bounded_and_control_free() -> None:
    canary = "browser\x00\x1f\x7f  agent " + "x" * 1000
    request = Request(
        {
            "type": "http",
            "client": ("203.0.113.20", 1234),
            "headers": [(b"user-agent", canary.encode())],
        }
    )

    ip_address, user_agent = client_metadata(request)

    assert ip_address == "203.0.113.20"
    assert user_agent is not None
    assert len(user_agent) == MAX_RETAINED_USER_AGENT_LENGTH
    assert not any(ord(character) < 32 or ord(character) == 127 for character in user_agent)
    assert bounded_user_agent(" \x00\x7f ") is None


@pytest.mark.asyncio
async def test_password_policy_error_is_safe_and_correctable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protected = f"password-policy-secret-{uuid4()}"

    async def reject(*_args, **_kwargs):
        raise PasswordPolicyError(protected)

    async def allow(**_kwargs):
        return None

    monkeypatch.setattr(recovery_service, "confirm_password_reset", reject)
    monkeypatch.setattr("app.platform.auth.router.enforce_rate_limit", allow)
    with pytest.raises(HTTPException) as captured:
        await confirm_password_reset(
            data=PasswordResetConfirmRequest(
                token="qualification-reset-token-0123456789abcdef",
                new_password="qualification-password-0123456789",
            ),
            request=Request(
                {"type": "http", "client": ("127.0.0.1", 1234), "headers": []}
            ),
            session=object(),
        )
    response = captured.value
    assert response.status_code == 422
    assert response.detail["code"] == "validation"
    assert response.detail["recovery"] == "USER_CORRECTION_REQUIRED"
    assert protected not in str(response.detail)
