#!/usr/bin/env python3
"""Validate an Enterprise-signed, Beta-only Preview release approval.

This tool intentionally has no issuing mode. The Enterprise authority creates
the signed artifact outside the candidate repository; the candidate can only
validate it against a pinned trusted issuer public key and expected release
evidence.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import re
import stat
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

CONTRACT = "enterprise-preview-release-approval/v1"
ISSUER_ID = "OM1E"
ISSUER_ROLE = "Enterprise Release Authority"
SCOPE = "BETA_PREVIEW"
MAX_TTL = timedelta(hours=24)
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
MIGRATION_HEAD = re.compile(r"^[a-z0-9][a-z0-9_-]{11,63}$")


class ApprovalError(ValueError):
    """A safe, non-secret approval validation failure."""


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def private_file(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ApprovalError(f"{label} must be a regular file")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ApprovalError(f"{label} must be mode 0600 or more restrictive")
    return path.read_bytes()


def parse_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise ApprovalError(f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ApprovalError(f"{label} is not a valid timestamp") from exc
    if parsed.tzinfo is None:
        raise ApprovalError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate_approval(
    artifact_path: Path,
    trusted_key_path: Path,
    *,
    expected_key_id: str,
    candidate_sha: str,
    migration_head: str,
    backup_receipt_sha256: str,
    restore_receipt_sha256: str,
    rollback_target_sha: str,
    rollback_target_release: str,
    now: datetime | None = None,
) -> dict[str, str]:
    raw = private_file(artifact_path, "approval artifact")
    try:
        artifact = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApprovalError("approval artifact is not valid JSON") from exc
    if not isinstance(artifact, dict):
        raise ApprovalError("approval artifact must be a JSON object")

    required = {
        "contract",
        "approval_id",
        "candidate_sha",
        "migration_head",
        "backup_receipt_sha256",
        "restore_receipt_sha256",
        "rollback_target",
        "scope",
        "issued_at",
        "expires_at",
        "authorized_issuer",
        "artifact_digest",
        "signature",
    }
    if set(artifact) != required:
        raise ApprovalError("approval artifact fields do not match v1 contract")
    if artifact["contract"] != CONTRACT:
        raise ApprovalError("approval contract is invalid")
    try:
        uuid.UUID(str(artifact["approval_id"]))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ApprovalError("approval_id is invalid") from exc

    rollback = artifact.get("rollback_target")
    rollback_sha = rollback.get("sha") if isinstance(rollback, dict) else None
    for label, value, pattern in (
        ("candidate_sha", artifact["candidate_sha"], SHA40),
        ("expected candidate SHA", candidate_sha, SHA40),
        ("backup_receipt_sha256", artifact["backup_receipt_sha256"], SHA64),
        ("expected backup receipt SHA", backup_receipt_sha256, SHA64),
        ("restore_receipt_sha256", artifact["restore_receipt_sha256"], SHA64),
        ("expected restore receipt SHA", restore_receipt_sha256, SHA64),
        ("rollback target SHA", rollback_sha, SHA40),
        ("expected rollback target SHA", rollback_target_sha, SHA40),
        ("artifact_digest", artifact["artifact_digest"], SHA64),
    ):
        if not isinstance(value, str) or not pattern.fullmatch(value):
            raise ApprovalError(f"{label} is invalid")
    if artifact["candidate_sha"] != candidate_sha:
        raise ApprovalError("approval candidate does not match requested candidate")
    if artifact["migration_head"] != migration_head or not MIGRATION_HEAD.fullmatch(
        str(artifact["migration_head"])
    ):
        raise ApprovalError("approval migration head does not match requested head")
    if artifact["backup_receipt_sha256"] != backup_receipt_sha256:
        raise ApprovalError("approval backup receipt does not match authority")
    if artifact["restore_receipt_sha256"] != restore_receipt_sha256:
        raise ApprovalError("approval restore receipt does not match authority")
    if artifact["scope"] != SCOPE:
        raise ApprovalError("approval scope is not Beta-only")

    rollback = artifact["rollback_target"]
    if not isinstance(rollback, dict) or set(rollback) != {"sha", "release"}:
        raise ApprovalError("rollback target is invalid")
    if rollback["sha"] != rollback_target_sha or rollback["release"] != rollback_target_release:
        raise ApprovalError("approval rollback target does not match requested target")

    issuer = artifact["authorized_issuer"]
    if not isinstance(issuer, dict) or set(issuer) != {"id", "role", "key_id"}:
        raise ApprovalError("authorized issuer is invalid")
    if issuer["id"] != ISSUER_ID or issuer["role"] != ISSUER_ROLE:
        raise ApprovalError("approval issuer is not the Enterprise release authority")
    if issuer["key_id"] != expected_key_id:
        raise ApprovalError("approval issuer key is not trusted for this release")

    issued = parse_time(artifact["issued_at"], "issued_at")
    expires = parse_time(artifact["expires_at"], "expires_at")
    if expires <= issued or expires - issued > MAX_TTL:
        raise ApprovalError("approval lifetime is invalid")
    observed = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if observed < issued or observed >= expires:
        raise ApprovalError("approval is expired or not yet valid")

    unsigned = dict(artifact)
    unsigned.pop("signature")
    supplied_digest = unsigned.pop("artifact_digest")
    computed_digest = hashlib.sha256(canonical(unsigned)).hexdigest()
    if supplied_digest != computed_digest:
        raise ApprovalError("approval artifact digest does not match its contents")

    signature = artifact["signature"]
    if not isinstance(signature, dict) or set(signature) != {"algorithm", "encoding", "value"}:
        raise ApprovalError("approval signature is invalid")
    if signature["algorithm"] != "Ed25519" or signature["encoding"] != "base64":
        raise ApprovalError("approval signature algorithm is invalid")
    try:
        signature_bytes = base64.b64decode(signature["value"], validate=True)
    except (ValueError, binascii.Error, TypeError) as exc:
        raise ApprovalError("approval signature encoding is invalid") from exc
    if len(signature_bytes) != 64:
        raise ApprovalError("approval signature length is invalid")
    try:
        public_key = load_pem_public_key(private_file(trusted_key_path, "trusted issuer key"))
        if not isinstance(public_key, Ed25519PublicKey):
            raise ApprovalError("trusted issuer key is not Ed25519")
        public_key.verify(signature_bytes, canonical({**unsigned, "artifact_digest": supplied_digest}))
    except ApprovalError:
        raise
    except Exception as exc:  # cryptography uses InvalidSignature without a stable stdlib base
        raise ApprovalError("approval signature does not verify against the trusted issuer") from exc

    return {
        "contract": CONTRACT,
        "approval_id": str(artifact["approval_id"]),
        "candidate_sha": candidate_sha,
        "migration_head": migration_head,
        "scope": SCOPE,
        "issuer": ISSUER_ID,
        "expires_at": expires.isoformat(),
        "artifact_digest": supplied_digest,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--trusted-issuer-key", type=Path, required=True)
    parser.add_argument("--trusted-key-id", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--migration-head", required=True)
    parser.add_argument("--backup-receipt-sha256", required=True)
    parser.add_argument("--restore-receipt-sha256", required=True)
    parser.add_argument("--rollback-target-sha", required=True)
    parser.add_argument("--rollback-target-release", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = validate_approval(
            args.artifact,
            args.trusted_issuer_key,
            expected_key_id=args.trusted_key_id,
            candidate_sha=args.candidate_sha,
            migration_head=args.migration_head,
            backup_receipt_sha256=args.backup_receipt_sha256,
            restore_receipt_sha256=args.restore_receipt_sha256,
            rollback_target_sha=args.rollback_target_sha,
            rollback_target_release=args.rollback_target_release,
        )
    except ApprovalError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"result": "PASS", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
