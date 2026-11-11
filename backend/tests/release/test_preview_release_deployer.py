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
