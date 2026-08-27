from __future__ import annotations

import json
import logging
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database.session import get_security_database_session
from app.main import app
from app.qbo_source import router as qbo_router_module
from app.qbo_source.intuit import (
    ACCOUNTING_SCOPE,
    AuthorizedRealm,
    HttpResponse,
    IntuitAuthenticationError,
    OAuthToken,
)
from app.qbo_source.runtime import (
    ProtectedSandboxCompanyBinding,
    SandboxCompanyInfoVerifier,
    SandboxConnectionRegistry,
    SandboxRuntimeError,
)
from app.qbo_source.secrets import (
    ProtectedSandboxSecretProvider,
    SandboxSecretStoreError,
)


class _Runtime:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.received: tuple[str | None, ...] | None = None

    async def complete(self, **values: str | None) -> None:
        self.received = tuple(values.values())
        if self.error:
            raise self.error

    async def begin(self, *, redirect_uri: str) -> str:
        self.received = (redirect_uri,)
        return (
            "https://appcenter.intuit.com/connect/oauth2"
            "?client_id=synthetic-client&response_type=code"
            "&scope=com.intuit.quickbooks.accounting&state=synthetic-state-marker"
        )


class _RateLimiter:
    def __init__(self) -> None:
        self.calls = 0

    async def enforce(self, **_: object) -> None:
        self.calls += 1


def test_callback_boundary_is_sanitized_and_maps_internal_headers(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    runtime = _Runtime()
    monkeypatch.setattr(
        "app.qbo_source.router.get_sandbox_oauth_runtime", lambda: runtime
    )
    markers = ("synthetic-code", "synthetic-state", "synthetic-realm")
    client = TestClient(app)
    with caplog.at_level(logging.DEBUG):
        response = client.get(
            "/api/v1/integrations/qbo/oauth/callback",
            headers={
                "X-ACP-QBO-Code": markers[0],
                "X-ACP-QBO-State": markers[1],
                "X-ACP-QBO-Realm": markers[2],
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "sandbox_oauth_callback",
        "result": "company_verified",
    }
    assert response.headers["cache-control"] == "no-store"
    assert runtime.received == (*markers, None)
    assert not any(marker in caplog.text for marker in markers)
    assert not any(marker in response.text for marker in markers)


@pytest.mark.parametrize(
    ("params", "status_code"),
    [
        ({}, 400),
        ({"state": "synthetic-state-marker", "realmId": "synthetic-realm-marker"}, 400),
        ({"code": "synthetic-code-marker", "realmId": "synthetic-realm-marker"}, 400),
        ({"error": "access_denied", "error_description": "private"}, 400),
    ],
)
def test_callback_rejects_incomplete_or_provider_error_without_echo(
    params: dict[str, str], status_code: int
) -> None:
    response = TestClient(app).get(
        "/api/v1/integrations/qbo/oauth/callback", params=params
    )
    assert response.status_code == status_code
    assert response.json()["result"] == "connection_not_completed"
    assert all(value not in response.text for value in params.values())


@pytest.mark.asyncio
async def test_authorization_initiation_is_bounded_and_does_not_log_state(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    runtime = _Runtime()
    limiter = _RateLimiter()
    monkeypatch.setattr(qbo_router_module, "get_sandbox_oauth_runtime", lambda: runtime)
    monkeypatch.setattr(qbo_router_module, "_rate_limiter", limiter)
    authorization = SimpleNamespace(user=SimpleNamespace(id=uuid4()))

    with caplog.at_level(logging.DEBUG):
        response = await qbo_router_module.qbo_sandbox_oauth_authorize(
            request=SimpleNamespace(), authorization=authorization  # type: ignore[arg-type]
        )

    assert response.status_code == 200
    assert limiter.calls == 1
    assert runtime.received == (
        (
            "https://preview.allcountyhomeservices.com"
            "/api/v1/integrations/qbo/oauth/callback"
        ),
    )
    assert b"com.intuit.quickbooks.accounting" in response.body
    assert "synthetic-state-marker" not in caplog.text


def test_authorization_initiation_requires_bearer_authentication() -> None:
    isolated = FastAPI()
    isolated.include_router(qbo_router_module.router)

    async def database_override():  # type: ignore[no-untyped-def]
        yield object()

    isolated.dependency_overrides[get_security_database_session] = database_override
    response = TestClient(isolated).post(qbo_router_module.AUTHORIZE_PATH)
    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required."}


def test_protected_company_binding_is_exact_and_restricted(tmp_path: Path) -> None:
    binding = ProtectedSandboxCompanyBinding(tmp_path / "configuration")
    binding.path.write_text("Synthetic Sandbox Company", encoding="utf-8")
    os.chmod(binding.path, 0o600)
    assert binding.read() == "Synthetic Sandbox Company"
    assert stat.S_IMODE(binding.root.stat().st_mode) == 0o700

    binding.path.write_text("Synthetic Sandbox Company\n", encoding="utf-8")
    os.chmod(binding.path, 0o600)
    with pytest.raises(SandboxRuntimeError, match="binding_invalid"):
        binding.read()


def _token(generation: int = 1) -> OAuthToken:
    return OAuthToken(
        access_token="synthetic-access-material",
        refresh_token="synthetic-refresh-material",
        access_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        refresh_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        scope=ACCOUNTING_SCOPE,
        generation=generation,
    )


@pytest.mark.asyncio
async def test_protected_token_store_is_restricted_and_generation_safe(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    root = tmp_path / "runtime" / "secrets"
    provider = ProtectedSandboxSecretProvider(root=root, repository_root=repository)
    original = _token()
    await provider.put_token(
        provider.TOKEN_REFERENCE, original, expected_generation=None
    )

    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(provider.token_path.stat().st_mode) == 0o600
    assert await provider.get_token(provider.TOKEN_REFERENCE) == original
    with pytest.raises(SandboxSecretStoreError, match="generation_conflict"):
        await provider.put_token(
            provider.TOKEN_REFERENCE, _token(2), expected_generation=99
        )
    assert (await provider.get_token(provider.TOKEN_REFERENCE)).generation == 1
    with pytest.raises(SandboxSecretStoreError, match="reference_rejected"):
        await provider.get_client_credential("qbo-production/client")


class _Transport:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response

    async def request(self, **_: object) -> HttpResponse:
        return self.response


@pytest.mark.asyncio
async def test_company_info_mismatch_fails_closed_and_deletes_token(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    provider = ProtectedSandboxSecretProvider(
        root=tmp_path / "secrets", repository_root=repository
    )
    await provider.put_token(provider.TOKEN_REFERENCE, _token(), expected_generation=None)
    verifier = SandboxCompanyInfoVerifier(
        transport=_Transport(
            HttpResponse(
                status=200,
                headers={},
                body=json.dumps(
                    {"CompanyInfo": {"Id": "wrong-realm", "CompanyName": "Sandbox"}}
                ).encode(),
            )
        ),
        secrets_provider=provider,
        expected_company_name="Sandbox",
        token_reference=provider.TOKEN_REFERENCE,
        minor_version=75,
        registry=SandboxConnectionRegistry(tmp_path / "connections"),
    )

    with pytest.raises(IntuitAuthenticationError, match="company_realm_mismatch"):
        await verifier.verify(AuthorizedRealm(realm_id="expected-realm", token=_token()))
    assert not provider.token_path.exists()


def test_preview_proxy_suppresses_callback_query_logging() -> None:
    repository = Path(__file__).parents[3]
    nginx = (repository / "frontend/nginx.preview.conf").read_text()
    callback = nginx.split(
        "location = /api/v1/integrations/qbo/oauth/callback {", maxsplit=1
    )[1].split("}", maxsplit=1)[0]
    assert "access_log off;" in callback
    assert "set $qbo_code $arg_code;" in callback
    assert "X-ACP-QBO-Code $qbo_code" in callback
    assert "rewrite ^ /api/v1/integrations/qbo/oauth/callback? break;" in callback
    assert "proxy_pass http://backend:8000;" in callback
    caddy = (
        repository / "docs/deployment/mission-control-preview.caddy"
    ).read_text()
    assert "log_skip @qbo_oauth_callback" in caddy
    assert os.environ.get("QBO_CLIENT_SECRET") is None
