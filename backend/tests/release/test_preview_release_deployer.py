from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / "scripts" / "deploy-preview-release.py"
SPEC = importlib.util.spec_from_file_location("deploy_preview_release", SCRIPT)
assert SPEC and SPEC.loader
deployer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = deployer
SPEC.loader.exec_module(deployer)


def git(root: Path, *arguments: str, check: bool = True) -> str:
    completed = subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip()


def preview_env(sha: str) -> str:
    return "\n".join(
        (
            "COMPOSE_PROJECT_NAME=acp-enterprise-preview",
            "PREVIEW_HTTP_PORT=8080",
            f"APP_VERSION={sha}",
            "DATABASE_URL=postgresql+asyncpg://preview:secret@postgres:5432/preview",
            "POSTGRES_PASSWORD=preview-secret",
            "PLATFORM_CONTRACT_EXPECTED_FINGERPRINT=test-fingerprint",
            'ACCESS_TOKEN_KEYS={"preview":"test-secret"}',
            "SECURITY_TOKEN_HMAC_KEY=test-hmac",
            "QBO_PRODUCTION_ENABLED=false",
        )
    ) + "\n"


def source_repo(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "builder"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "tests@example.invalid")
    git(root, "config", "user.name", "Release Tests")
    (root / "backend").mkdir()
    (root / "scripts").mkdir()
    (root / "backend" / "Dockerfile.preview").write_text("FROM scratch\n")
    (root / "docker-compose.preview.yml").write_text("services: {}\n")
    (root / "scripts" / "verify-beta-connectivity.sh").write_text("#!/bin/sh\nexit 0\n")
    (root / "tracked.txt").write_text("tracked source\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "test release")
    return root, git(root, "rev-parse", "HEAD")


def runtime_root(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "acp-enterprise"
    releases = root / "releases"
    previous = releases / (deployer.RELEASE_PREFIX + "a" * 8)
    previous.mkdir(parents=True)
    env = previous / ".env.preview"
    env.write_text(preview_env("a" * 40))
    env.chmod(0o600)
    (root / "current").symlink_to("releases/enterprise-beta-aaaaaaaa")
    return root, previous


def clean_root(tmp_path: Path, sha: str) -> tuple[Path, Path]:
    root = tmp_path / "acp-enterprise"
    root.mkdir()
    env = tmp_path / ".env.preview"
    env.write_text(preview_env(sha))
    env.chmod(0o600)
    return root, env


def test_git_archive_materializes_source_without_git_and_copies_only_env(tmp_path: Path) -> None:
    source, sha = source_repo(tmp_path)
    root, previous = runtime_root(tmp_path)
    release, target = deployer.build_release(
        source,
        root,
        sha,
        previous,
        os.readlink(root / "current"),
        git(source, "rev-parse", f"{sha}^{{tree}}"),
        ("backend",),
    )

    assert release.path.is_dir()
    assert target.name == f"enterprise-beta-{sha[:8]}"
    assert (release.path / "tracked.txt").read_text() == "tracked source\n"
    assert not (release.path / ".git").exists()
    assert (release.path / ".env.preview").read_text().split("APP_VERSION=", 1)[1].splitlines()[0] == sha
    assert (release.path / ".release-metadata.json").is_file()


def test_dry_run_does_not_create_target_or_switch_current(tmp_path: Path) -> None:
    source, sha = source_repo(tmp_path)
    root, _ = runtime_root(tmp_path)

    assert (
        deployer.main(
            [
                "deploy",
                "--source-root",
                str(source),
                "--root",
                str(root),
                "--sha",
                sha,
                "--dry-run",
            ]
        )
        == 0
    )
    assert os.readlink(root / "current") == "releases/enterprise-beta-aaaaaaaa"
    assert not (root / "releases" / f"enterprise-beta-{sha[:8]}").exists()


def test_clean_root_bootstrap_dry_run_does_not_create_current(
    tmp_path: Path,
) -> None:
    source, sha = source_repo(tmp_path)
    root, env = clean_root(tmp_path, sha)

    assert (
        deployer.main(
            [
                "bootstrap",
                "--source-root",
                str(source),
                "--root",
                str(root),
                "--sha",
                sha,
                "--env-file",
                str(env),
                "--service",
                "backend",
                "--dry-run",
            ]
        )
        == 0
    )
    assert not (root / "current").exists()
    assert not (root / "releases").exists()


def test_clean_root_bootstrap_materializes_and_switches_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, sha = source_repo(tmp_path)
    root, env = clean_root(tmp_path, sha)
    monkeypatch.setattr(deployer, "validate_compose", lambda *_args, **_kwargs: None)

    assert (
        deployer.main(
            [
                "bootstrap",
                "--source-root",
                str(source),
                "--root",
                str(root),
                "--sha",
                sha,
                "--env-file",
                str(env),
                "--service",
                "backend",
            ]
        )
        == 0
    )
    target = root / "releases" / f"enterprise-beta-{sha[:8]}"
    assert target.is_dir()
    assert (root / "current").resolve() == target
    assert not (target / ".git").exists()
    assert (target / ".env.preview").stat().st_mode & 0o777 == 0o600
    assert f"APP_VERSION={sha}" in (target / ".env.preview").read_text()
    assert '"previous_release": null' in (target / ".release-metadata.json").read_text()


def test_dirty_source_is_blocked(tmp_path: Path) -> None:
    source, sha = source_repo(tmp_path)
    (source / "untracked.txt").write_text("dirty\n")
    root, _ = runtime_root(tmp_path)

    assert deployer.main(
        [
            "deploy",
            "--source-root",
            str(source),
            "--root",
            str(root),
            "--sha",
            sha,
            "--dry-run",
        ]
    ) == 1


def test_stateful_and_migration_services_are_blocked() -> None:
    with pytest.raises(deployer.DeployError, match="forbidden"):
        deployer.selected_services(("backend", "postgres"))
    with pytest.raises(deployer.DeployError, match="forbidden"):
        deployer.selected_services(("backend", "migrate"))


def test_atomic_switch_replaces_current_symlink(tmp_path: Path) -> None:
    root, _ = runtime_root(tmp_path)
    target = root / "releases" / "enterprise-beta-bbbbbbbb"
    target.mkdir()
    deployer.atomic_switch(root, target)
    assert os.readlink(root / "current") == "releases/enterprise-beta-bbbbbbbb"


def test_rollback_dry_run_preserves_current_release(tmp_path: Path) -> None:
    root, _ = runtime_root(tmp_path)
    target = root / "releases" / "enterprise-beta-bbbbbbbb"
    target.mkdir()
    (target / ".env.preview").write_text(preview_env("b" * 40))
    (target / ".env.preview").chmod(0o600)
    (target / "docker-compose.preview.yml").write_text("services: {}\n")

    assert (
        deployer.main(
            [
                "rollback",
                "--root",
                str(root),
                "--to",
                str(target),
                "--service",
                "backend",
                "--dry-run",
            ]
        )
        == 0
    )
    assert os.readlink(root / "current") == "releases/enterprise-beta-aaaaaaaa"


def test_backend_only_verification_does_not_require_frontend_or_proxy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(deployer, "wait_for_backend", lambda *_args: calls.append("wait"))
    monkeypatch.setattr(
        deployer,
        "verify_backend_runtime",
        lambda *_args: calls.append("backend"),
    )
    monkeypatch.setattr(deployer, "verify_schema", lambda *_args: calls.append("schema"))
    monkeypatch.setattr(
        deployer,
        "verify_stateful_ids",
        lambda *_args: calls.append("stateful"),
    )
    monkeypatch.setattr(
        deployer,
        "verify_http",
        lambda *_args: calls.append("proxy"),
    )
    monkeypatch.setattr(
        deployer,
        "verify_beta",
        lambda *_args: calls.append("beta"),
    )

    deployer.verify_release(
        tmp_path / "release",
        "a" * 40,
        {"postgres": "postgres", "redis": "redis"},
        1,
        ("backend",),
    )

    assert calls == ["wait", "backend", "schema", "stateful"]


def test_full_stack_verification_keeps_proxy_and_beta_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(deployer, "wait_for_backend", lambda *_args: calls.append("wait"))
    monkeypatch.setattr(
        deployer,
        "verify_backend_runtime",
        lambda *_args: calls.append("backend"),
    )
    monkeypatch.setattr(deployer, "verify_http", lambda *_args: calls.append("proxy"))
    monkeypatch.setattr(deployer, "verify_schema", lambda *_args: calls.append("schema"))
    monkeypatch.setattr(
        deployer,
        "verify_stateful_ids",
        lambda *_args: calls.append("stateful"),
    )
    monkeypatch.setattr(deployer, "verify_beta", lambda *_args: calls.append("beta"))

    deployer.verify_release(
        tmp_path / "release",
        "a" * 40,
        {"postgres": "postgres", "redis": "redis"},
        1,
        ("backend", "frontend"),
    )

    assert calls == ["wait", "backend", "proxy", "schema", "stateful", "beta"]


def test_backend_runtime_rejects_unhealthy_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    responses = iter(("backend-id\n", "running\n", "unhealthy\n"))
    monkeypatch.setattr(deployer, "compose_command", lambda *_args: ("docker", "compose"))
    monkeypatch.setattr(deployer, "run", lambda *_args, **_kwargs: next(responses))

    with pytest.raises(deployer.DeployError, match="not healthy"):
        deployer.verify_backend_runtime(tmp_path / "release", "a" * 40)


def test_backend_runtime_rejects_wrong_app_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    responses = iter(("backend-id\n", "running\n", "healthy\n", "APP_VERSION=" + "b" * 40 + "\n"))
    monkeypatch.setattr(deployer, "compose_command", lambda *_args: ("docker", "compose"))
    monkeypatch.setattr(deployer, "run", lambda *_args, **_kwargs: next(responses))

    with pytest.raises(deployer.DeployError, match="APP_VERSION"):
        deployer.verify_backend_runtime(tmp_path / "release", "a" * 40)


def test_deploy_rolls_back_when_schema_or_health_verification_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, sha = source_repo(tmp_path)
    root, previous = runtime_root(tmp_path)
    monkeypatch.setattr(deployer, "validate_compose", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(deployer, "compose_ids", lambda *_args: {"postgres": "p", "redis": "r"})
    monkeypatch.setattr(deployer, "build", lambda *_args: None)
    monkeypatch.setattr(deployer, "recreate", lambda *_args: None)
    calls = 0

    def fail_target_then_accept_rollback(*_args, **_kwargs) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise deployer.DeployError("schema mismatch")

    monkeypatch.setattr(deployer, "verify_release", fail_target_then_accept_rollback)

    assert deployer.main(
        [
            "deploy",
            "--source-root",
            str(source),
            "--root",
            str(root),
            "--sha",
            sha,
            "--service",
            "backend",
        ]
    ) == 1
    assert calls == 2
    assert (root / "current").resolve() == previous
