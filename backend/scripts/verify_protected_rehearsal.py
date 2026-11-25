"""Verify and seal one isolated restored-database release rehearsal.

The verifier is intentionally evidence-only: it cannot connect to Beta, mutate a
protected database, approve a release, or deploy.  Every input must be a private,
digest-bound receipt produced by the isolated rehearsal workflow.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Final

SHA40: Final = re.compile(r"[0-9a-f]{40}")
SHA64: Final = re.compile(r"[0-9a-f]{64}")
OUTPUT_CONTRACT: Final = "enterprise-release.protected-rehearsal-verification/v1"


class RehearsalEvidenceError(ValueError):
    """Raised when rehearsal evidence is incomplete, stale, or inconsistent."""


def canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_private_file(path: Path, label: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise RehearsalEvidenceError(f"{label} must be a regular file")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise RehearsalEvidenceError(f"{label} permissions are not restrictive")


def load_json(path: Path, label: str, contract: str) -> dict[str, Any]:
    require_private_file(path, label)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RehearsalEvidenceError(f"{label} is not valid JSON") from error
    if not isinstance(payload, dict) or payload.get("contract") != contract:
        raise RehearsalEvidenceError(f"{label} contract is invalid")
    digest = payload.get("digest")
    unsigned = {key: value for key, value in payload.items() if key != "digest"}
    expected = hashlib.sha256(canonical(unsigned)).hexdigest()
    if digest != expected:
        raise RehearsalEvidenceError(f"{label} digest is invalid")
    return payload


def load_backup(manifest_path: Path) -> tuple[dict[str, Any], Path]:
    require_private_file(manifest_path, "backup manifest")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RehearsalEvidenceError("backup manifest is not valid JSON") from error
    required = {
        "authority_sha",
        "backup_file",
        "contract_version",
        "database_identity",
        "environment",
        "format",
        "schema_head",
        "sha256",
        "size_bytes",
    }
    if not required <= set(manifest):
        raise RehearsalEvidenceError("backup manifest is incomplete")
    if manifest["contract_version"] != "platform-resilience.backup.v1":
        raise RehearsalEvidenceError("backup manifest contract is invalid")
    if manifest["environment"] not in {"development", "test", "preview-isolated"}:
        raise RehearsalEvidenceError("backup environment is not approved")
    if manifest["format"] != "postgresql-custom":
        raise RehearsalEvidenceError("backup format is not PostgreSQL custom")
    if not SHA40.fullmatch(str(manifest["authority_sha"])):
        raise RehearsalEvidenceError("backup authority SHA is invalid")
    if not SHA64.fullmatch(str(manifest["sha256"])):
        raise RehearsalEvidenceError("backup SHA-256 is invalid")
    backup = manifest_path.parent / str(manifest["backup_file"])
    require_private_file(backup, "backup artifact")
    if backup.stat().st_size != manifest["size_bytes"]:
        raise RehearsalEvidenceError("backup size does not match its manifest")
    if sha256(backup) != manifest["sha256"]:
        raise RehearsalEvidenceError("backup digest does not match its manifest")
    return manifest, backup


def require_binding(
    payload: dict[str, Any], expected: dict[str, Any], label: str
) -> None:
    mismatches = sorted(
        key for key, value in expected.items() if payload.get(key) != value
    )
    if mismatches:
        raise RehearsalEvidenceError(
            f"{label} binding mismatch: {', '.join(mismatches)}"
        )


def require_role_flags(
    role: dict[str, Any], expected: dict[str, bool], name: str
) -> None:
    for flag, value in expected.items():
        if role.get(flag) is not value:
            raise RehearsalEvidenceError(f"{name} role flag {flag} is invalid")


def verify_roles(payload: dict[str, Any]) -> None:
    roles = payload.get("roles")
    if not isinstance(roles, dict) or set(roles) != {
        "acp_app",
        "acp_backup",
        "acp_migrate",
        "acp_schema_owner",
    }:
        raise RehearsalEvidenceError("role evidence does not cover the required roles")
    safe = {
        "superuser": False,
        "createdb": False,
        "createrole": False,
        "replication": False,
    }
    require_role_flags(
        roles["acp_schema_owner"],
        {**safe, "login": False, "bypassrls": False},
        "acp_schema_owner",
    )
    require_role_flags(
        roles["acp_migrate"],
        {**safe, "login": True, "bypassrls": False},
        "acp_migrate",
    )
    if roles["acp_migrate"].get("member_of") != ["acp_schema_owner"]:
        raise RehearsalEvidenceError("acp_migrate ownership membership is invalid")
    require_role_flags(
        roles["acp_app"],
        {**safe, "login": True, "bypassrls": False},
        "acp_app",
    )
    require_role_flags(
        roles["acp_backup"],
        {**safe, "login": True, "bypassrls": True},
        "acp_backup",
    )
    expected = {
        "application_connection_role": "acp_app",
        "backup_connection_role": "acp_backup",
        "cross_tenant_read_denied": True,
        "cross_tenant_write_denied": True,
        "migration_connection_role": "acp_migrate",
        "object_owner": "acp_schema_owner",
    }
    require_binding(payload, expected, "role evidence")


def write_private(path: Path, payload: dict[str, Any]) -> None:
    path = path.resolve()
    if not path.parent.exists():
        path.parent.mkdir(mode=0o700, parents=True)
    if stat.S_IMODE(path.parent.stat().st_mode) & 0o077:
        raise RehearsalEvidenceError(
            "verification evidence directory permissions are not restrictive"
        )
    if path.exists():
        raise RehearsalEvidenceError("refusing to overwrite verification evidence")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def verify(args: argparse.Namespace) -> dict[str, Any]:
    candidate = args.candidate_sha
    baseline = args.baseline_sha
    if not SHA40.fullmatch(candidate) or not SHA40.fullmatch(baseline):
        raise RehearsalEvidenceError("candidate and baseline must be full Git SHAs")
    if candidate == baseline:
        raise RehearsalEvidenceError("candidate must differ from the restored baseline")

    manifest_path = args.backup_manifest.resolve()
    manifest, backup = load_backup(manifest_path)
    if manifest["authority_sha"] != baseline:
        raise RehearsalEvidenceError("backup is not bound to the requested baseline")

    restore = load_json(
        args.restore_receipt.resolve(),
        "restore receipt",
        "platform-resilience.restore-receipt.v2",
    )
    if not str(restore.get("target_identity", "")).startswith("isolated-"):
        raise RehearsalEvidenceError("restore target is not isolated")
    if not str(restore.get("database_name", "")).startswith("acp_resilience_restore"):
        raise RehearsalEvidenceError("restore database identity is not isolated")
    require_binding(
        restore,
        {
            "source_authority_sha": baseline,
            "source_database_identity": manifest["database_identity"],
            "source_schema_head": manifest["schema_head"],
            "source_sha256": manifest["sha256"],
            "target_was_empty": True,
        },
        "restore receipt",
    )
    database_identity = restore["target_identity"]

    migration = load_json(
        args.migration_evidence.resolve(),
        "migration evidence",
        "enterprise-release.migration-rehearsal/v1",
    )
    require_binding(
        migration,
        {
            "alembic_check": "PASS",
            "candidate_sha": candidate,
            "database_identity": database_identity,
            "expected_head": args.expected_head,
            "idempotent_reupgrade": True,
            "observed_after_head": args.expected_head,
            "observed_before_head": manifest["schema_head"],
            "single_head": True,
        },
        "migration evidence",
    )

    roles = load_json(
        args.role_evidence.resolve(),
        "role evidence",
        "enterprise-release.database-role-rehearsal/v1",
    )
    require_binding(
        roles,
        {"candidate_sha": candidate, "database_identity": database_identity},
        "role evidence",
    )
    verify_roles(roles)

    readiness = load_json(
        args.readiness_evidence.resolve(),
        "readiness evidence",
        "enterprise-release.application-readiness-rehearsal/v1",
    )
    require_binding(
        readiness,
        {
            "application_role": "acp_app",
            "candidate_sha": candidate,
            "database_identity": database_identity,
            "schema_head": args.expected_head,
            "state": "HEALTHY",
        },
        "readiness evidence",
    )

    rollback = load_json(
        args.rollback_evidence.resolve(),
        "rollback evidence",
        "enterprise-release.rollback-rehearsal/v1",
    )
    if not str(rollback.get("target_identity", "")).startswith("isolated-"):
        raise RehearsalEvidenceError("rollback target is not isolated")
    require_binding(
        rollback,
        {
            "baseline_sha": baseline,
            "candidate_sha": candidate,
            "data_digest_after": rollback.get("data_digest_before"),
            "restored_head": manifest["schema_head"],
            "source_backup_sha256": manifest["sha256"],
            "verified": True,
        },
        "rollback evidence",
    )

    evidence_paths = {
        "backup_artifact": backup,
        "backup_manifest": manifest_path,
        "migration": args.migration_evidence.resolve(),
        "readiness": args.readiness_evidence.resolve(),
        "restore": args.restore_receipt.resolve(),
        "roles": args.role_evidence.resolve(),
        "rollback": args.rollback_evidence.resolve(),
    }
    result: dict[str, Any] = {
        "baseline_sha": baseline,
        "candidate_sha": candidate,
        "checks": {
            "backup_integrity": "PASS",
            "isolated_restore": "PASS",
            "migration": "PASS",
            "readiness": "PASS",
            "role_separation": "PASS",
            "rollback": "PASS",
        },
        "contract": OUTPUT_CONTRACT,
        "database_identity": database_identity,
        "deployment_authorized": False,
        "evidence_sha256": {
            name: sha256(path) for name, path in sorted(evidence_paths.items())
        },
        "expected_head": args.expected_head,
        "release_decision": "QUALIFIED_FOR_INDEPENDENT_REVIEW",
    }
    result["digest"] = hashlib.sha256(canonical(result)).hexdigest()
    return result


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    root.add_argument("--candidate-sha", required=True)
    root.add_argument("--baseline-sha", required=True)
    root.add_argument("--expected-head", required=True)
    root.add_argument("--backup-manifest", type=Path, required=True)
    root.add_argument("--restore-receipt", type=Path, required=True)
    root.add_argument("--migration-evidence", type=Path, required=True)
    root.add_argument("--role-evidence", type=Path, required=True)
    root.add_argument("--readiness-evidence", type=Path, required=True)
    root.add_argument("--rollback-evidence", type=Path, required=True)
    root.add_argument("--output", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        result = verify(args)
        write_private(args.output, result)
    except (OSError, RehearsalEvidenceError) as error:
        raise SystemExit(
            f"protected rehearsal verification blocked: {error}"
        ) from error
    print(
        json.dumps(
            {
                "digest": result["digest"],
                "output": str(args.output.resolve()),
                "result": result["release_decision"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
