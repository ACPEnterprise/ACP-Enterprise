from __future__ import annotations

import json
import logging
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.database.session import get_security_database_session
from app.main import app
from app.platform.permissions.authorization import AuthorizationContext
from app.qbo_source import router as qbo_router_module
from app.qbo_source.diagnostics import (
    OAuthDiagnosticStage,
    ProtectedOAuthDiagnosticJournal,
)
from app.qbo_source.intuit import (
    ACCOUNTING_SCOPE,
    AuthorizedRealm,
    HttpResponse,
    IntuitAuthenticationError,
    IntuitError,
    OAuthToken,
)
from app.qbo_source.runtime import (
    ProtectedSandboxCompanyBinding,
    SandboxCompanyInfoVerifier,
    SandboxConnectionRegistry,
    SandboxOAuthRuntime,
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

    def connection_state(self) -> str:
        return "connected"

    async def disconnect(self) -> str:
        if self.error:
            raise self.error
        return "not_connected"


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
        "result": "connection_completed",
    }
    assert response.headers["cache-control"] == "private, no-store"
    assert runtime.received == (*markers, None)
    assert not any(marker in caplog.text for marker in markers)
    assert not any(marker in response.text for marker in markers)


@pytest.mark.parametrize(
    ("params", "status_code"),
    [
        ({}, 400),
        ({"state": "synthetic-state-marker", "realmId": "synthetic-realm-marker"}, 400),
        ({"code": "synthetic-code-marker", "realmId": "synthetic-realm-marker"}, 400),
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


@pytest.mark.parametrize(
    ("error_code", "safe_result"),
    [
        ("oauth_state_invalid", "state_invalid"),
        ("oauth_state_expired", "state_expired"),
        ("oauth_state_replayed", "state_replayed"),
        ("oauth_provider_rejected", "provider_rejected"),
        ("token_request_rejected", "token_exchange_failed"),
        ("company_info_provider_rejected", "companyinfo_failed"),
        ("company_realm_mismatch", "realm_mismatch"),
        ("company_identity_mismatch", "company_name_mismatch"),
    ],
)
def test_callback_returns_actionable_sanitized_failure(
    monkeypatch: pytest.MonkeyPatch, error_code: str, safe_result: str
) -> None:
    runtime = _Runtime(IntuitAuthenticationError(error_code))
    monkeypatch.setattr(qbo_router_module, "get_sandbox_oauth_runtime", lambda: runtime)

    response = TestClient(app).get(
        "/api/v1/integrations/qbo/oauth/callback",
        headers={
            "X-ACP-QBO-Code": "synthetic-code",
            "X-ACP-QBO-State": "synthetic-state",
            "X-ACP-QBO-Realm": "synthetic-realm",
        },
    )

    assert response.status_code == 400
    assert response.json()["result"] == safe_result
    assert "synthetic" not in response.text


def test_provider_rejection_delegates_state_consumption_without_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _Runtime(IntuitAuthenticationError("oauth_provider_rejected"))
    monkeypatch.setattr(qbo_router_module, "get_sandbox_oauth_runtime", lambda: runtime)

    response = TestClient(app).get(
        "/api/v1/integrations/qbo/oauth/callback",
        params={
            "state": "synthetic-state-marker",
            "error": "access_denied",
            "error_description": "provider-private-description",
        },
    )

    assert response.status_code == 400
    assert response.json()["result"] == "provider_rejected"
    assert runtime.received == (
        None,
        "synthetic-state-marker",
        None,
        "access_denied",
    )
    assert "provider-private-description" not in response.text


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
            request=cast(Request, SimpleNamespace()),
            authorization=cast(AuthorizationContext, authorization),
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


@pytest.mark.asyncio
async def test_disconnect_boundary_is_bounded_and_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _Runtime()
    limiter = _RateLimiter()
    monkeypatch.setattr(qbo_router_module, "get_sandbox_oauth_runtime", lambda: runtime)
    monkeypatch.setattr(qbo_router_module, "_rate_limiter", limiter)
    authorization = cast(
        AuthorizationContext, SimpleNamespace(user=SimpleNamespace(id=uuid4()))
    )

    response = await qbo_router_module.qbo_sandbox_oauth_disconnect(authorization)

    assert response.status_code == 200
    assert response.body == (
        b'{"status":"qbo_sandbox_connection","connection_state":"not_connected"}'
    )
    assert limiter.calls == 1


def test_connection_and_disconnect_require_bearer_authentication() -> None:
    isolated = FastAPI()
    isolated.include_router(qbo_router_module.router)

    async def database_override():  # type: ignore[no-untyped-def]
        yield object()

    isolated.dependency_overrides[get_security_database_session] = database_override
    client = TestClient(isolated)
    assert client.get(qbo_router_module.CONNECTION_PATH).status_code == 401
    assert client.post(qbo_router_module.DISCONNECT_PATH).status_code == 401


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


class _DisconnectOAuth:
    def __init__(
        self, provider: ProtectedSandboxSecretProvider, *, fail: bool = False
    ) -> None:
        self.provider = provider
        self.fail = fail
        self.calls = 0

    async def revoke(self, *, token_reference: str) -> None:
        self.calls += 1
        if self.fail:
            raise IntuitAuthenticationError("token_revocation_failed")
        await self.provider.delete_token(token_reference)


def _disconnect_runtime(
    tmp_path: Path, *, fail: bool = False
) -> tuple[
    SandboxOAuthRuntime,
    ProtectedSandboxSecretProvider,
    SandboxConnectionRegistry,
    _DisconnectOAuth,
]:
    repository = tmp_path / "repository"
    repository.mkdir()
    provider = ProtectedSandboxSecretProvider(
        root=tmp_path / "secrets", repository_root=repository
    )
    registry = SandboxConnectionRegistry(tmp_path / "connections")
    oauth = _DisconnectOAuth(provider, fail=fail)
    runtime = SandboxOAuthRuntime(
        callback=None,  # type: ignore[arg-type]
        verifier=SandboxCompanyInfoVerifier(
            transport=_Transport(HttpResponse(200, {}, b"{}")),
            secrets_provider=provider,
            expected_company_name="Sandbox",
            token_reference=provider.TOKEN_REFERENCE,
            minor_version=75,
            registry=registry,
        ),
        coordinator=SimpleNamespace(oauth=oauth),  # type: ignore[arg-type]
        diagnostics=ProtectedOAuthDiagnosticJournal(
            tmp_path / "oauth-diagnostics", repository_root=repository
        ),
    )
    return runtime, provider, registry, oauth


@pytest.mark.asyncio
async def test_disconnect_revokes_before_cleanup_and_preserves_history(
    tmp_path: Path,
) -> None:
    runtime, provider, registry, oauth = _disconnect_runtime(tmp_path)
    await provider.put_token(
        provider.TOKEN_REFERENCE, _token(), expected_generation=None
    )
    registry.record_verified(
        realm_id="123456789",
        company_info_id="native-id",
        company_name="Sandbox",
        minor_version=75,
    )
    runtime.diagnostics.record("a" * 64, OAuthDiagnosticStage.CONNECTION_COMMITTED)
    diagnostic_before = next(runtime.diagnostics.root.glob("*/*.json")).read_bytes()

    assert runtime.connection_state() == "connected"
    assert await runtime.disconnect() == "not_connected"

    assert oauth.calls == 1
    assert not provider.token_path.exists()
    assert not registry.verified_path.exists()
    histories = list((registry.root / "history").glob("*.json"))
    assert len(histories) == 1
    assert stat.S_IMODE(histories[0].stat().st_mode) == 0o600
    assert (
        next(runtime.diagnostics.root.glob("*/*.json")).read_bytes()
        == diagnostic_before
    )
    assert await runtime.disconnect() == "not_connected"
    assert oauth.calls == 1


@pytest.mark.asyncio
async def test_disconnect_failure_retains_token_and_connection_marker(
    tmp_path: Path,
) -> None:
    runtime, provider, registry, oauth = _disconnect_runtime(tmp_path, fail=True)
    await provider.put_token(
        provider.TOKEN_REFERENCE, _token(), expected_generation=None
    )
    registry.record_verified(
        realm_id="123456789",
        company_info_id="native-id",
        company_name="Sandbox",
        minor_version=75,
    )

    with pytest.raises(IntuitAuthenticationError, match="token_revocation_failed"):
        await runtime.disconnect()

    assert oauth.calls == 1
    assert provider.token_path.exists()
    assert registry.verified_path.exists()
    assert runtime.connection_state() == "connected"


@pytest.mark.asyncio
async def test_duplicate_disconnect_is_rejected_before_provider_call(
    tmp_path: Path,
) -> None:
    runtime, provider, registry, oauth = _disconnect_runtime(tmp_path)
    await provider.put_token(
        provider.TOKEN_REFERENCE, _token(), expected_generation=None
    )
    registry.record_verified(
        realm_id="123456789",
        company_info_id="native-id",
        company_name="Sandbox",
        minor_version=75,
    )
    registry.begin_disconnect()
    try:
        assert runtime.connection_state() == "disconnecting"
        with pytest.raises(SandboxRuntimeError, match="state_inconsistent"):
            await runtime.disconnect()
        assert oauth.calls == 0
        assert provider.token_path.exists()
        assert registry.verified_path.exists()
    finally:
        registry.end_disconnect()


def _token(generation: int = 1, *, realm_id: str = "123456789") -> OAuthToken:
    return OAuthToken(
        access_token="synthetic-access-material",
        refresh_token="synthetic-refresh-material",
        access_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        refresh_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        scope=ACCOUNTING_SCOPE,
        generation=generation,
        realm_id=realm_id,
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
    def __init__(self, response: HttpResponse | Exception) -> None:
        self.response = response
        self.requests: list[dict[str, object]] = []

    async def request(self, **values: object) -> HttpResponse:
        self.requests.append(values)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.mark.asyncio
async def test_company_info_native_id_is_separate_from_authorized_realm(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    provider = ProtectedSandboxSecretProvider(
        root=tmp_path / "secrets", repository_root=repository
    )
    await provider.put_token(
        provider.TOKEN_REFERENCE, _token(), expected_generation=None
    )
    transport = _Transport(
        HttpResponse(
            status=200,
            headers={},
            body=json.dumps(
                {
                    "CompanyInfo": {
                        "Id": "native-company-info-id",
                        "CompanyName": "Sandbox",
                    }
                }
            ).encode(),
        )
    )
    registry = SandboxConnectionRegistry(tmp_path / "connections")
    verifier = SandboxCompanyInfoVerifier(
        transport=transport,
        secrets_provider=provider,
        expected_company_name="Sandbox",
        token_reference=provider.TOKEN_REFERENCE,
        minor_version=75,
        registry=registry,
    )

    await verifier.verify(AuthorizedRealm(realm_id="123456789", token=_token()))

    assert transport.requests[0]["url"] == (
        "https://sandbox-quickbooks.api.intuit.com/v3/company/"
        "123456789/companyinfo/123456789?minorversion=75"
    )
    connection = json.loads((registry.root / "verified.json").read_text())
    assert connection["realm_id"] == "123456789"
    assert connection["company_info_id"] == "native-company-info-id"
    assert connection["company_name"] == "Sandbox"
    assert connection["schema_version"] == "qbo-sandbox-connection/v2"


@pytest.mark.asyncio
async def test_token_bound_to_another_realm_fails_before_company_info_request(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    provider = ProtectedSandboxSecretProvider(
        root=tmp_path / "secrets", repository_root=repository
    )
    transport = _Transport(
        HttpResponse(
            status=200,
            headers={},
            body=b"{}",
        )
    )
    verifier = SandboxCompanyInfoVerifier(
        transport=transport,
        secrets_provider=provider,
        expected_company_name="Sandbox",
        token_reference=provider.TOKEN_REFERENCE,
        minor_version=75,
        registry=SandboxConnectionRegistry(tmp_path / "connections"),
    )

    with pytest.raises(IntuitAuthenticationError, match="company_realm_mismatch"):
        await verifier.verify(
            AuthorizedRealm(realm_id="123456789", token=_token(realm_id="987654321"))
        )
    assert transport.requests == []


def test_sanitized_diagnostic_journal_is_restricted_and_append_only(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    journal = ProtectedOAuthDiagnosticJournal(
        tmp_path / "oauth-diagnostics", repository_root=repository
    )
    attempt_id = "a" * 64
    journal.record(attempt_id, OAuthDiagnosticStage.CALLBACK_REACHED)
    journal.record(
        attempt_id,
        OAuthDiagnosticStage.CONNECTION_FAILED,
        failure_classification="token_exchange_failed",
    )

    records = sorted((journal.root / attempt_id).iterdir())
    content = b"".join(path.read_bytes() for path in records)
    assert len(records) == 2
    assert stat.S_IMODE(journal.root.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in records)
    assert b"token_exchange_failed" in content
    for forbidden in (
        b"synthetic-code",
        b"synthetic-state",
        b"synthetic-access-material",
        b"synthetic-refresh-material",
        b"client-secret",
    ):
        assert forbidden not in content


class _PersistedTokenCallback:
    def __init__(
        self,
        provider: ProtectedSandboxSecretProvider,
        *,
        callback_realm: str = "123456789",
        token_realm: str = "123456789",
    ) -> None:
        self.provider = provider
        self.callback_realm = callback_realm
        self.token_realm = token_realm
        self.state_consumed = False

    async def handle(self, **_: str | None) -> AuthorizedRealm:
        self.state_consumed = True
        token = _token(realm_id=self.token_realm)
        await self.provider.put_token(
            self.provider.TOKEN_REFERENCE, token, expected_generation=None
        )
        return AuthorizedRealm(realm_id=self.callback_realm, token=token)


@pytest.mark.asyncio
async def test_real_attempt_shape_commits_distinct_company_info_native_id(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    provider = ProtectedSandboxSecretProvider(
        root=tmp_path / "secrets", repository_root=repository
    )
    callback = _PersistedTokenCallback(provider)
    registry = SandboxConnectionRegistry(tmp_path / "connections")
    diagnostics = ProtectedOAuthDiagnosticJournal(
        tmp_path / "oauth-diagnostics", repository_root=repository
    )
    verifier = SandboxCompanyInfoVerifier(
        transport=_Transport(
            HttpResponse(
                status=200,
                headers={},
                body=json.dumps(
                    {
                        "CompanyInfo": {
                            "Id": "native-company-info-id",
                            "CompanyName": "Sandbox",
                        }
                    }
                ).encode(),
            )
        ),
        secrets_provider=provider,
        expected_company_name="Sandbox",
        token_reference=provider.TOKEN_REFERENCE,
        minor_version=75,
        registry=registry,
    )
    runtime = SandboxOAuthRuntime(
        callback=callback,  # type: ignore[arg-type]
        verifier=verifier,
        coordinator=None,  # type: ignore[arg-type]
        diagnostics=diagnostics,
    )

    await runtime.complete(
        code="synthetic-code",
        state="synthetic-state-" + "x" * 32,
        realm_id="123456789",
        provider_error=None,
    )

    assert callback.state_consumed
    assert provider.token_path.exists()
    connection = json.loads((registry.root / "verified.json").read_text())
    assert connection["realm_id"] == "123456789"
    assert connection["company_info_id"] == "native-company-info-id"
    evidence = b"".join(path.read_bytes() for path in diagnostics.root.glob("*/*.json"))
    for expected in (
        b'"stage":"STATE_VALIDATED"',
        b'"stage":"TOKEN_PERSISTED_TEMPORARILY"',
        b'"stage":"COMPANYINFO_REQUEST_STARTED"',
        b'"stage":"VERIFICATION_SUCCEEDED"',
        b'"stage":"CONNECTION_COMMITTED"',
    ):
        assert expected in evidence
    for forbidden in (
        b"synthetic-code",
        b"synthetic-state",
        b"synthetic-access-material",
        b"synthetic-refresh-material",
    ):
        assert forbidden not in evidence


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("callback_realm", "token_realm", "response", "error_code", "stage"),
    [
        (
            "123456789",
            "987654321",
            HttpResponse(200, {}, b"{}"),
            "company_realm_mismatch",
            "REALM_MISMATCH",
        ),
        (
            "123456789",
            "123456789",
            HttpResponse(200, {}, b"not-json"),
            "company_info_response_malformed",
            "COMPANYINFO_RESPONSE_MALFORMED",
        ),
        (
            "123456789",
            "123456789",
            HttpResponse(
                200,
                {},
                json.dumps(
                    {
                        "CompanyInfo": {
                            "Id": "native-company-info-id",
                            "CompanyName": "Different Sandbox",
                        }
                    }
                ).encode(),
            ),
            "company_identity_mismatch",
            "COMPANY_NAME_MISMATCH",
        ),
        (
            "123456789",
            "123456789",
            HttpResponse(401, {}, b"{}"),
            "company_info_provider_rejected",
            "COMPANYINFO_PROVIDER_REJECTED",
        ),
        (
            "123456789",
            "123456789",
            RuntimeError("synthetic transport failure"),
            "company_info_transport_failed",
            "COMPANYINFO_TRANSPORT_FAILED",
        ),
    ],
)
async def test_post_exchange_failures_clean_token_and_never_commit(
    tmp_path: Path,
    callback_realm: str,
    token_realm: str,
    response: HttpResponse | Exception,
    error_code: str,
    stage: str,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    provider = ProtectedSandboxSecretProvider(
        root=tmp_path / "secrets", repository_root=repository
    )
    callback = _PersistedTokenCallback(
        provider, callback_realm=callback_realm, token_realm=token_realm
    )
    registry = SandboxConnectionRegistry(tmp_path / "connections")
    diagnostics = ProtectedOAuthDiagnosticJournal(
        tmp_path / "oauth-diagnostics", repository_root=repository
    )
    runtime = SandboxOAuthRuntime(
        callback=callback,  # type: ignore[arg-type]
        verifier=SandboxCompanyInfoVerifier(
            transport=_Transport(response),
            secrets_provider=provider,
            expected_company_name="Sandbox",
            token_reference=provider.TOKEN_REFERENCE,
            minor_version=75,
            registry=registry,
        ),
        coordinator=None,  # type: ignore[arg-type]
        diagnostics=diagnostics,
    )

    with pytest.raises(IntuitError, match=error_code):
        await runtime.complete(
            code="synthetic-code",
            state="synthetic-state-" + "x" * 32,
            realm_id=callback_realm,
            provider_error=None,
        )

    assert not provider.token_path.exists()
    assert not (registry.root / "verified.json").exists()
    evidence = b"".join(path.read_bytes() for path in diagnostics.root.glob("*/*.json"))
    assert f'"stage":"{stage}"'.encode() in evidence
    assert b'"stage":"TOKEN_CLEANUP_SUCCEEDED"' in evidence
    assert b'"stage":"CONNECTION_FAILED"' in evidence


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
    caddy = (repository / "docs/deployment/mission-control-preview.caddy").read_text()
    assert "log_skip @qbo_oauth_callback" in caddy
    assert os.environ.get("QBO_CLIENT_SECRET") is None
