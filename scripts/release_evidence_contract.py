#!/usr/bin/env python3
"""Validation helpers for non-secret release and smoke-readiness evidence."""

from __future__ import annotations

import hashlib
import json
import re
import stat
import uuid
from pathlib import Path
from typing import Any

SMOKE_CONTRACT = "enterprise-preview-smoke-readiness/v1"
EVIDENCE_CONTRACT = "enterprise-release-binding/v1"
SMOKE_TOKEN_PATH = "/run/acp-release/acceptance-reader/access-token"
PROVISIONER_PATH = "backend/scripts/provision_acceptance_readonly_principal.py"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")


class EvidenceError(ValueError):
    """A safe, non-secret evidence failure."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def protected_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise EvidenceError(f"{label} must be a regular file")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise EvidenceError(f"{label} must be mode 0600 or more restrictive")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be a JSON object")
    return value


def require_sha(value: Any, label: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise EvidenceError(f"{label} is invalid")
    return value


def require_uuid(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise EvidenceError(f"{label} is invalid")
    try:
        uuid.UUID(value)
    except ValueError as exc:
        raise EvidenceError(f"{label} is invalid") from exc
    return value


def validate_smoke_readiness(
    path: Path,
    *,
    candidate_sha: str,
    tooling_sha: str,
    company_id: str,
    branch_id: str,
    denied_company_id: str,
    provisioner_path: Path,
) -> dict[str, str]:
    artifact = protected_json(path, "smoke-readiness evidence")
    required = {
        "contract",
        "candidate_sha",
        "tooling_sha",
        "scope",
        "company_id",
        "branch_id",
        "denied_company_id",
        "token_path",
        "token_issued",
        "token_required_for_live_acceptance",
        "credential_custody",
        "provisioning",
    }
    if set(artifact) != required or artifact.get("contract") != SMOKE_CONTRACT:
        raise EvidenceError("smoke-readiness contract is invalid")
    require_sha(candidate_sha, "candidate SHA", SHA40)
    require_sha(tooling_sha, "tooling SHA", SHA40)
    if artifact.get("candidate_sha") != candidate_sha:
        raise EvidenceError("smoke readiness candidate SHA does not match")
    if artifact.get("tooling_sha") != tooling_sha:
        raise EvidenceError("smoke readiness tooling SHA does not match")
    if artifact.get("scope") != "BETA_PREVIEW":
        raise EvidenceError("smoke readiness scope is invalid")
    for label, expected in (
        ("company ID", company_id),
        ("branch ID", branch_id),
        ("denied company ID", denied_company_id),
    ):
        require_uuid(expected, label)
    if artifact.get("company_id") != company_id:
        raise EvidenceError("smoke readiness company binding does not match")
    if artifact.get("branch_id") != branch_id:
        raise EvidenceError("smoke readiness branch binding does not match")
    if artifact.get("denied_company_id") != denied_company_id:
        raise EvidenceError("smoke readiness denied-tenant binding does not match")
    if artifact.get("token_path") != SMOKE_TOKEN_PATH:
        raise EvidenceError("smoke token custody path is not canonical")
    if artifact.get("token_issued") is not False:
        raise EvidenceError(
            "pre-signing smoke evidence must not contain an issued token"
        )
    if artifact.get("token_required_for_live_acceptance") is not True:
        raise EvidenceError("live acceptance must require the real smoke token")
    custody = artifact.get("credential_custody")
    if custody != {
        "owner": "root",
        "mode": "0600",
        "mounted_read_only": True,
    }:
        raise EvidenceError("smoke token custody contract is invalid")
    provisioning = artifact.get("provisioning")
    if not isinstance(provisioning, dict) or set(provisioning) != {
        "after_signed_approval",
        "after_schema_ready",
        "procedure_path",
        "procedure_sha256",
        "isolated_procedure_passed",
    }:
        raise EvidenceError("smoke provisioning contract is invalid")
    if (
        provisioning.get("after_signed_approval") is not True
        or provisioning.get("after_schema_ready") is not True
        or provisioning.get("procedure_path") != PROVISIONER_PATH
        or provisioning.get("isolated_procedure_passed") is not True
    ):
        raise EvidenceError("smoke provisioning sequencing is invalid")
    procedure_sha = require_sha(
        provisioning.get("procedure_sha256"),
        "smoke provisioner SHA",
        SHA256_PATTERN,
    )
    if provisioner_path.is_symlink() or not provisioner_path.is_file():
        raise EvidenceError("smoke provisioner is unavailable")
    if sha256(provisioner_path) != procedure_sha:
        raise EvidenceError("smoke provisioner digest does not match evidence")
    return {
        "contract": SMOKE_CONTRACT,
        "candidate_sha": candidate_sha,
        "tooling_sha": tooling_sha,
        "company_id": company_id,
        "branch_id": branch_id,
        "denied_company_id": denied_company_id,
        "token_state": "NOT_ISSUED_PRE_SIGNING",
    }


SHA256_PATTERN = SHA64


def validate_evidence_binding(
    path: Path,
    smoke_path: Path,
    *,
    candidate_sha: str,
    tooling_sha: str,
    migration_head: str,
    backup_receipt_sha256: str,
    restore_receipt_sha256: str,
    rollback_target_sha: str,
    rollback_target_release: str,
    company_id: str,
    branch_id: str,
    denied_company_id: str,
    provisioner_path: Path,
) -> dict[str, str]:
    manifest = protected_json(path, "release evidence manifest")
    required = {
        "contract",
        "candidate_sha",
        "tooling_sha",
        "migration_head",
        "backup_receipt_sha256",
        "restore_receipt_sha256",
        "rollback_target",
        "smoke_readiness_sha256",
    }
    if set(manifest) != required or manifest.get("contract") != EVIDENCE_CONTRACT:
        raise EvidenceError("release evidence binding contract is invalid")
    expected = {
        "candidate_sha": candidate_sha,
        "tooling_sha": tooling_sha,
        "migration_head": migration_head,
        "backup_receipt_sha256": backup_receipt_sha256,
        "restore_receipt_sha256": restore_receipt_sha256,
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise EvidenceError(f"release evidence {field} does not match")
    require_sha(rollback_target_sha, "rollback target SHA", SHA40)
    if manifest.get("rollback_target") != {
        "sha": rollback_target_sha,
        "release": rollback_target_release,
    }:
        raise EvidenceError("release evidence rollback target does not match")
    require_sha(backup_receipt_sha256, "backup receipt SHA", SHA64)
    require_sha(restore_receipt_sha256, "restore receipt SHA", SHA64)
    smoke_result = validate_smoke_readiness(
        smoke_path,
        candidate_sha=candidate_sha,
        tooling_sha=tooling_sha,
        company_id=company_id,
        branch_id=branch_id,
        denied_company_id=denied_company_id,
        provisioner_path=provisioner_path,
    )
    smoke_digest = sha256(smoke_path)
    if manifest.get("smoke_readiness_sha256") != smoke_digest:
        raise EvidenceError("release evidence smoke-readiness digest does not match")
    return {
        "contract": EVIDENCE_CONTRACT,
        "candidate_sha": candidate_sha,
        "tooling_sha": tooling_sha,
        "smoke_readiness_sha256": smoke_digest,
        "smoke_state": smoke_result["token_state"],
    }
