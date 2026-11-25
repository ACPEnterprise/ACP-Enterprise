from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from development_factory.reports import redact

CONTRACT = "enterprise-immutable-release-manifest/v1"
ARTIFACT_ROLES = ("application", "tooling", "migration", "backup", "rollback")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
MIGRATION_HEAD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
RELEASE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
SECRET_LIKE = re.compile(
    r"(?i)(authorization|bearer|credential|database[_-]?url|password|"
    r"private[_-]?key|secret|token)"
)


class ReleaseManifestError(ValueError):
    """A fail-closed, secret-safe release manifest error."""


@dataclass(frozen=True)
class ArtifactRecord:
    role: str
    path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class VerifiedReleaseConfiguration:
    candidate_sha: str
    tooling_sha: str
    migration_head: str
    rollback_target_sha: str
    rollback_target_release: str
    manifest_sha256: str
    artifacts: tuple[ArtifactRecord, ...]


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def canonical_digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate_release_manifest(
    *,
    root: Path,
    output: Path,
    candidate_sha: str,
    tooling_sha: str,
    migration_head: str,
    rollback_target_sha: str,
    rollback_target_release: str,
    artifacts: Mapping[str, Path],
) -> dict[str, Any]:
    """Create a new immutable release manifest without overwriting evidence."""

    _validate_sha(candidate_sha, "candidate SHA")
    _validate_sha(tooling_sha, "tooling SHA")
    _validate_sha(rollback_target_sha, "rollback target SHA")
    _validate_identifier(migration_head, MIGRATION_HEAD, "migration head")
    _validate_identifier(
        rollback_target_release,
        RELEASE_NAME,
        "rollback target release",
    )
    if set(artifacts) != set(ARTIFACT_ROLES):
        raise ReleaseManifestError(
            "artifacts must contain exactly: " + ", ".join(ARTIFACT_ROLES)
        )

    artifact_records = [
        _record_artifact(root, role, artifacts[role]) for role in ARTIFACT_ROLES
    ]
    paths = [record.path for record in artifact_records]
    if len(paths) != len(set(paths)):
        raise ReleaseManifestError("artifact paths must be unique")

    unsigned: dict[str, Any] = {
        "contract": CONTRACT,
        "candidate_sha": candidate_sha,
        "tooling_sha": tooling_sha,
        "migration_head": migration_head,
        "rollback_target": {
            "sha": rollback_target_sha,
            "release": rollback_target_release,
        },
        "artifacts": [record.__dict__ for record in artifact_records],
    }
    manifest = {**unsigned, "manifest_sha256": canonical_digest(unsigned)}
    _write_immutable_json(output, manifest)
    return manifest


def verify_release_manifest(
    path: Path,
    *,
    root: Path,
    candidate_sha: str | None = None,
    tooling_sha: str | None = None,
    migration_head: str | None = None,
    rollback_target_sha: str | None = None,
    rollback_target_release: str | None = None,
) -> VerifiedReleaseConfiguration:
    """Independently verify identity bindings and every artifact byte digest."""

    payload = _load_manifest(path)
    required = {
        "contract",
        "candidate_sha",
        "tooling_sha",
        "migration_head",
        "rollback_target",
        "artifacts",
        "manifest_sha256",
    }
    if set(payload) != required or payload.get("contract") != CONTRACT:
        raise ReleaseManifestError("release manifest contract is invalid")

    manifest_digest = payload.get("manifest_sha256")
    if not isinstance(manifest_digest, str) or not SHA64.fullmatch(manifest_digest):
        raise ReleaseManifestError("release manifest digest is invalid")
    unsigned = {
        key: value for key, value in payload.items() if key != "manifest_sha256"
    }
    if canonical_digest(unsigned) != manifest_digest:
        raise ReleaseManifestError("release manifest digest does not match contents")

    actual_candidate = _manifest_sha(payload, "candidate_sha", "candidate SHA")
    actual_tooling = _manifest_sha(payload, "tooling_sha", "tooling SHA")
    actual_migration = payload.get("migration_head")
    if not isinstance(actual_migration, str):
        raise ReleaseManifestError("migration head is invalid")
    _validate_identifier(actual_migration, MIGRATION_HEAD, "migration head")

    rollback = payload.get("rollback_target")
    if not isinstance(rollback, dict) or set(rollback) != {"sha", "release"}:
        raise ReleaseManifestError("rollback target is invalid")
    actual_rollback_sha = rollback.get("sha")
    actual_rollback_release = rollback.get("release")
    if not isinstance(actual_rollback_sha, str):
        raise ReleaseManifestError("rollback target SHA is invalid")
    if not isinstance(actual_rollback_release, str):
        raise ReleaseManifestError("rollback target release is invalid")
    _validate_sha(actual_rollback_sha, "rollback target SHA")
    _validate_identifier(
        actual_rollback_release,
        RELEASE_NAME,
        "rollback target release",
    )

    _require_binding(candidate_sha, actual_candidate, "candidate SHA")
    _require_binding(tooling_sha, actual_tooling, "tooling SHA")
    _require_binding(migration_head, actual_migration, "migration head")
    _require_binding(
        rollback_target_sha,
        actual_rollback_sha,
        "rollback target SHA",
    )
    _require_binding(
        rollback_target_release,
        actual_rollback_release,
        "rollback target release",
    )

    raw_artifacts = payload.get("artifacts")
    if not isinstance(raw_artifacts, list) or len(raw_artifacts) != len(ARTIFACT_ROLES):
        raise ReleaseManifestError("release manifest artifact set is invalid")
    records = tuple(_parse_artifact(value) for value in raw_artifacts)
    if tuple(record.role for record in records) != ARTIFACT_ROLES:
        raise ReleaseManifestError("release manifest artifact roles are invalid")
    if len({record.path for record in records}) != len(records):
        raise ReleaseManifestError("artifact paths must be unique")
    for record in records:
        actual_path = _resolve_artifact(root, record.path)
        if actual_path.stat().st_size != record.size_bytes:
            raise ReleaseManifestError(f"{record.role} artifact size does not match")
        if file_digest(actual_path) != record.sha256:
            raise ReleaseManifestError(f"{record.role} artifact digest does not match")

    return VerifiedReleaseConfiguration(
        candidate_sha=actual_candidate,
        tooling_sha=actual_tooling,
        migration_head=actual_migration,
        rollback_target_sha=actual_rollback_sha,
        rollback_target_release=actual_rollback_release,
        manifest_sha256=manifest_digest,
        artifacts=records,
    )


def safe_error(error: BaseException) -> str:
    return redact(str(error))


def _record_artifact(root: Path, role: str, path: Path) -> ArtifactRecord:
    relative = _relative_artifact(root, path)
    actual = _resolve_artifact(root, relative)
    return ArtifactRecord(
        role=role,
        path=relative,
        sha256=file_digest(actual),
        size_bytes=actual.stat().st_size,
    )


def _relative_artifact(root: Path, path: Path) -> str:
    root_resolved = root.resolve()
    candidate = path if path.is_absolute() else root_resolved / path
    try:
        relative = candidate.resolve(strict=True).relative_to(root_resolved)
    except (OSError, ValueError) as exc:
        raise ReleaseManifestError(
            "artifact must be a file beneath the artifact root"
        ) from exc
    value = relative.as_posix()
    if SECRET_LIKE.search(value):
        raise ReleaseManifestError("secret-like artifact paths are prohibited")
    return value


def _resolve_artifact(root: Path, value: str) -> Path:
    if not value or value.startswith("/") or SECRET_LIKE.search(value):
        raise ReleaseManifestError("artifact path is invalid")
    relative = Path(value)
    if relative.as_posix() != value or ".." in relative.parts:
        raise ReleaseManifestError("artifact path is invalid")
    root_resolved = root.resolve()
    candidate = root_resolved / relative
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root_resolved)
    except (OSError, ValueError) as exc:
        raise ReleaseManifestError("artifact path escapes the artifact root") from exc
    if candidate.is_symlink() or not resolved.is_file():
        raise ReleaseManifestError("artifact must be a regular non-symlink file")
    return resolved


def _parse_artifact(value: object) -> ArtifactRecord:
    if not isinstance(value, dict) or set(value) != {
        "role",
        "path",
        "sha256",
        "size_bytes",
    }:
        raise ReleaseManifestError("artifact record is invalid")
    role = value.get("role")
    path = value.get("path")
    digest = value.get("sha256")
    size_bytes = value.get("size_bytes")
    if not isinstance(role, str) or role not in ARTIFACT_ROLES:
        raise ReleaseManifestError("artifact role is invalid")
    if not isinstance(path, str):
        raise ReleaseManifestError("artifact path is invalid")
    if not isinstance(digest, str) or not SHA64.fullmatch(digest):
        raise ReleaseManifestError(f"{role} artifact digest is invalid")
    if (
        not isinstance(size_bytes, int)
        or isinstance(size_bytes, bool)
        or size_bytes < 0
    ):
        raise ReleaseManifestError(f"{role} artifact size is invalid")
    return ArtifactRecord(role, path, digest, size_bytes)


def _load_manifest(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ReleaseManifestError("release manifest must be a regular file")
    if stat.S_IMODE(path.stat().st_mode) & 0o022:
        raise ReleaseManifestError("release manifest must not be group/world writable")
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseManifestError("release manifest is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ReleaseManifestError("release manifest must be a JSON object")
    return payload


def _write_immutable_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = None
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        path.chmod(0o400)
    except FileExistsError as exc:
        raise ReleaseManifestError("release manifest already exists") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _manifest_sha(payload: dict[str, Any], field: str, label: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        raise ReleaseManifestError(f"{label} is invalid")
    _validate_sha(value, label)
    return value


def _validate_sha(value: str, label: str) -> None:
    if not SHA40.fullmatch(value):
        raise ReleaseManifestError(f"{label} is invalid")


def _validate_identifier(value: str, pattern: re.Pattern[str], label: str) -> None:
    if not pattern.fullmatch(value) or SECRET_LIKE.search(value):
        raise ReleaseManifestError(f"{label} is invalid")


def _require_binding(expected: str | None, actual: str, label: str) -> None:
    if expected is not None and expected != actual:
        raise ReleaseManifestError(f"{label} does not match manifest")
