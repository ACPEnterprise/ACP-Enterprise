import json
import logging
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from scripts.factory_credentials import FactoryCredentialError, FactoryRefreshCredential

NOW = datetime(2026, 9, 8, 17, 30, tzinfo=timezone.utc)
OLD_REFRESH = "old-refresh-secret-material-not-for-logs"
NEW_REFRESH = "new-refresh-secret-material-not-for-logs"
ACCESS = "short-lived-access-secret-not-for-disk"


def secret_file(tmp_path):
    path = tmp_path / "factory-refresh.json"
    path.write_text(json.dumps({"refresh_token": OLD_REFRESH}), encoding="utf-8")
    path.chmod(0o600)
    return path


@pytest.mark.asyncio
async def test_rotates_mode_0600_secret_and_keeps_access_token_off_disk(tmp_path):
    path = secret_file(tmp_path)

    def exchange(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/auth/refresh"
        assert json.loads(request.content)["refresh_token"] == OLD_REFRESH
        return httpx.Response(
            200,
            json={
                "access_token": ACCESS,
                "refresh_token": NEW_REFRESH,
                "access_token_expires_at": "2026-09-08T17:45:00Z",
            },
        )

    renewed = await FactoryRefreshCredential(path).renew(
        control_api_url="https://control.example.invalid",
        delegation_expires_at=NOW + timedelta(hours=72),
        now=NOW,
        transport=httpx.MockTransport(exchange),
    )

    assert renewed.access_token == ACCESS
    assert json.loads(path.read_text()) == {"refresh_token": NEW_REFRESH}
    assert path.stat().st_mode & 0o777 == 0o600
    assert ACCESS not in path.read_text()


@pytest.mark.asyncio
async def test_refuses_renewal_at_delegation_expiry_without_network(tmp_path):
    called = False

    def exchange(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    with pytest.raises(FactoryCredentialError, match="delegation is expired"):
        await FactoryRefreshCredential(secret_file(tmp_path)).renew(
            control_api_url="https://control.example.invalid",
            delegation_expires_at=NOW,
            now=NOW,
            transport=httpx.MockTransport(exchange),
        )
    assert not called


@pytest.mark.asyncio
async def test_revoked_session_denial_preserves_refresh_secret_and_redacts_errors(
    tmp_path, caplog
):
    path = secret_file(tmp_path)
    caplog.set_level(logging.DEBUG)
    with pytest.raises(FactoryCredentialError, match="renewal was denied") as captured:
        await FactoryRefreshCredential(path).renew(
            control_api_url="https://control.example.invalid",
            delegation_expires_at=NOW + timedelta(hours=1),
            now=NOW,
            transport=httpx.MockTransport(lambda request: httpx.Response(401)),
        )
    evidence = str(captured.value) + caplog.text
    assert OLD_REFRESH not in evidence
    assert NEW_REFRESH not in evidence
    assert ACCESS not in evidence
    assert json.loads(path.read_text()) == {"refresh_token": OLD_REFRESH}


@pytest.mark.asyncio
async def test_rejects_permissive_secret_file_before_exchange(tmp_path):
    path = secret_file(tmp_path)
    path.chmod(0o640)
    with pytest.raises(FactoryCredentialError, match="mode-0600"):
        await FactoryRefreshCredential(path).renew(
            control_api_url="https://control.example.invalid",
            delegation_expires_at=NOW + timedelta(hours=1),
            now=NOW,
        )


@pytest.mark.asyncio
async def test_rejects_symbolic_link_secret_file(tmp_path):
    target = secret_file(tmp_path)
    link = tmp_path / "factory-refresh-link.json"
    link.symlink_to(target)
    with pytest.raises(FactoryCredentialError, match="symbolic link"):
        await FactoryRefreshCredential(link).renew(
            control_api_url="https://control.example.invalid",
            delegation_expires_at=NOW + timedelta(hours=1),
            now=NOW,
        )
