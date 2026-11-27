from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import stat
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from development_factory.reports import redact

CONTRACT: Final = "enterprise-ci-artifacts/v1"
SHA40: Final = re.compile(r"[0-9a-f]{40}")
SHA64: Final = re.compile(r"[0-9a-f]{64}")
SECRET_LIKE: Final = re.compile(
    r"(?i)(authorization|bearer|credential|database[_-]?url|password|"
    r"private[_-]?key|secret|token)"
)
DEPENDENCY_PATHS: Final = (
    ".node-version",
    "backend/requirements.txt",
    "backend/requirements-dev.txt",
    "frontend/package-lock.json",
    "mobile/package-lock.json",
)
CONFIGURATION_PATHS: Final = (
    ".node-version",
    ".dockerignore",
    "backend/Dockerfile",
    "frontend/Dockerfile",
    "docker-compose.yml",
    "docker-compose.preview.yml",
    "docker-compose.production.yml",
    "docker-compose.release-qualification.yml",
)
APPLICATION_PATHS: Final = (
    ".node-version",
    "backend/alembic",
    "backend/app",
    "backend/Dockerfile",
    "backend/requirements.txt",
    "frontend/Dockerfile",
    "frontend/package-lock.json",
    "frontend/package.json",
    "frontend/public",
    "frontend/src",
    "mobile/package-lock.json",
    "mobile/package.json",
    "mobile/src",
)
TOOLING_PATHS: Final = (
    "backend/development_factory",
    "backend/scripts",
    "development-factory",
    "scripts",
)
ARTIFACTS: Final = {
    "application": ("application.tar.gz", "twelvehats-application", APPLICATION_PATHS),
    "tooling": ("tooling.tar.gz", "twelvehats-tooling", TOOLING_PATHS),
}


class CIArtifactError(ValueError):
    """Fail-closed immutable CI artifact error."""


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_bytes(repository: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=False,
        capture_output=True,
    )
    if completed.returncode:
        reason = redact(completed.stderr.decode(errors="replace").strip())
        raise CIArtifactError(f"Git command failed: {reason or 'unknown error'}")
    return completed.stdout


def resolve_candidate(repository: Path, candidate_sha: str) -> tuple[str, str]:
    if not SHA40.fullmatch(candidate_sha):
        raise CIArtifactError("candidate SHA must be a full lowercase Git SHA")
    resolved = git_bytes(
        repository, "rev-parse", "--verify", f"{candidate_sha}^{{commit}}"
    )
    if resolved.decode().strip() != candidate_sha:
        raise CIArtifactError("candidate SHA did not resolve exactly")
    tree = (
        git_bytes(repository, "rev-parse", f"{candidate_sha}^{{tree}}").decode().strip()
    )
    if not SHA40.fullmatch(tree):
        raise CIArtifactError("candidate tree SHA is invalid")
    return candidate_sha, tree


def committed_file(repository: Path, candidate_sha: str, path: str) -> bytes:
    if path.startswith("/") or ".." in Path(path).parts or SECRET_LIKE.search(path):
        raise CIArtifactError("source identity path is invalid")
    return git_bytes(repository, "show", f"{candidate_sha}:{path}")


def archive_bytes(
    repository: Path,
    candidate_sha: str,
    *,
    prefix: str,
    paths: Sequence[str],
) -> bytes:
    if not paths or any(SECRET_LIKE.search(path) for path in paths):
        raise CIArtifactError("artifact source paths are invalid")
    tar = git_bytes(
        repository,
        "archive",
        "--format=tar",
        f"--prefix={prefix}/",
        candidate_sha,
        "--",
        *paths,
    )
    output = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as stream:
        stream.write(tar)
    return output.getvalue()


def require_output_directory(path: Path) -> Path:
    path = path.resolve()
    if not path.exists():
        path.mkdir(mode=0o700, parents=True)
    if not path.is_dir() or path.is_symlink():
        raise CIArtifactError("artifact output must be a real directory")
    if stat.S_IMODE(path.stat().st_mode) & 0o022:
        raise CIArtifactError("artifact output must not be group/world writable")
    return path


def write_once(path: Path, content: bytes) -> None:
    if path.exists():
        raise CIArtifactError(f"refusing to overwrite immutable artifact {path.name}")
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        path.chmod(0o400)
    finally:
        if descriptor is not None:
            os.close(descriptor)


def source_identities(
    repository: Path, candidate_sha: str, paths: Sequence[str]
) -> dict[str, str]:
    return {
        path: digest_bytes(committed_file(repository, candidate_sha, path))
        for path in paths
    }


def build_ci_artifacts(
    *, repository: Path, output_directory: Path, candidate_sha: str
) -> dict[str, Any]:
    repository = repository.resolve()
    candidate_sha, tree_sha = resolve_candidate(repository, candidate_sha)
    output_directory = require_output_directory(output_directory)
    artifact_records: list[dict[str, Any]] = []
    for role, (filename, prefix, paths) in ARTIFACTS.items():
        content = archive_bytes(
            repository,
            candidate_sha,
            prefix=prefix,
            paths=paths,
        )
        write_once(output_directory / filename, content)
        artifact_records.append(
            {
                "filename": filename,
                "role": role,
                "sha256": digest_bytes(content),
                "size_bytes": len(content),
                "source_paths": list(paths),
            }
        )
    unsigned: dict[str, Any] = {
        "artifacts": artifact_records,
        "candidate_sha": candidate_sha,
        "configuration_sha256": source_identities(
            repository, candidate_sha, CONFIGURATION_PATHS
        ),
        "contract": CONTRACT,
        "dependency_sha256": source_identities(
            repository, candidate_sha, DEPENDENCY_PATHS
        ),
        "deployment_authorized": False,
        "tree_sha": tree_sha,
    }
    manifest = {**unsigned, "manifest_sha256": digest_bytes(canonical(unsigned))}
    write_once(
        output_directory / "ci-artifact-manifest.json",
        json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n",
    )
    return manifest


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise CIArtifactError("CI artifact manifest must be a regular file")
    if stat.S_IMODE(path.stat().st_mode) & 0o022:
        raise CIArtifactError("CI artifact manifest must not be group/world writable")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CIArtifactError("CI artifact manifest is not valid JSON") from error
    if not isinstance(payload, dict):
        raise CIArtifactError("CI artifact manifest must be a JSON object")
    return payload


def verify_ci_artifacts(
    *, repository: Path, manifest_path: Path, candidate_sha: str
) -> dict[str, Any]:
    repository = repository.resolve()
    manifest_path = manifest_path.resolve()
    payload = load_manifest(manifest_path)
    required = {
        "artifacts",
        "candidate_sha",
        "configuration_sha256",
        "contract",
        "dependency_sha256",
        "deployment_authorized",
        "manifest_sha256",
        "tree_sha",
    }
    if set(payload) != required or payload.get("contract") != CONTRACT:
        raise CIArtifactError("CI artifact manifest contract is invalid")
    unsigned = {
        key: value for key, value in payload.items() if key != "manifest_sha256"
    }
    if payload.get("manifest_sha256") != digest_bytes(canonical(unsigned)):
        raise CIArtifactError("CI artifact manifest digest is invalid")
    resolved, tree = resolve_candidate(repository, candidate_sha)
    if payload.get("candidate_sha") != resolved or payload.get("tree_sha") != tree:
        raise CIArtifactError("CI artifact source identity does not match")
    if payload.get("deployment_authorized") is not False:
        raise CIArtifactError("CI artifacts may not authorize deployment")
    expected_dependencies = source_identities(repository, resolved, DEPENDENCY_PATHS)
    expected_configuration = source_identities(
        repository, resolved, CONFIGURATION_PATHS
    )
    if payload.get("dependency_sha256") != expected_dependencies:
        raise CIArtifactError("dependency identity does not match candidate")
    if payload.get("configuration_sha256") != expected_configuration:
        raise CIArtifactError("configuration identity does not match candidate")
    raw_records = payload.get("artifacts")
    if not isinstance(raw_records, list) or len(raw_records) != len(ARTIFACTS):
        raise CIArtifactError("CI artifact set is incomplete")
    by_role = {
        record.get("role"): record for record in raw_records if isinstance(record, dict)
    }
    if set(by_role) != set(ARTIFACTS):
        raise CIArtifactError("CI artifact roles are invalid")
    for role, (filename, prefix, paths) in ARTIFACTS.items():
        record = by_role[role]
        expected_keys = {"filename", "role", "sha256", "size_bytes", "source_paths"}
        if set(record) != expected_keys:
            raise CIArtifactError(f"{role} artifact record is invalid")
        if record.get("filename") != filename or record.get("source_paths") != list(
            paths
        ):
            raise CIArtifactError(f"{role} artifact definition does not match")
        artifact = manifest_path.parent / filename
        if not artifact.is_file() or artifact.is_symlink():
            raise CIArtifactError(f"{role} artifact is missing")
        if stat.S_IMODE(artifact.stat().st_mode) & 0o022:
            raise CIArtifactError(f"{role} artifact is writable by group/world")
        if artifact.stat().st_size != record.get("size_bytes"):
            raise CIArtifactError(f"{role} artifact size does not match")
        observed = digest_file(artifact)
        if not SHA64.fullmatch(str(record.get("sha256", ""))) or observed != record.get(
            "sha256"
        ):
            raise CIArtifactError(f"{role} artifact digest does not match")
        rebuilt = archive_bytes(repository, resolved, prefix=prefix, paths=paths)
        if digest_bytes(rebuilt) != observed:
            raise CIArtifactError(f"{role} artifact is not reproducible")
    return {
        "artifacts_verified": len(ARTIFACTS),
        "candidate_sha": resolved,
        "configuration_files_verified": len(CONFIGURATION_PATHS),
        "dependency_files_verified": len(DEPENDENCY_PATHS),
        "manifest_sha256": payload["manifest_sha256"],
        "reproducible": True,
    }


def safe_error(error: BaseException) -> str:
    return redact(str(error))
