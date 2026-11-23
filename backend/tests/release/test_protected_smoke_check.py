from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_protected_smoke_requires_a_real_credential_file() -> None:
    source = (ROOT / "scripts" / "protected-smoke-check.py").read_text()
    assert "approved smoke credential file is required" in source
    assert "fixture token" in source
    assert "Authorization" in source


def test_protected_smoke_has_independent_checks_and_denial_contracts() -> None:
    source = (ROOT / "scripts" / "protected-smoke-check.py").read_text()
    for check in ("authentication", "authorization", "tenant-isolation", "routes", "background-services"):
        assert f'"{check}"' in source
    assert "SMOKE_DENIED_COMPANY_ID" in source
    assert "anonymous protected request was not rejected" in source
    assert "cross-tenant request was not denied" in source
    assert 'DEFAULT_AUTHENTICATED_ROUTE = "/api/v1/customers"' in source
    assert 'DEFAULT_AUTHORIZATION_ROUTE = "/api/v1/company-admin/permissions"' in source
