from __future__ import annotations

import json
import os
import stat
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from app.core.config import Settings
from app.main import app
from app.qbo_source.contracts import EntityKind
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
from app.qbo_source.runtime import (
    ProtectedSandboxCompanyBinding,
    SandboxCompanyInfoVerifier,
    SandboxConnectionRegistry,
    SandboxRuntimeError,
)
from app.qbo_source.secrets import (
    ProtectedProductionSecretProvider,
    ProtectedSandboxSecretProvider,
)
from fastapi.testclient import TestClient


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
