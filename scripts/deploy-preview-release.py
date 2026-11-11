#!/usr/bin/env python3
"""Build and atomically deploy an immutable Preview/Beta release.

This tool is deliberately Preview-only.  It consumes a clean Git worktree as
the source of truth, but materializes releases with ``git archive`` so the
runtime directory never contains ``.git``.  It never invokes Alembic upgrade
commands and never targets the PostgreSQL or Redis services.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from urllib.error import URLError
from urllib.request import urlopen


FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
RELEASE_PREFIX = "enterprise-beta-"
PROJECT_NAME = "acp-enterprise-preview"
DEFAULT_ROOT = Path("/opt/acp-enterprise")
DEFAULT_SERVICES = ("backend",)
ALLOWED_SERVICES = {
    "backend",
    "frontend",
    "identity-delivery-worker",
    "mission-control-api",
    "mission-control-web",
    "worker",
    "factory-control-sync",
}
PROTECTED_SERVICES = {
    "migrate",
    "postgres",
    "redis",
    "qbo-sandbox-init",
    "qbo-production-init",
    "worker-provision",
}
PROFILE_FOR_SERVICE = {
    "mission-control-api": "mission-control",
    "mission-control-web": "mission-control",
    "worker": "worker",
    "factory-control-sync": "factory-control",
}


class DeployError(RuntimeError):
    """A controlled release gate failed."""


@dataclass(frozen=True)
class Release:
    root: Path
    path: Path
    sha: str
    previous_path: Path | None
    previous_link: str | None


def fail(message: str) -> None:
    raise DeployError(message)


def command_text(command: Sequence[str]) -> str:
    return " ".join(subprocess.list2cmdline([part]) for part in command)


def run(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    capture: bool = False,
    quiet_failure: bool = False,
) -> str:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=False,
    )
    if completed.returncode != 0:
        if quiet_failure:
            detail = ""
        else:
            detail = " output was not included to avoid exposing runtime configuration."
        fail(f"command failed ({completed.returncode}): {command_text(command)}.{detail}")
    return completed.stdout if capture and completed.stdout is not None else ""


def git_output(source_root: Path, *arguments: str) -> str:
    return run(("git", "-C", str(source_root), *arguments), capture=True).strip()


def require_source(source_root: Path, sha: str) -> tuple[str, str]:
    if not FULL_SHA.fullmatch(sha):
        fail("--sha must be the exact 40-character lowercase commit SHA")
    source_root = source_root.resolve()
    if not source_root.is_dir():
        fail(f"source root is not a directory: {source_root}")
    try:
        git_root = Path(git_output(source_root, "rev-parse", "--show-toplevel")).resolve()
    except DeployError as exc:
        fail(f"source root is not a Git worktree: {source_root} ({exc})")
    if git_root != source_root:
        fail(f"source root must be the Git worktree root: {git_root}")
    if git_output(source_root, "status", "--porcelain=v1", "--untracked-files=all"):
        fail("source worktree is dirty; refusing to build a release")
    resolved = git_output(source_root, "rev-parse", "--verify", f"{sha}^{{commit}}")
    if resolved != sha:
        fail(f"requested SHA does not resolve exactly: requested {sha}, resolved {resolved}")
    tree = git_output(source_root, "rev-parse", "--verify", f"{sha}^{{tree}}")
    tracked_env = subprocess.run(
        ("git", "-C", str(source_root), "ls-files", "--error-unmatch", ".env.preview"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if tracked_env.returncode == 0:
        fail(".env.preview is tracked by the requested source; runtime secrets cannot be archived")
    for required in ("docker-compose.preview.yml", "backend/Dockerfile.preview", "scripts/verify-beta-connectivity.sh"):
        run(("git", "-C", str(source_root), "cat-file", "-e", f"{sha}:{required}"), quiet_failure=True)
    return resolved, tree


def release_target(root: Path, sha: str) -> Path:
    return root / "releases" / f"{RELEASE_PREFIX}{sha[:8]}"


def assert_preview_root(root: Path) -> tuple[Path, Path]:
    root = root.resolve()
    if "production" in str(root).lower():
        fail("Production paths are not supported by this deployer")
    releases = root / "releases"
    current = root / "current"
    if not releases.is_dir():
        fail(f"release root is missing: {releases}")
    if not current.is_symlink():
        fail(f"{current} must be an atomic symlink")
    resolved = current.resolve(strict=True)
    if resolved.parent != releases.resolve() or not resolved.name.startswith(RELEASE_PREFIX):
        fail(f"current does not point to an enterprise-beta release: {resolved}")
    if not resolved.is_dir() or resolved.is_symlink():
        fail(f"current release is not a real directory: {resolved}")
    return releases, resolved


def assert_bootstrap_root(root: Path) -> tuple[Path, Path]:
    """Validate a clean ACP root without creating or switching anything."""
    raw_root = Path(root)
    if raw_root.is_symlink():
        fail("bootstrap root must not be a symlink")
    root = raw_root.resolve()
    if root.name != "acp-enterprise" or "production" in str(root).lower():
        fail(f"bootstrap root is not an approved non-Production ACP root: {root}")
    current = root / "current"
    if os.path.lexists(current):
        fail(f"clean-root bootstrap refuses an existing current path: {current}")
    releases = root / "releases"
    if releases.is_symlink() or (releases.exists() and not releases.is_dir()):
        fail(f"release directory is not a real directory: {releases}")
    if releases.is_dir() and any(releases.iterdir()):
        fail(f"clean-root bootstrap refuses a non-empty release directory: {releases}")
    return root, releases


def validate_runtime_env(path: Path, *, expected_sha: str | None = None) -> dict[str, str]:
    if not path.is_file() or path.is_symlink():
        fail(f"missing or unsafe runtime config: {path}")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        fail(f"runtime config must not be group/other readable: {path}")
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw or raw.lstrip().startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        values[key.strip()] = value.strip()
    if values.get("COMPOSE_PROJECT_NAME") != PROJECT_NAME:
        fail(f".env.preview must set COMPOSE_PROJECT_NAME={PROJECT_NAME}")
    if values.get("QBO_PRODUCTION_ENABLED", "false").lower() == "true":
        fail("QBO production support is disabled in this Preview-only deployer")
    if expected_sha is not None and values.get("APP_VERSION") != expected_sha:
        fail(f"APP_VERSION is not {expected_sha} in {path}")
    for required in (
        "DATABASE_URL",
        "POSTGRES_PASSWORD",
        "PLATFORM_CONTRACT_EXPECTED_FINGERPRINT",
        "ACCESS_TOKEN_KEYS",
        "SECURITY_TOKEN_HMAC_KEY",
    ):
        if not values.get(required):
            fail(f".env.preview is missing required value: {required}")
    return values


def update_app_version(content: str, sha: str) -> str:
    lines = content.splitlines()
    replaced = False
    output: list[str] = []
    for line in lines:
        if re.match(r"^\s*APP_VERSION=", line):
            if replaced:
                fail(".env.preview contains duplicate APP_VERSION entries")
            output.append(f"APP_VERSION={sha}")
            replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append(f"APP_VERSION={sha}")
    return "\n".join(output) + "\n"


def write_private(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)
    path.chmod(0o600)


def extract_archive(source_root: Path, sha: str, stage: Path) -> None:
    archive_path = stage.parent / f".{stage.name}.tar"
    try:
        with archive_path.open("wb") as archive_file:
            completed = subprocess.run(
                ("git", "-C", str(source_root), "archive", "--format=tar", sha),
                stdout=archive_file,
                stderr=subprocess.PIPE,
                check=False,
                text=False,
            )
        if completed.returncode != 0:
            fail(f"git archive failed for {sha}")
        with tarfile.open(archive_path, "r:") as archive:
            members = archive.getmembers()
            stage_resolved = stage.resolve()
            for member in members:
                member_path = (stage / member.name).resolve()
                if member_path != stage_resolved and stage_resolved not in member_path.parents:
                    fail(f"unsafe path in Git archive: {member.name}")
            archive.extractall(stage, filter="data")
    finally:
        archive_path.unlink(missing_ok=True)
    if (stage / ".git").exists() or (stage / ".git").is_symlink():
        fail("Git metadata appeared in the runtime release")


def copy_runtime_config(previous: Path, stage: Path, sha: str) -> None:
    source = previous / ".env.preview"
    validate_runtime_env(source)
    write_private(stage / ".env.preview", update_app_version(source.read_text(encoding="utf-8"), sha))


def copy_bootstrap_config(source: Path, stage: Path, sha: str) -> None:
    validate_runtime_env(source, expected_sha=sha)
    write_private(stage / ".env.preview", source.read_text(encoding="utf-8"))


def env_values(path: Path) -> dict[str, str]:
    return validate_runtime_env(path)


def compose_command(release: Path, arguments: Sequence[str]) -> list[str]:
    values = env_values(release / ".env.preview")
    return [
        "docker",
        "compose",
        "--project-name",
        values["COMPOSE_PROJECT_NAME"],
        "--env-file",
        str(release / ".env.preview"),
        "-f",
        str(release / "docker-compose.preview.yml"),
        *arguments,
    ]


def compose_ids(release: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for service in ("postgres", "redis"):
        output = run(compose_command(release, ("ps", "-q", service)), capture=True)
        identifier = output.strip().splitlines()[-1] if output.strip() else ""
        if not identifier:
            fail(f"{service} is not running; refusing an application-only release")
        result[service] = identifier
    return result


def selected_services(values: Sequence[str] | None) -> tuple[str, ...]:
    services = tuple(dict.fromkeys(values or DEFAULT_SERVICES))
    protected = sorted(set(services) & PROTECTED_SERVICES)
    if protected:
        fail(f"stateful/migration service(s) are forbidden: {', '.join(protected)}")
    unknown = sorted(set(services) - ALLOWED_SERVICES)
    if unknown:
        fail(f"unsupported application service(s): {', '.join(unknown)}")
    if "backend" not in services:
        fail("backend must be included so APP_VERSION, schema, and health gates remain authoritative")
    return services


def profile_args(services: Sequence[str]) -> list[str]:
    return [item for profile in sorted({PROFILE_FOR_SERVICE[s] for s in services if s in PROFILE_FOR_SERVICE}) for item in ("--profile", profile)]


def validate_compose(release: Path, *, dry_run: bool) -> None:
    if not (release / "docker-compose.preview.yml").is_file():
        fail(f"missing docker-compose.preview.yml in {release}")
    validate_runtime_env(release / ".env.preview")
    if dry_run:
        return
    run(compose_command(release, ("config", "--quiet")))


def write_metadata(
    release: Release, release_name: str, tree: str, services: Sequence[str]
) -> None:
    metadata = {
        "format": "acp-preview-release/v1",
        "environment": "preview",
        "release": release_name,
        "app_version": release.sha,
        "tree": tree,
        "runtime_files": [".env.preview"],
        "services": list(services),
        "previous_current_target": release.previous_link,
        "previous_release": str(release.previous_path) if release.previous_path else None,
    }
    write_private(release.path / ".release-metadata.json", json.dumps(metadata, indent=2, sort_keys=True) + "\n")


def atomic_switch(root: Path, target: Path) -> None:
    current = root / "current"
    temporary = root / f".current.{uuid.uuid4().hex}.tmp"
    relative_target = os.path.relpath(target, root)
    os.symlink(relative_target, temporary)
    try:
        os.replace(temporary, current)
        directory_fd = os.open(root, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def release_sha(release: Path) -> str:
    if not release.name.startswith(RELEASE_PREFIX):
        fail(f"not an enterprise-beta release: {release}")
    values = validate_runtime_env(release / ".env.preview")
    sha = values.get("APP_VERSION", "")
    if not FULL_SHA.fullmatch(sha) or release.name != f"{RELEASE_PREFIX}{sha[:8]}":
        fail(f"release name and APP_VERSION do not agree: {release}")
    if (release / ".git").exists() or (release / ".git").is_symlink():
        fail(f"runtime release contains Git metadata: {release}")
    return sha


def wait_for_backend(release: Path, timeout: int) -> None:
    deadline = time.monotonic() + timeout
    last = "unknown"
    while time.monotonic() < deadline:
        output = run(compose_command(release, ("ps", "-q", "backend")), capture=True)
        identifier = output.strip().splitlines()[-1] if output.strip() else ""
        if identifier:
            status_output = run(("docker", "inspect", "--format", "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}", identifier), capture=True)
            last = status_output.strip()
            if last == "healthy":
                return
        time.sleep(2)
    fail(f"backend did not become healthy within {timeout}s (last state: {last})")


def verify_http(release: Path, sha: str) -> None:
    values = env_values(release / ".env.preview")
    port = values.get("PREVIEW_HTTP_PORT", "8080")
    if not port.isdigit():
        fail("PREVIEW_HTTP_PORT must be numeric")
    url = f"http://127.0.0.1:{port}/backend-health"
    try:
        with urlopen(url, timeout=15) as response:
            if response.status != 200:
                fail(f"backend health returned HTTP {response.status}")
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError) as exc:
        fail(f"backend health verification failed: {exc}")
    if payload.get("status") != "healthy" or payload.get("version") != sha:
        fail("backend health is not healthy at the requested APP_VERSION")


def verify_schema(release: Path) -> None:
    current = run(compose_command(release, ("exec", "-T", "backend", "alembic", "current")), capture=True)
    heads = run(compose_command(release, ("exec", "-T", "backend", "alembic", "heads")), capture=True)
    run(compose_command(release, ("exec", "-T", "backend", "alembic", "check")))
    revision = re.compile(r"(?m)^([a-z0-9]+)(?:\s|$)")
    current_revisions = revision.findall(current)
    head_revisions = revision.findall(heads)
    if len(current_revisions) != 1 or len(head_revisions) != 1 or current_revisions != head_revisions:
        fail("Alembic current/head mismatch")
    if "(head)" not in current:
        fail("Alembic current is not marked head")


def verify_stateful_ids(release: Path, before: dict[str, str]) -> None:
    after = compose_ids(release)
    for service in ("postgres", "redis"):
        if after[service] != before[service]:
            fail(f"{service} container identity changed during application-only deployment")


def verify_beta(release: Path) -> None:
    verifier = release / "scripts" / "verify-beta-connectivity.sh"
    if not verifier.is_file():
        fail(f"missing Beta connectivity verifier: {verifier}")
    run(("sh", str(verifier)))


def verify_release(release: Path, sha: str, before_ids: dict[str, str], timeout: int, *, beta: bool = True) -> None:
    wait_for_backend(release, timeout)
    verify_http(release, sha)
    verify_schema(release)
    verify_stateful_ids(release, before_ids)
    if beta:
        verify_beta(release)


def recreate(release: Path, services: Sequence[str]) -> None:
    run(compose_command(release, (*profile_args(services), "up", "-d", "--no-deps", "--force-recreate", "--no-build", *services)))


def build(release: Path, services: Sequence[str]) -> None:
    run(compose_command(release, (*profile_args(services), "build", *services)))


def build_release(
    source_root: Path,
    root: Path,
    sha: str,
    previous: Path,
    previous_link: str,
    tree: str,
    services: Sequence[str],
) -> tuple[Release, Path]:
    target = release_target(root, sha)
    if os.path.lexists(target):
        fail(f"conflicting target release already exists: {target}")
    stage = root / "releases" / f".{target.name}.tmp-{uuid.uuid4().hex}"
    stage.mkdir(mode=0o755)
    try:
        extract_archive(source_root, sha, stage)
        copy_runtime_config(previous, stage, sha)
        release = Release(root, stage, sha, previous, previous_link)
        write_metadata(release, target.name, tree, services)
        return release, target
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def build_bootstrap_release(
    source_root: Path,
    root: Path,
    sha: str,
    tree: str,
    env_file: Path,
    services: Sequence[str],
) -> tuple[Release, Path]:
    target = release_target(root, sha)
    if os.path.lexists(target):
        fail(f"conflicting target release already exists: {target}")
    releases = root / "releases"
    releases.mkdir(mode=0o755, parents=True, exist_ok=True)
    stage = releases / f".{target.name}.tmp-{uuid.uuid4().hex}"
    stage.mkdir(mode=0o755)
    try:
        extract_archive(source_root, sha, stage)
        copy_bootstrap_config(env_file, stage, sha)
        release = Release(root, stage, sha, None, None)
        write_metadata(release, target.name, tree, services)
        return release, target
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def bootstrap(args: argparse.Namespace) -> int:
    source_root = Path(args.source_root).resolve()
    root, releases = assert_bootstrap_root(Path(args.root))
    services = selected_services(args.service)
    sha, tree = require_source(source_root, args.sha)
    env_file = Path(args.env_file).resolve()
    validate_runtime_env(env_file, expected_sha=sha)
    target = release_target(root, sha)
    if os.path.lexists(target):
        fail(f"conflicting target release already exists: {target}")
    if args.dry_run:
        print(f"DRY-RUN: clean-root source={source_root} sha={sha} tree={tree}")
        print(f"DRY-RUN: env-file={env_file} mode-safe APP_VERSION={sha}")
        print(f"DRY-RUN: target={target}")
        print(f"DRY-RUN: current would atomically point to {target}")
        print(f"DRY-RUN: services={','.join(services)} (none will start)")
        print("DRY-RUN: PostgreSQL, Redis, migrations, HCP, QBO, Production, and DNS are untouched.")
        return 0
    releases.mkdir(mode=0o755, parents=True, exist_ok=True)
    release, target = build_bootstrap_release(
        source_root, root, sha, tree, env_file, services
    )
    finalized = False
    try:
        validate_compose(release.path, dry_run=False)
        os.replace(release.path, target)
        finalized = True
        atomic_switch(root, target)
    except Exception as exc:
        current = root / "current"
        if not finalized:
            shutil.rmtree(release.path, ignore_errors=True)
        elif not (current.is_symlink() and current.resolve() == target):
            shutil.rmtree(target, ignore_errors=True)
        raise DeployError(str(exc)) from exc
    print(f"Bootstrapped Preview/Beta release: {target}")
    print(f"APP_VERSION={sha}")
    print("No PostgreSQL, Redis, migration, application, HCP, QBO, Production, or DNS action was performed.")
    return 0


def deploy(args: argparse.Namespace) -> int:
    source_root = Path(args.source_root).resolve()
    root = Path(args.root).resolve()
    services = selected_services(args.service)
    sha, tree = require_source(source_root, args.sha)
    _, previous = assert_preview_root(root)
    previous_link = os.readlink(root / "current")
    previous_sha = release_sha(previous)
    if previous_sha == sha:
        fail("requested SHA is already the active release")
    target = release_target(root, sha)
    if os.path.lexists(target):
        fail(f"conflicting target release already exists: {target}")
    validate_runtime_env(previous / ".env.preview")
    if args.dry_run:
        print(f"DRY-RUN: source={source_root} sha={sha} tree={tree}")
        print(f"DRY-RUN: target={target}")
        print(f"DRY-RUN: previous={previous} ({previous_link})")
        print(f"DRY-RUN: services={','.join(services)}")
        print("DRY-RUN: would archive tracked source, copy .env.preview, validate Compose, build application images, atomically switch current, recreate application services, and verify.")
        print("DRY-RUN: PostgreSQL, Redis, migrations, and Production are untouched.")
        return 0
    before_ids = compose_ids(previous)
    release, target = build_release(
        source_root, root, sha, previous, previous_link, tree, services
    )
    finalized = False
    try:
        validate_compose(release.path, dry_run=False)
        build(release.path, services)
        os.replace(release.path, target)
        finalized = True
        atomic_switch(root, target)
        recreate(target, services)
        verify_release(target, sha, before_ids, args.health_timeout)
    except Exception as exc:
        if not finalized:
            shutil.rmtree(release.path, ignore_errors=True)
        if (root / "current").resolve() == target:
            print("Release verification failed; attempting application-only rollback.", file=sys.stderr)
            try:
                build(previous, services)
                atomic_switch(root, previous)
                recreate(previous, services)
                verify_release(previous, previous_sha, before_ids, args.health_timeout, beta=False)
                print(f"Rollback completed to {previous}", file=sys.stderr)
            except Exception as rollback_exc:
                print(f"AUTOMATIC ROLLBACK FAILED: {rollback_exc}", file=sys.stderr)
        raise DeployError(str(exc)) from exc
    print(f"Deployed Preview/Beta release: {target}")
    print(f"APP_VERSION={sha}")
    print(f"Rollback: {Path(sys.argv[0]).resolve()} rollback --root {root} --to {previous}")
    return 0


def rollback(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    _, current = assert_preview_root(root)
    current_sha = release_sha(current)
    target = Path(args.to).resolve() if args.to else None
    if target is None:
        metadata_path = current / ".release-metadata.json"
        if not metadata_path.is_file():
            fail("current release has no rollback metadata; pass --to explicitly")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        previous = metadata.get("previous_release")
        if not previous:
            fail("current release has no previous release target")
        target = Path(previous).resolve()
    releases = (root / "releases").resolve()
    if target.parent != releases or not target.name.startswith(RELEASE_PREFIX) or not target.is_dir():
        fail(f"rollback target must be an existing enterprise-beta release: {target}")
    target_sha = release_sha(target)
    if target == current:
        fail("rollback target is already current")
    services = selected_services(args.service)
    validate_compose(target, dry_run=args.dry_run)
    if args.dry_run:
        print(f"DRY-RUN: rollback current={current} ({current_sha}) to={target} ({target_sha})")
        print(f"DRY-RUN: services={','.join(services)}; PostgreSQL, Redis, migrations, and Production are untouched.")
        return 0
    before_ids = compose_ids(current)
    try:
        build(target, services)
        atomic_switch(root, target)
        recreate(target, services)
        verify_release(target, target_sha, before_ids, args.health_timeout, beta=True)
    except Exception as exc:
        if (root / "current").resolve() == target:
            try:
                build(current, services)
                atomic_switch(root, current)
                recreate(current, services)
            except Exception as rollback_exc:
                print(f"ROLLBACK-OF-ROLLBACK FAILED: {rollback_exc}", file=sys.stderr)
        raise DeployError(str(exc)) from exc
    print(f"Rolled back Preview/Beta release to: {target}")
    print(f"APP_VERSION={target_sha}")
    return 0


def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    common.add_argument("--health-timeout", type=int, default=180)
    common.add_argument("--dry-run", action="store_true")
    command_parser = argparse.ArgumentParser(description=__doc__)
    subparsers = command_parser.add_subparsers(dest="command", required=True)
    deploy_parser = subparsers.add_parser("deploy", parents=[common])
    deploy_parser.add_argument("--sha", required=True)
    deploy_parser.add_argument("--source-root", type=Path, default=Path.cwd())
    deploy_parser.add_argument(
        "--service",
        action="append",
        help="application service; repeatable, backend is required",
    )
    rollback_parser = subparsers.add_parser("rollback", parents=[common])
    rollback_parser.add_argument("--to", type=Path)
    rollback_parser.add_argument(
        "--service",
        action="append",
        help="application service; repeatable, backend is required",
    )
    bootstrap_parser = subparsers.add_parser("bootstrap", parents=[common])
    bootstrap_parser.add_argument("--source-root", type=Path, required=True)
    bootstrap_parser.add_argument("--sha", required=True)
    bootstrap_parser.add_argument("--env-file", type=Path, required=True)
    bootstrap_parser.add_argument(
        "--service",
        action="append",
        required=True,
        help="application service; repeatable, backend is required",
    )
    return command_parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        if args.command == "deploy":
            return deploy(args)
        if args.command == "rollback":
            return rollback(args)
        return bootstrap(args)
    except DeployError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
