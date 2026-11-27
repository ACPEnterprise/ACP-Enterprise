import json
from pathlib import Path

import pytest

from scripts import protected_smoke_check

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
        "accounting-readonly",
    ):
        assert f'"{check}"' in source
    assert "SMOKE_DENIED_COMPANY_ID" in source
    assert "tenant-scoped identities" in source
    assert "anonymous protected request was not rejected" in source
    assert "cross-tenant request was not denied" in source
    packaged = (ROOT / "backend" / "scripts" / "protected_smoke_check.py").read_text()
    assert "archive-backed aged receivables is unavailable" in packaged
    assert "NO_ADMITTED_NATIVE_REPORTING_CONTEXT" in packaged
    assert '"mutation_authority": "none"' in packaged


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


def test_assembled_acceptance_stages_smoke_token_for_runtime_identity() -> None:
    source = (ROOT / "scripts" / "qualify-application-integration.sh").read_text()

    assert 'SMOKE_CUSTODY_VOLUME="${PROJECT}-smoke-custody"' in source
    assert 'PRINCIPAL_CUSTODY_VOLUME="${PROJECT}-principal-custody"' in source
    assert "docker volume create --label" in source
    assert 'runtime_uid="$(compose run --rm --no-deps backend id -u)"' in source
    assert 'runtime_gid="$(compose run --rm --no-deps backend id -g)"' in source
    assert "cat > /run/acceptance-custody/runtime-smoke-token" in source
    assert 'chown "$CUSTODY_UID:$CUSTODY_GID" /run/acceptance-custody' in source
    assert 'chown "$CUSTODY_UID:$CUSTODY_GID" /run/acp-release' in source
    assert '--user "$runtime_uid:$runtime_gid"' in source
    assert "stat -c %a /run/acceptance-custody/runtime-smoke-token" in source
    assert ":ro" in source


def test_accounting_readonly_smoke_accepts_archive_and_classifies_native_absence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    credential = tmp_path / "token"
    credential.write_text("not-read-by-test")
    monkeypatch.setattr(protected_smoke_check, "secret", lambda _: "token")
    monkeypatch.setattr(
        protected_smoke_check,
        "tenant_binding",
        lambda: ("company", "branch"),
    )

    def request(path: str, *_: object, **__: object) -> tuple[int, bytes]:
        if path.startswith("/api/v1/accounting/source-evidence/qbo?"):
            return 200, json.dumps(
                {
                    "as_of": "2026-11-19",
                    "mutation_authority": "none",
                    "historical_reconciliation": {"source_record_count": 20702},
                }
            ).encode()
        if "aged-receivables" in path:
            return 200, json.dumps(
                {
                    "contract_version": "qbo-source-backed-ar-summary/v1",
                    "net_open_ar": "500584.34",
                    "includes_customer_credits_and_unapplied_payments": False,
                    "accepted_as_acp_accounting": False,
                    "mutation_authority": "none",
                }
            ).encode()
        return 404, b'{"detail":"Financial report evidence was not found."}'

    monkeypatch.setattr(protected_smoke_check, "request", request)

    result = protected_smoke_check.check_accounting_readonly(credential)

    assert result == {
        "check": "accounting-readonly",
        "status": "PASS",
        "native_reporting_state": "NO_ADMITTED_NATIVE_REPORTING_CONTEXT",
        "aged_receivables_contract": "qbo-source-backed-ar-summary/v1",
        "source_record_count": "20702",
        "mutation_authority": "none",
    }


def test_accounting_readonly_smoke_fails_when_archive_ar_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    credential = tmp_path / "token"
    credential.write_text("not-read-by-test")
    monkeypatch.setattr(protected_smoke_check, "secret", lambda _: "token")
    monkeypatch.setattr(
        protected_smoke_check,
        "tenant_binding",
        lambda: ("company", "branch"),
    )

    def request(path: str, *_: object, **__: object) -> tuple[int, bytes]:
        if path.startswith("/api/v1/accounting/source-evidence/qbo?"):
            return 200, json.dumps(
                {"as_of": "2026-11-19", "mutation_authority": "none"}
            ).encode()
        return 503, b'{"detail":"temporarily unavailable"}'

    monkeypatch.setattr(protected_smoke_check, "request", request)

    with pytest.raises(
        protected_smoke_check.SmokeBlocked,
        match="archive-backed aged receivables is unavailable",
    ):
        protected_smoke_check.check_accounting_readonly(credential)
