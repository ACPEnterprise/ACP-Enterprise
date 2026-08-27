from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import JSONResponse

from app.platform.auth.errors import RateLimitExceededError, RateLimitUnavailableError
from app.platform.auth.rate_limit import AuthenticationRateLimiter
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AdministrationPermission
from app.platform.permissions.dependencies import require_permission

from .callback import CALLBACK_PATH
from .intuit import IntuitAuthenticationError, IntuitProtocolError
from .runtime import SandboxRuntimeError, get_sandbox_oauth_runtime
from .secrets import SandboxSecretStoreError

router = APIRouter(tags=["QBO Sandbox OAuth"])
_rate_limiter = AuthenticationRateLimiter()
_Administer = Annotated[
    AuthorizationContext,
    Depends(require_permission(AdministrationPermission.COMPANY_ADMINISTER)),
]

AUTHORIZE_PATH = "/api/v1/integrations/qbo/oauth/authorize"
CONNECTION_PATH = "/api/v1/integrations/qbo/connection"
DISCONNECT_PATH = "/api/v1/integrations/qbo/oauth/disconnect"
_CALLBACK_URI = (
    "https://preview.allcountyhomeservices.com/api/v1/integrations/qbo/oauth/callback"
)

_SAFE_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "Referrer-Policy": "no-referrer",
}


def _safe_response(status_code: int, code: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"status": "sandbox_oauth_callback", "result": code},
        headers=_SAFE_HEADERS,
    )


def _connection_response(status_code: int, connection_state: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "qbo_sandbox_connection",
            "connection_state": connection_state,
        },
        headers=_SAFE_HEADERS,
    )


@router.get(CONNECTION_PATH, name="qbo-sandbox-connection-status")
async def qbo_sandbox_connection_status(
    authorization: _Administer,
) -> JSONResponse:
    del authorization
    try:
        state = get_sandbox_oauth_runtime().connection_state()
    except (SandboxRuntimeError, SandboxSecretStoreError):
        return _connection_response(status.HTTP_503_SERVICE_UNAVAILABLE, "unavailable")
    return _connection_response(status.HTTP_200_OK, state)


@router.post(DISCONNECT_PATH, name="qbo-sandbox-oauth-disconnect")
async def qbo_sandbox_oauth_disconnect(
    authorization: _Administer,
) -> JSONResponse:
    identifier = hashlib.sha256(str(authorization.user.id).encode()).hexdigest()
    try:
        await _rate_limiter.enforce(
            bucket="qbo-sandbox-oauth-disconnect",
            identifier_hash=identifier,
            limit=2,
            window_seconds=600,
        )
        state = await get_sandbox_oauth_runtime().disconnect()
    except RateLimitExceededError:
        return _connection_response(
            status.HTTP_429_TOO_MANY_REQUESTS, "disconnect_failed"
        )
    except RateLimitUnavailableError:
        return _connection_response(
            status.HTTP_503_SERVICE_UNAVAILABLE, "disconnect_failed"
        )
    except (IntuitAuthenticationError, IntuitProtocolError):
        return _connection_response(status.HTTP_502_BAD_GATEWAY, "disconnect_failed")
    except (SandboxRuntimeError, SandboxSecretStoreError, OSError, ValueError):
        return _connection_response(
            status.HTTP_503_SERVICE_UNAVAILABLE, "disconnect_failed"
        )
    return _connection_response(status.HTTP_200_OK, state)


def _safe_callback_error(error: IntuitAuthenticationError | IntuitProtocolError) -> str:
    if error.code == "oauth_state_expired":
        return "state_expired"
    if error.code == "oauth_state_replayed":
        return "state_replayed"
    if error.code == "oauth_provider_rejected":
        return "provider_rejected"
    if error.code.startswith(("oauth_state", "oauth_environment")):
        return "state_invalid"
    if error.code.startswith("token_") or error.code == "invalid_token_response":
        return "token_exchange_failed"
    if error.code == "company_realm_mismatch":
        return "realm_mismatch"
    if error.code == "company_identity_mismatch":
        return "company_name_mismatch"
    if error.code.startswith("company_info"):
        return "companyinfo_failed"
    return "provider_verification_failed"


@router.post(AUTHORIZE_PATH, name="qbo-sandbox-oauth-authorize")
async def qbo_sandbox_oauth_authorize(
    request: Request,
    authorization: _Administer,
) -> JSONResponse:
    """Create protected state and return one sandbox authorization URL."""
    del request
    identifier = hashlib.sha256(str(authorization.user.id).encode()).hexdigest()
    try:
        await _rate_limiter.enforce(
            bucket="qbo-sandbox-oauth-initiation",
            identifier_hash=identifier,
            limit=3,
            window_seconds=600,
        )
        authorization_url = await get_sandbox_oauth_runtime().begin(
            redirect_uri=_CALLBACK_URI
        )
    except RateLimitExceededError:
        return _safe_response(status.HTTP_429_TOO_MANY_REQUESTS, "initiation_limited")
    except RateLimitUnavailableError:
        return _safe_response(
            status.HTTP_503_SERVICE_UNAVAILABLE, "initiation_safeguard_unavailable"
        )
    except (SandboxRuntimeError, SandboxSecretStoreError, ValueError):
        return _safe_response(
            status.HTTP_503_SERVICE_UNAVAILABLE, "sandbox_not_configured"
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "sandbox_oauth_initiation",
            "authorization_url": authorization_url,
        },
        headers=_SAFE_HEADERS,
    )


@router.get(CALLBACK_PATH, name="qbo-sandbox-oauth-callback")
async def qbo_sandbox_oauth_callback(
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    realm_id: Annotated[str | None, Query(alias="realmId")] = None,
    provider_error: Annotated[str | None, Query(alias="error")] = None,
    error_description: Annotated[str | None, Query()] = None,
    internal_code: Annotated[str | None, Header(alias="X-ACP-QBO-Code")] = None,
    internal_state: Annotated[str | None, Header(alias="X-ACP-QBO-State")] = None,
    internal_realm: Annotated[str | None, Header(alias="X-ACP-QBO-Realm")] = None,
    internal_error: Annotated[str | None, Header(alias="X-ACP-QBO-Error")] = None,
) -> JSONResponse:
    del error_description
    effective_code = internal_code or code
    effective_state = internal_state or state
    effective_realm = internal_realm or realm_id
    effective_error = internal_error or provider_error
    if not effective_state or (
        not effective_error and not all((effective_code, effective_realm))
    ):
        return _safe_response(status.HTTP_400_BAD_REQUEST, "connection_not_completed")
    try:
        runtime = get_sandbox_oauth_runtime()
        await runtime.complete(
            code=effective_code,
            state=effective_state,
            realm_id=effective_realm,
            provider_error=effective_error,
        )
    except (SandboxRuntimeError, SandboxSecretStoreError):
        return _safe_response(
            status.HTTP_503_SERVICE_UNAVAILABLE, "sandbox_not_configured"
        )
    except (IntuitAuthenticationError, IntuitProtocolError) as error:
        return _safe_response(status.HTTP_400_BAD_REQUEST, _safe_callback_error(error))
    except ValueError:
        return _safe_response(
            status.HTTP_400_BAD_REQUEST, "provider_verification_failed"
        )
    except Exception:  # noqa: BLE001 - external boundary returns no sensitive detail
        return _safe_response(
            status.HTTP_502_BAD_GATEWAY, "provider_verification_failed"
        )
    return _safe_response(status.HTTP_200_OK, "connection_completed")
