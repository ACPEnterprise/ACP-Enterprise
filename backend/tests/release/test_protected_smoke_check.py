from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_protected_smoke_requires_a_real_credential_file() -> None:
    source = (ROOT / "scripts" / "protected-smoke-check.py").read_text()
    assert "approved smoke credential file is required" in source
    assert "fixture token" in source
    assert "Authorization" in source


def test_protected_smoke_has_independent_checks_and_denial_contracts() -> None:
    source = (ROOT / "scripts" / "protected-smoke-check.py").read_text()
    for check in (
        "authentication",
        "authorization",
        "tenant-isolation",
        "routes",
        "background-services",
    ):
        assert f'"{check}"' in source
    assert "SMOKE_DENIED_COMPANY_ID" in source
    assert "anonymous protected request was not rejected" in source
    assert "cross-tenant request was not denied" in source


def test_protected_smoke_is_packaged_and_mounted_with_private_host_custody() -> None:
    packaged = (ROOT / "backend" / "scripts" / "protected_smoke_check.py").read_text()
    compose = (ROOT / "docker-compose.preview.yml").read_text()
    runtime = (ROOT / "scripts" / "protected-runtime-check.py").read_text()

    assert "fixture token" not in packaged
    assert "--credential-file" in packaged
    assert "PREVIEW_SMOKE_TOKEN_FILE_HOST" in compose
    assert ":/run/secrets/preview-smoke-token:ro" in compose
    assert "scripts.protected_smoke_check" in runtime


def test_principal_provisioners_enforce_canonical_writable_custody() -> None:
    actor = (
        ROOT / "backend" / "scripts" / "provision_beta_release_actor.py"
    ).read_text()
    reader = (
        ROOT / "backend" / "scripts" / "provision_acceptance_readonly_principal.py"
    ).read_text()

    assert "/run/acp-release/release-actor/access-token" in actor
    assert "/run/acp-release/acceptance-reader/access-token" in reader
    assert "os.fsync(descriptor)" in actor
    assert "os.fsync(descriptor)" in reader
    assert "/run/secrets/release_actor_token" not in actor
