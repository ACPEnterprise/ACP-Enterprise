from __future__ import annotations

import importlib.machinery
import importlib.util
from argparse import Namespace
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[3] / "scripts" / "platform-resilience"
loader = importlib.machinery.SourceFileLoader("platform_resilience", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)


def test_nonproduction_environment_gate() -> None:
    for environment in ("development", "test", "preview-isolated"):
        module.require_nonproduction(environment)
    with pytest.raises(ValueError, match="not an approved isolated"):
        module.require_nonproduction("production")


def test_database_url_never_returns_password_in_arguments() -> None:
    arguments, environment = module.database_parts(
        "postgresql+asyncpg://operator:protected@db:5544/acp"
    )
    assert arguments == [
        "--host",
        "db",
        "--port",
        "5544",
        "--username",
        "operator",
        "--dbname",
        "acp",
    ]
    assert environment["PGPASSWORD"] == "protected"
    assert "protected" not in " ".join(arguments)


def test_restore_refuses_wrong_identity_before_running(tmp_path, monkeypatch) -> None:
    backup = tmp_path / "backup.dump"
    backup.write_bytes(b"safe synthetic backup")
    backup.chmod(0o600)
    manifest = {
        "backup_file": backup.name,
        "contract_version": "platform-resilience.backup.v1",
        "environment": "test",
        "database_identity": "source-a",
        "format": "postgresql-custom",
        "size_bytes": backup.stat().st_size,
        "sha256": module.sha256(backup),
    }
    manifest_path = backup.with_suffix(".dump.manifest.json")
    manifest_path.write_text(
        __import__("json").dumps(manifest)
    )
    manifest_path.chmod(0o600)
    monkeypatch.setattr(module, "run", lambda *_args, **_kwargs: "")
    with pytest.raises(ValueError, match="does not match"):
        module.restore(
            Namespace(
                environment="test",
                target_identity="isolated-target",
                backup=str(backup),
                expected_source_identity="source-b",
                database_url="postgresql://u:p@db/acp_resilience_restore_test",
            )
        )


def test_restore_refuses_authoritative_database_name(tmp_path) -> None:
    with pytest.raises(ValueError, match="acp_resilience_restore"):
        module.restore(
            Namespace(
                environment="test",
                target_identity="isolated-target",
                backup=str(tmp_path / "missing.dump"),
                expected_source_identity="source",
                database_url="postgresql://u:p@db/acp_enterprise_preview",
            )
        )


def test_corrupt_backup_fails_checksum_before_restore(tmp_path, monkeypatch) -> None:
    backup = tmp_path / "backup.dump"
    backup.write_bytes(b"original")
    backup.chmod(0o600)
    manifest = {
        "backup_file": backup.name,
        "contract_version": "platform-resilience.backup.v1",
        "format": "postgresql-custom",
        "size_bytes": backup.stat().st_size,
        "sha256": module.sha256(backup),
    }
    manifest_path = backup.with_suffix(".dump.manifest.json")
    manifest_path.write_text(
        __import__("json").dumps(manifest)
    )
    manifest_path.chmod(0o600)
    backup.write_bytes(b"tampered")
    monkeypatch.setattr(module, "run", lambda *_args, **_kwargs: "")
    with pytest.raises(ValueError, match="checksum"):
        module.load_verified(backup)


def test_restore_refuses_nonempty_target_before_pg_restore(tmp_path, monkeypatch) -> None:
    backup = tmp_path / "backup.dump"
    backup.write_bytes(b"safe synthetic backup")
    backup.chmod(0o600)
    manifest = {
        "backup_file": backup.name,
        "contract_version": "platform-resilience.backup.v1",
        "database_identity": "source-a",
        "environment": "test",
        "format": "postgresql-custom",
        "sha256": module.sha256(backup),
        "size_bytes": backup.stat().st_size,
    }
    manifest_path = backup.with_suffix(".dump.manifest.json")
    manifest_path.write_text(__import__("json").dumps(manifest))
    manifest_path.chmod(0o600)

    def run(command, **_kwargs):
        return "1" if command[0] == "psql" else ""

    monkeypatch.setattr(module, "run", run)
    with pytest.raises(ValueError, match="not empty"):
        module.restore(
            Namespace(
                environment="test",
                target_identity="isolated-target",
                backup=str(backup),
                expected_source_identity="source-a",
                database_url="postgresql://u:p@db/acp_resilience_restore_test",
            )
        )


def test_release_check_fails_all_inconsistent_release_dimensions(capsys) -> None:
    args = Namespace(
        expected_backend_sha="a",
        actual_backend_sha="b",
        expected_frontend_sha="a",
        actual_frontend_sha="c",
        expected_mission_control_sha="a",
        actual_mission_control_sha="d",
        expected_schema_head=["h1"],
        actual_schema_head=["h2"],
    )
    with pytest.raises(SystemExit) as failure:
        module.release_check(args)
    assert failure.value.code == 2
    output = capsys.readouterr().out
    assert "BACKEND_SHA_MISMATCH" in output
    assert "FRONTEND_SHA_MISMATCH" in output
    assert "MISSION_CONTROL_SHA_MISMATCH" in output
    assert "SCHEMA_MISMATCH" in output


def test_release_check_accepts_one_coherent_mission_control_release(capsys) -> None:
    args = Namespace(
        expected_backend_sha="a",
        actual_backend_sha="a",
        expected_frontend_sha="a",
        actual_frontend_sha="a",
        expected_mission_control_sha="b",
        actual_mission_control_sha="b",
        expected_schema_head=["h1"],
        actual_schema_head=["h1"],
    )

    module.release_check(args)

    output = capsys.readouterr().out
    assert '"ready": true' in output
    assert '"state": "HEALTHY"' in output
