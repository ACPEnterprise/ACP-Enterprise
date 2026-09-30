from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from app.marketing.oauth import (
    GoogleAdsOAuthError,
    GoogleAdsOAuthRuntime,
    ProtectedGoogleAuthorizationStore,
)
from app.platform.secrets import ProtectedSecretProvider, SecretProviderError


def _provider(tmp_path: Path, environment: str = "beta") -> ProtectedSecretProvider:
    repository = tmp_path / "repository"
    repository.mkdir()
    return ProtectedSecretProvider(
        root=tmp_path / f"{environment}-secrets",
        repository_root=repository,
        environment=environment,
    )


def test_platform_secret_write_read_rotate_revoke_and_environment_isolation(
    tmp_path: Path,
) -> None:
    provider = _provider(tmp_path)
    reference = "marketing/beta/google-ads/client"
    first = provider.write(
        reference,
        {"client_id": "fixture-id", "client_secret": "fixture-secret"},
        expected_generation=None,
    )
    assert first.generation == 1
    assert provider.read(reference).values["client_id"] == "fixture-id"
    second = provider.write(
        reference,
        {"client_id": "fixture-id-2", "client_secret": "fixture-secret-2"},
        expected_generation=1,
    )
    assert second.generation == 2
    with pytest.raises(SecretProviderError, match="secret_generation_conflict"):
        provider.write(reference, {"client_id": "stale"}, expected_generation=1)
    with pytest.raises(SecretProviderError, match="environment_mismatch"):
        provider.read("marketing/production/google-ads/client")
    provider.revoke(reference, expected_generation=2)
    with pytest.raises(SecretProviderError, match="secret_unavailable"):
        provider.read(reference)


@pytest.mark.asyncio
async def test_oauth_state_nonce_success_and_replay_denial(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    client_reference = "marketing/beta/google-ads/client"
    developer_reference = "marketing/beta/google-ads/developer"
    provider.write(
        client_reference,
        {"client_id": "fixture-id", "client_secret": "fixture-secret"},
        expected_generation=None,
    )
    provider.write(
        developer_reference,
        {"developer_token": "fixture-developer"},
        expected_generation=None,
    )
    states = ProtectedGoogleAuthorizationStore(
        root=tmp_path / "states", repository_root=tmp_path / "repository"
    )

    def exchange(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://oauth2.googleapis.com/token"
        return httpx.Response(
            200,
            json={
                "access_token": "fixture-access",
                "refresh_token": "fixture-refresh",
                "expires_in": 3600,
                "scope": "https://www.googleapis.com/auth/adwords",
            },
        )

    runtime = GoogleAdsOAuthRuntime(
        environment="beta",
        redirect_uri="https://beta.example.test/api/v1/marketing/google-ads/oauth/callback",
        client_reference=client_reference,
        developer_reference=developer_reference,
        secrets_provider=provider,
        states=states,
        state_signing_key=b"s" * 32,
        client=httpx.AsyncClient(transport=httpx.MockTransport(exchange)),
    )
    company_id, user_id, session_id = uuid4(), uuid4(), uuid4()
    url, nonce = runtime.begin(
        company_id=company_id, user_id=user_id, session_id=session_id
    )
    state = url.split("state=", 1)[1].split("&", 1)[0]
    pending, generation, expires_at = await runtime.complete(
        code="fixture-code", state=state, nonce=nonce
    )
    assert pending.company_id == company_id
    assert pending.user_id == user_id
    assert pending.session_id == session_id
    assert generation == 1 and expires_at > datetime.now(timezone.utc)
    with pytest.raises(GoogleAdsOAuthError, match="oauth_state_replayed"):
        await runtime.complete(code="fixture-code", state=state, nonce=nonce)


@pytest.mark.asyncio
async def test_oauth_wrong_browser_session_nonce_fails_closed(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    provider.write(
        "marketing/beta/google-ads/client",
        {"client_id": "id", "client_secret": "secret"},
        expected_generation=None,
    )
    provider.write(
        "marketing/beta/google-ads/developer",
        {"developer_token": "developer"},
        expected_generation=None,
    )
    runtime = GoogleAdsOAuthRuntime(
        environment="beta",
        redirect_uri="https://beta.example.test/api/v1/marketing/google-ads/oauth/callback",
        client_reference="marketing/beta/google-ads/client",
        developer_reference="marketing/beta/google-ads/developer",
        secrets_provider=provider,
        states=ProtectedGoogleAuthorizationStore(
            root=tmp_path / "states", repository_root=tmp_path / "repository"
        ),
        state_signing_key=b"s" * 32,
    )
    url, _ = runtime.begin(company_id=uuid4(), user_id=uuid4(), session_id=uuid4())
    state = url.split("state=", 1)[1].split("&", 1)[0]
    with pytest.raises(GoogleAdsOAuthError, match="oauth_session_mismatch"):
        await runtime.complete(code="unused", state=state, nonce="wrong-browser")
