from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def module():
    spec = importlib.util.spec_from_file_location(
        "protected_runtime_check", ROOT / "scripts" / "protected-runtime-check.py"
    )
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def runtime(tmp_path: Path) -> Path:
    root = tmp_path / "acp-enterprise"
    current = root / "current"
    current.mkdir(parents=True)
    (current / "docker-compose.preview.yml").write_text("services: {}\n")
    (current / ".release-metadata.json").write_text(
        json.dumps({"app_version": "a" * 40}) + "\n"
    )
    return root


def test_postgres_check_requires_authenticated_identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checked = module()
    root = runtime(tmp_path)
    calls: list[list[str]] = []

    def fake(command: list[str]) -> str:
        calls.append(command)
        if "alembic" in command:
            return "s1a3g5k7m9q2 (head)"
        return "app_user|preview|false"

    monkeypatch.setattr(checked, "run_read_only", fake)
    result = checked.check_postgres(root, "acp-enterprise-preview", "a" * 40, "s1a3g5k7m9q2")

    assert result["status"] == "PASS"
    assert result["superuser"] == "false"
    assert any("pg_isready" in item for command in calls for item in command)


def test_backend_check_is_not_dispatched_to_redis(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checked = module()
    root = runtime(tmp_path)
    calls: list[list[str]] = []

    def fake(command: list[str]) -> str:
        calls.append(command)
        if "alembic" in command:
            return "s1a3g5k7m9q2 (head)"
        return ""

    monkeypatch.setattr(checked, "run_read_only", fake)
    result = checked.check_backend(root, "acp-enterprise-preview", "a" * 40, "s1a3g5k7m9q2")

    assert result["service"] == "backend"
    assert any("127.0.0.1:8000/health" in item for command in calls for item in command)
    assert all("redis" not in item for command in calls for item in command)


def test_database_security_rejects_privileged_role(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checked = module()
    root = runtime(tmp_path)

    def fake(command: list[str]) -> str:
        if "alembic" in command:
            return "s1a3g5k7m9q2 (head)"
        return "true|false|false|false|false|0|0"

    monkeypatch.setattr(checked, "run_read_only", fake)
    with pytest.raises(checked.RuntimeCheckError, match="elevated role privileges"):
        checked.check_database_security(root, "acp-enterprise-preview", "a" * 40, "s1a3g5k7m9q2")


def test_database_security_rejects_missing_forced_rls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checked = module()
    root = runtime(tmp_path)

    def fake(command: list[str]) -> str:
        if "alembic" in command:
            return "s1a3g5k7m9q2 (head)"
        return "false|false|false|false|false|2|1"

    monkeypatch.setattr(checked, "run_read_only", fake)
    with pytest.raises(checked.RuntimeCheckError, match="row-level security"):
        checked.check_database_security(root, "acp-enterprise-preview", "a" * 40, "s1a3g5k7m9q2")


def test_postgres_superuser_state_is_reported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checked = module()
    root = runtime(tmp_path)

    def fake(command: list[str]) -> str:
        return (
            "s1a3g5k7m9q2 (head)"
            if "alembic" in command
            else "postgres|preview|true"
        )

    monkeypatch.setattr(checked, "run_read_only", fake)
    result = checked.check_postgres(root, "acp-enterprise-preview", "a" * 40, "s1a3g5k7m9q2")
    assert result["status"] == "PASS"
    assert result["superuser"] == "true"


def test_redis_check_requires_authenticated_health_secret(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checked = module()
    root = runtime(tmp_path)
    calls: list[list[str]] = []

    def fake(command: list[str]) -> str:
        calls.append(command)
        if "alembic" in command:
            return "s1a3g5k7m9q2 (head)"
        return ""

    monkeypatch.setattr(checked, "run_read_only", fake)
    result = checked.check_redis(root, "acp-enterprise-preview", "a" * 40, "s1a3g5k7m9q2")

    assert result == {"service": "redis", "status": "PASS", "identity": "acp-health"}
    redis_command = " ".join(calls[-1])
    assert "/run/secrets/redis/health-password" in redis_command
    assert "REDISCLI_AUTH=\"$(cat" in redis_command
    assert "ACL WHOAMI" not in redis_command


def test_runtime_identity_mismatch_blocks_before_health(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checked = module()
    root = runtime(tmp_path)
    (root / "current" / ".release-metadata.json").write_text(
        json.dumps({"app_version": "b" * 40}) + "\n"
    )
    called = False

    def fake(_command: list[str]) -> str:
        nonlocal called
        called = True
        return ""

    monkeypatch.setattr(checked, "run_read_only", fake)
    with pytest.raises(checked.RuntimeCheckError, match="application identity mismatch"):
        checked.check_redis(root, "acp-enterprise-preview", "a" * 40, "s1a3g5k7m9q2")
    assert called is False


def test_postgres_failed_health_blocks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checked = module()
    root = runtime(tmp_path)

    def fake(command: list[str]) -> str:
        if "alembic" in command:
            return "s1a3g5k7m9q2 (head)"
        raise checked.RuntimeCheckError("protected health command failed")

    monkeypatch.setattr(checked, "run_read_only", fake)
    with pytest.raises(checked.RuntimeCheckError, match="PostgreSQL authenticated health is unavailable"):
        checked.check_postgres(root, "acp-enterprise-preview", "a" * 40, "s1a3g5k7m9q2")


def test_redis_missing_health_credentials_blocks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checked = module()
    root = runtime(tmp_path)

    def fake(command: list[str]) -> str:
        if "alembic" in command:
            return "s1a3g5k7m9q2 (head)"
        raise checked.RuntimeCheckError("protected health command failed")

    monkeypatch.setattr(checked, "run_read_only", fake)
    with pytest.raises(checked.RuntimeCheckError, match="Redis health credentials or connection are unavailable"):
        checked.check_redis(root, "acp-enterprise-preview", "a" * 40, "s1a3g5k7m9q2")
