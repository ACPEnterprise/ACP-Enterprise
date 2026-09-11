from __future__ import annotations

import json
import os
import stat
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app
from app.platform.permissions.authorization import AuthorizationContext
from app.qbo_source import router as qbo_router_module
from app.qbo_source.contracts import EntityKind
from app.qbo_source.evidence import RunState
from app.qbo_source.intuit import (
    ACCOUNTING_SCOPE,
    AuthorizedRealm,
    HttpResponse,
    IntuitEnvironment,
    IntuitHttpTransport,
    IntuitProtocolError,
    OAuthToken,
)
from app.qbo_source.production import (
    PRODUCTION_ACQUISITION_SCOPE,
    PRODUCTION_READ_PROBE_PREFIX,
    PRODUCTION_READ_PROBE_SCOPE,
    ProductionAcquisitionCommand,
    execute_production_acquisition,
    execute_production_read_probe,
)
from app.qbo_source.router import PRODUCTION_CALLBACK_PATH
from app.qbo_source.runner import AcquisitionResult
from app.qbo_source.runtime import (
    ProtectedSandboxCompanyBinding,
    SandboxCompanyInfoVerifier,
    SandboxConnectionRegistry,
    SandboxOAuthRuntime,
    SandboxRuntimeError,
)
from app.qbo_source.secrets import (
    ProtectedProductionSecretProvider,
    ProtectedSandboxSecretProvider,
)


class _Closable:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class _Transport:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.urls: list[str] = []

    async def request(self, **values: object) -> HttpResponse:
        self.urls.append(str(values["url"]))
        return self.response


class _ProductionProbeTransport(_Transport):
    def __init__(self) -> None:
        super().__init__(
            HttpResponse(
                200,
                {},
                json.dumps(
                    {
                        "CompanyInfo": {
                            "Id": "native-company-id",
                            "CompanyName": "Exact Company",
                        }
                    }
                ).encode(),
            )
        )
        self.client = _Closable()


class _ConnectionEvidenceRuntime:
    async def connection_evidence(self) -> dict[str, object]:
        return {
            "connection_state": "connected",
            "provider_environment": "production",
            "company_identity_sha256": "a" * 64,
            "company_info_verified_at": "2026-09-11T02:00:00+00:00",
            "company_info_readability": "verified_at_oauth_connection",
            "credential_state": "verified_production_client",
            "token_realm_binding": "verified",
            "refresh_authority": "access_token_current",
            "acquisition_eligible": True,
        }


def _token(realm_id: str = "123456789") -> OAuthToken:
    now = datetime.now(timezone.utc)
    return OAuthToken(
        access_token="synthetic-access",
        refresh_token="synthetic-refresh",
        access_expires_at=now + timedelta(hours=1),
        refresh_expires_at=now + timedelta(days=100),
        scope=ACCOUNTING_SCOPE,
        generation=0,
        realm_id=realm_id,
    )


def test_production_secret_namespace_is_physically_distinct(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    sandbox = ProtectedSandboxSecretProvider(
        root=tmp_path / "sandbox", repository_root=repository
    )
    production = ProtectedProductionSecretProvider(
        root=tmp_path / "production", repository_root=repository
    )

    assert sandbox.CLIENT_REFERENCE != production.CLIENT_REFERENCE
    assert sandbox.TOKEN_REFERENCE != production.TOKEN_REFERENCE
    assert sandbox.client_path != production.client_path
    assert sandbox.token_path != production.token_path
    assert stat.S_IMODE(production.root.stat().st_mode) == 0o700


@pytest.mark.asyncio
async def test_production_companyinfo_uses_authorized_realm_and_exact_name(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    provider = ProtectedProductionSecretProvider(
        root=tmp_path / "secrets", repository_root=repository
    )
    transport = _Transport(
        HttpResponse(
            200,
            {},
            json.dumps(
                {
                    "CompanyInfo": {
                        "Id": "native-company-id",
                        "CompanyName": "Exact Company",
                    }
                }
            ).encode(),
        )
    )
    registry = SandboxConnectionRegistry(tmp_path / "connections", "production")
    verifier = SandboxCompanyInfoVerifier(
        transport=transport,
        secrets_provider=provider,
        expected_company_name="Exact Company",
        token_reference=provider.TOKEN_REFERENCE,
        minor_version=75,
        registry=registry,
        environment=IntuitEnvironment.PRODUCTION,
    )

    await verifier.verify(AuthorizedRealm(realm_id="123456789", token=_token()))

    assert transport.urls == [
        "https://quickbooks.api.intuit.com/v3/company/123456789/companyinfo/123456789?minorversion=75"
    ]
    marker = json.loads(registry.verified_path.read_text())
    assert marker["environment"] == "production"
    assert marker["realm_id"] == "123456789"
    assert marker["company_info_id"] == "native-company-id"


@pytest.mark.asyncio
async def test_production_accounting_host_rejects_post() -> None:
    transport = IntuitHttpTransport()
    with pytest.raises(IntuitProtocolError, match="operation_rejected"):
        await transport.request(
            method="POST",
            url="https://quickbooks.api.intuit.com/v3/company/123/invoice",
            headers={},
            body=b"{}",
        )
    await transport.client.aclose()


def test_production_callback_fails_closed_until_external_configuration() -> None:
    response = TestClient(app).get(
        PRODUCTION_CALLBACK_PATH,
        params={"code": "synthetic", "state": "s" * 32, "realmId": "123"},
    )
    assert response.status_code == 503
    assert response.json() == {
        "status": "qbo_production_oauth_callback",
        "result": "production_not_configured",
    }
    assert "synthetic" not in response.text


def test_production_connection_evidence_requires_authentication() -> None:
    response = TestClient(app).get(qbo_router_module.PRODUCTION_CONNECTION_PATH)
    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required."}


@pytest.mark.asyncio
async def test_production_connection_evidence_surfaces_verified_readability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        qbo_router_module,
        "get_production_oauth_runtime",
        lambda: _ConnectionEvidenceRuntime(),
    )

    response = await qbo_router_module.qbo_production_connection_evidence(
        cast(AuthorizationContext, SimpleNamespace())
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert json.loads(response.body) == {
        "status": "qbo_production_connection",
        "connection_state": "connected",
        "provider_environment": "production",
        "company_identity_sha256": "a" * 64,
        "company_info_verified_at": "2026-09-11T02:00:00+00:00",
        "company_info_readability": "verified_at_oauth_connection",
        "credential_state": "verified_production_client",
        "token_realm_binding": "verified",
        "refresh_authority": "access_token_current",
        "acquisition_eligible": True,
        "mutation_authority": "none",
    }


@pytest.mark.asyncio
async def test_production_connection_evidence_surfaces_missing_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable() -> object:
        raise SandboxRuntimeError("production_oauth_runtime_disabled")

    monkeypatch.setattr(qbo_router_module, "get_production_oauth_runtime", unavailable)

    response = await qbo_router_module.qbo_production_connection_evidence(
        cast(AuthorizationContext, SimpleNamespace())
    )

    assert json.loads(response.body) == {
        "status": "qbo_production_connection",
        "connection_state": "unavailable",
        "provider_environment": "production",
        "company_identity_sha256": None,
        "company_info_verified_at": None,
        "company_info_readability": "unverified",
        "credential_state": "unverified",
        "token_realm_binding": "unverified",
        "refresh_authority": "unverified",
        "acquisition_eligible": False,
        "mutation_authority": "none",
    }


@pytest.mark.asyncio
async def test_runtime_connection_evidence_hashes_exact_verified_company(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    provider = ProtectedProductionSecretProvider(
        root=tmp_path / "secrets", repository_root=repository
    )
    provider.client_path.write_text(
        json.dumps(
            {
                "schema_version": "qbo-production-client/v1",
                "environment": "production",
                "client_id": "synthetic-client",
                "client_secret": "synthetic-secret",
            }
        )
    )
    os.chmod(provider.client_path, 0o600)
    await provider.put_token(
        provider.TOKEN_REFERENCE, _token("realm-123"), expected_generation=None
    )
    registry = SandboxConnectionRegistry(tmp_path / "connections", "production")
    registry.record_verified(
        realm_id="realm-123",
        company_info_id="company-456",
        company_name="Exact Company",
        minor_version=75,
    )
    verifier = SimpleNamespace(
        secrets_provider=provider,
        registry=registry,
        environment=IntuitEnvironment.PRODUCTION,
    )
    runtime = SandboxOAuthRuntime(
        callback=cast(object, SimpleNamespace()),
        verifier=cast(SandboxCompanyInfoVerifier, verifier),
        coordinator=cast(
            object,
            SimpleNamespace(
                oauth=SimpleNamespace(credential_reference=provider.CLIENT_REFERENCE)
            ),
        ),
        diagnostics=cast(object, SimpleNamespace()),
        token_reference=provider.TOKEN_REFERENCE,
    )

    evidence = await runtime.connection_evidence()

    assert evidence["connection_state"] == "connected"
    assert evidence["company_info_readability"] == "verified_at_oauth_connection"
    assert evidence["acquisition_eligible"] is True
    assert evidence["credential_state"] == "verified_production_client"
    assert evidence["token_realm_binding"] == "verified"
    assert evidence["refresh_authority"] == "access_token_current"
    assert len(str(evidence["company_identity_sha256"])) == 64
    assert "Exact Company" not in json.dumps(evidence)


@pytest.mark.asyncio
async def test_runtime_connection_evidence_rejects_token_realm_conflict(
    tmp_path: Path,
) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text("present")

    class Secrets:
        async def get_client_credential(self, reference: str) -> object:
            assert reference == "qbo-production/client"
            return object()

        async def get_token(self, reference: str) -> OAuthToken:
            assert reference == "qbo-production/token"
            return _token("different-realm")

    registry = SandboxConnectionRegistry(tmp_path / "connections", "production")
    registry.record_verified(
        realm_id="realm-123",
        company_info_id="company-456",
        company_name="Exact Company",
        minor_version=75,
    )
    secrets = Secrets()
    secrets.token_path = token_path  # type: ignore[attr-defined]
    runtime = SandboxOAuthRuntime(
        callback=cast(object, SimpleNamespace()),
        verifier=cast(
            SandboxCompanyInfoVerifier,
            SimpleNamespace(
                secrets_provider=secrets,
                registry=registry,
                environment=IntuitEnvironment.PRODUCTION,
            ),
        ),
        coordinator=cast(
            object,
            SimpleNamespace(
                oauth=SimpleNamespace(credential_reference="qbo-production/client")
            ),
        ),
        diagnostics=cast(object, SimpleNamespace()),
        token_reference="qbo-production/token",
    )

    with pytest.raises(SandboxRuntimeError, match="token_realm_conflict"):
        await runtime.connection_evidence()


def test_production_configuration_requires_exact_isolated_preview_contract(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="must match Preview exactly"):
        Settings(
            environment="test",
            qbo_production_enabled=True,
            qbo_production_callback_uri="https://example.test/callback",
            qbo_production_runtime_root=str(tmp_path / "runtime"),
            qbo_production_evidence_root=str(tmp_path / "evidence"),
        )


@pytest.mark.asyncio
async def test_acquisition_requires_verified_connection_before_any_query(
    tmp_path: Path,
) -> None:
    configuration = Settings(
        environment="test",
        qbo_production_enabled=True,
        qbo_production_callback_uri=(
            "https://preview.allcountyhomeservices.com"
            "/api/v1/integrations/qbo/production/oauth/callback"
        ),
        qbo_production_runtime_root=str(tmp_path / "runtime"),
        qbo_production_evidence_root=str(tmp_path / "evidence"),
        qbo_repository_root=str(tmp_path / "repository"),
    )
    Path(configuration.qbo_repository_root).mkdir()
    binding = ProtectedSandboxCompanyBinding(
        Path(configuration.qbo_production_runtime_root) / "configuration"
    )
    os.chmod(Path(configuration.qbo_production_runtime_root), 0o700)
    binding.path.write_text("Exact Company")
    os.chmod(binding.path, 0o600)

    with pytest.raises(SandboxRuntimeError, match="connection_not_verified"):
        await execute_production_acquisition(
            ProductionAcquisitionCommand("real-run", date(2026, 8, 25)), configuration
        )

    assert not Path(configuration.qbo_production_evidence_root).exists()


def test_production_scope_is_exact_existing_contract_catalog() -> None:
    assert PRODUCTION_ACQUISITION_SCOPE == tuple(EntityKind)
    assert PRODUCTION_READ_PROBE_SCOPE == (EntityKind.COMPANY_INFO,)


@pytest.mark.asyncio
async def test_read_probe_requires_verified_connection_before_companyinfo(
    tmp_path: Path,
) -> None:
    configuration = Settings(
        environment="test",
        qbo_production_enabled=True,
        qbo_production_callback_uri=(
            "https://preview.allcountyhomeservices.com"
            "/api/v1/integrations/qbo/production/oauth/callback"
        ),
        qbo_production_runtime_root=str(tmp_path / "runtime"),
        qbo_production_evidence_root=str(tmp_path / "evidence"),
        qbo_repository_root=str(tmp_path / "repository"),
    )
    Path(configuration.qbo_repository_root).mkdir()
    binding = ProtectedSandboxCompanyBinding(
        Path(configuration.qbo_production_runtime_root) / "configuration"
    )
    os.chmod(Path(configuration.qbo_production_runtime_root), 0o700)
    binding.path.write_text("Exact Company")
    os.chmod(binding.path, 0o600)

    with pytest.raises(SandboxRuntimeError, match="connection_not_verified"):
        await execute_production_read_probe(
            ProductionAcquisitionCommand(
                f"{PRODUCTION_READ_PROBE_PREFIX}20260911-001",
                date(2026, 9, 11),
            ),
            configuration,
        )

    assert not Path(configuration.qbo_production_evidence_root).exists()


@pytest.mark.asyncio
async def test_read_probe_and_full_acquisition_cannot_share_run_namespace() -> None:
    with pytest.raises(ValueError, match="requires company-info-probe"):
        await execute_production_read_probe(
            ProductionAcquisitionCommand("full-run", date(2026, 9, 11))
        )


@pytest.mark.asyncio
async def test_read_probe_seals_only_companyinfo_without_false_empty_families(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.qbo_source import production

    repository = tmp_path / "repository"
    repository.mkdir()
    runtime = tmp_path / "runtime"
    evidence = tmp_path / "evidence"
    configuration = Settings(
        environment="test",
        qbo_production_enabled=True,
        qbo_production_callback_uri=(
            "https://preview.allcountyhomeservices.com"
            "/api/v1/integrations/qbo/production/oauth/callback"
        ),
        qbo_production_runtime_root=str(runtime),
        qbo_production_evidence_root=str(evidence),
        qbo_repository_root=str(repository),
    )
    company = ProtectedSandboxCompanyBinding(runtime / "configuration")
    os.chmod(runtime, 0o700)
    company.path.write_text("Exact Company")
    os.chmod(company.path, 0o600)
    SandboxConnectionRegistry(runtime / "connections", "production").record_verified(
        realm_id="123456789",
        company_info_id="native-company-id",
        company_name="Exact Company",
        minor_version=75,
    )
    provider = ProtectedProductionSecretProvider(
        root=runtime / "secrets", repository_root=repository
    )
    await provider.put_token(
        provider.TOKEN_REFERENCE, _token(), expected_generation=None
    )
    transport = _ProductionProbeTransport()
    monkeypatch.setattr(production, "IntuitHttpTransport", lambda: transport)

    run_id = f"{PRODUCTION_READ_PROBE_PREFIX}20260911-actual-read"
    result = await execute_production_read_probe(
        ProductionAcquisitionCommand(run_id, date(2026, 9, 11)), configuration
    )

    manifest = json.loads((evidence / "runs" / run_id / "manifest.json").read_text())
    assert result.state.value == "complete"
    assert result.envelope_count == 1
    assert result.bounded_snapshot is None
    assert manifest["entity_counts"] == {"company_info": 1}
    assert not (evidence / "runs" / run_id / "bounded-manifest.json").exists()
    assert transport.urls == [
        "https://quickbooks.api.intuit.com/v3/company/123456789/companyinfo/123456789?minorversion=75"
    ]
    assert transport.client.closed is True
    with pytest.raises(ValueError, match="cannot reuse a read-probe"):
        await execute_production_acquisition(
            ProductionAcquisitionCommand(
                f"{PRODUCTION_READ_PROBE_PREFIX}20260911-001",
                date(2026, 9, 11),
            )
        )


def test_operator_cli_returns_nonzero_for_sealed_partial_evidence(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.qbo_source import production

    monkeypatch.setattr(
        production,
        "run_read_probe",
        lambda command: AcquisitionResult(
            run_id=command.run_id,
            state=RunState.PARTIAL,
            envelope_count=0,
            manifest_sha256="a" * 64,
            failure_code="api_authorization_rejected",
        ),
    )

    status_code = production.main(
        [
            "--run-id",
            f"{PRODUCTION_READ_PROBE_PREFIX}partial",
            "--cutoff",
            "2026-09-11",
            "--company-info-only",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert status_code == 2
    assert output["state"] == "partial"
    assert output["failure_code"] == "api_authorization_rejected"


def test_operator_cli_returns_zero_only_for_complete_evidence(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.qbo_source import production

    monkeypatch.setattr(
        production,
        "run_read_probe",
        lambda command: AcquisitionResult(
            run_id=command.run_id,
            state=RunState.COMPLETE,
            envelope_count=1,
            manifest_sha256="b" * 64,
            failure_code=None,
        ),
    )

    status_code = production.main(
        [
            "--run-id",
            f"{PRODUCTION_READ_PROBE_PREFIX}complete",
            "--cutoff",
            "2026-09-11",
            "--company-info-only",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert status_code == 0
    assert output["state"] == "complete"
    assert output["failure_code"] is None


def test_production_callback_query_logging_is_suppressed() -> None:
    repository = Path(__file__).parents[3]
    nginx = (repository / "frontend/nginx.preview.conf").read_text()
    location = nginx.split(
        "location = /api/v1/integrations/qbo/production/oauth/callback {", maxsplit=1
    )[1].split("}", maxsplit=1)[0]
    assert "access_log off;" in location
    assert (
        "rewrite ^ /api/v1/integrations/qbo/production/oauth/callback? break;"
        in location
    )
    assert "X-ACP-QBO-Code $qbo_code" in location
    caddy = (repository / "docs/deployment/mission-control-preview.caddy").read_text()
    assert "/api/v1/integrations/qbo/production/oauth/callback" in caddy
