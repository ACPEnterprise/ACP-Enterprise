#!/usr/bin/env python3
"""Operate the owner-enrolled, Beta-only Enterprise release authority.

The protected authority root is independent of candidate worktrees. Enrollment,
issuance, rotation, and revocation require an interactive human custodian.
Validation is non-interactive and fails closed against a pinned public key,
key ID, authority registry, exact release bindings, and independent review.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import fcntl
import getpass
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption,
    Encoding,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
    load_pem_public_key,
)

AUTHORITY_CONTRACT = "enterprise-release-authority-trust/v1"
APPROVAL_CONTRACT = "enterprise-preview-release-approval/v2"
REVIEW_CONTRACT = "enterprise-release-independent-review/v1"
AUDIT_CONTRACT = "enterprise-release-authority-audit-event/v1"
AUTHORITY_ID = "twelvehats-beta-release-authority"
AUTHORITY_ROLE = "Enterprise Release Authority"
SCOPE = "BETA_PREVIEW"
MAX_APPROVAL_TTL = timedelta(hours=24)
MAX_REVIEW_AGE = timedelta(hours=72)
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
MIGRATION_HEAD = re.compile(r"^[a-z0-9][a-z0-9_-]{11,63}$")
IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")


class AuthorityError(ValueError):
    """A safe, non-secret authority failure."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise AuthorityError(f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuthorityError(f"{label} is not a valid timestamp") from exc
    if parsed.tzinfo is None:
        raise AuthorityError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def object_digest(value: object) -> str:
    return digest(canonical(value))


def protected_file(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise AuthorityError(f"{label} must be a regular file")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise AuthorityError(f"{label} must be mode 0600 or more restrictive")
    return path.read_bytes()


def protected_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(protected_file(path, label))
    except json.JSONDecodeError as exc:
        raise AuthorityError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise AuthorityError(f"{label} must be a JSON object")
    return value


def atomic_private_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_private_json(path: Path, value: object) -> None:
    atomic_private_write(
        path, json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"
    )


def ensure_private_root(root: Path, *, create: bool = False) -> Path:
    resolved = root.resolve()
    if create:
        resolved.mkdir(mode=0o700, parents=True, exist_ok=True)
    if resolved.is_symlink() or not resolved.is_dir():
        raise AuthorityError("authority root must be a real directory")
    if stat.S_IMODE(resolved.stat().st_mode) & 0o077:
        raise AuthorityError("authority root must be mode 0700 or more restrictive")
    return resolved


def require_sha(value: str, label: str, pattern: re.Pattern[str] = SHA64) -> str:
    if not pattern.fullmatch(value):
        raise AuthorityError(f"{label} is invalid")
    return value


def require_identifier(value: str, label: str) -> str:
    if not IDENTIFIER.fullmatch(value):
        raise AuthorityError(f"{label} is invalid")
    return value


def require_uuid(value: str, label: str) -> str:
    try:
        uuid.UUID(value)
    except ValueError as exc:
        raise AuthorityError(f"{label} must be a UUID") from exc
    return value


def utility_digest() -> str:
    return digest(Path(__file__).resolve().read_bytes())


def public_fingerprint(public_key: Ed25519PublicKey) -> str:
    return digest(
        public_key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    )


def key_id_for(public_key: Ed25519PublicKey, observed: datetime) -> str:
    return f"beta-era-{observed:%Y%m%d}-{public_fingerprint(public_key)[:12]}"


def key_enrollment_digest(
    *,
    authority_id: str,
    custodian_id: str,
    key_id: str,
    fingerprint: str,
    valid_from: str,
    expires_at: str,
    owner_approval_id: str,
) -> str:
    return object_digest(
        {
            "authority_id": authority_id,
            "custodian_id": custodian_id,
            "key_id": key_id,
            "public_key_sha256": fingerprint,
            "valid_from": valid_from,
            "expires_at": expires_at,
            "owner_approval_id": owner_approval_id,
        }
    )


def encrypted_key_material(passphrase: bytes) -> tuple[bytes, bytes, Ed25519PublicKey]:
    if len(passphrase) < 16:
        raise AuthorityError(
            "private-key passphrase must contain at least 16 characters"
        )
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    private_bytes = private_key.private_bytes(
        Encoding.PEM,
        PrivateFormat.PKCS8,
        BestAvailableEncryption(passphrase),
    )
    public_bytes = public_key.public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    )
    return private_bytes, public_bytes, public_key


def registry_without_digest(registry: dict[str, Any]) -> dict[str, Any]:
    result = dict(registry)
    result.pop("registry_digest", None)
    return result


def seal_registry(registry: dict[str, Any]) -> dict[str, Any]:
    unsigned = registry_without_digest(registry)
    return {**unsigned, "registry_digest": object_digest(unsigned)}


def append_audit(
    root: Path,
    event: str,
    details: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    audit_path = root / "audit" / "events.ndjson"
    audit_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(audit_path.parent, 0o700)
    descriptor = os.open(audit_path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "r+b", closefd=True) as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        existing = stream.read().decode()
        lines = [line for line in existing.splitlines() if line]
        previous_hash = "0" * 64
        sequence = 1
        if lines:
            try:
                previous = json.loads(lines[-1])
            except json.JSONDecodeError as exc:
                raise AuthorityError("authority audit log is corrupt") from exc
            previous_hash = str(previous.get("event_hash", ""))
            require_sha(previous_hash, "previous audit hash")
            sequence = int(previous.get("sequence", 0)) + 1
        unsigned = {
            "contract": AUDIT_CONTRACT,
            "sequence": sequence,
            "recorded_at": timestamp(now or utc_now()),
            "event": event,
            "previous_hash": previous_hash,
            "details": details,
        }
        record = {**unsigned, "event_hash": object_digest(unsigned)}
        stream.seek(0, os.SEEK_END)
        stream.write(canonical(record) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
        os.fchmod(stream.fileno(), 0o600)
        return record


def verify_audit(root: Path) -> dict[str, Any]:
    path = root / "audit" / "events.ndjson"
    raw = protected_file(path, "authority audit log").decode()
    previous_hash = "0" * 64
    count = 0
    for count, line in enumerate((item for item in raw.splitlines() if item), start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AuthorityError("authority audit log is corrupt") from exc
        if (
            record.get("sequence") != count
            or record.get("previous_hash") != previous_hash
        ):
            raise AuthorityError("authority audit chain is discontinuous")
        supplied = record.get("event_hash")
        unsigned = dict(record)
        unsigned.pop("event_hash", None)
        if supplied != object_digest(unsigned):
            raise AuthorityError("authority audit event digest is invalid")
        previous_hash = str(supplied)
    if count == 0:
        raise AuthorityError("authority audit log is empty")
    return {"events": count, "head": previous_hash}


def create_enrollment(
    root: Path,
    *,
    custodian_id: str,
    custodian_name: str,
    reviewer_id: str,
    reviewer_name: str,
    owner_approval_id: str,
    passphrase: bytes,
    validity_days: int = 90,
    now: datetime | None = None,
) -> dict[str, Any]:
    observed = (now or utc_now()).astimezone(timezone.utc)
    require_identifier(custodian_id, "custodian ID")
    require_identifier(reviewer_id, "reviewer ID")
    if reviewer_id == custodian_id:
        raise AuthorityError(
            "independent reviewer must differ from the authority custodian"
        )
    if not custodian_name.strip() or not reviewer_name.strip():
        raise AuthorityError("custodian and reviewer names are required")
    if not 1 <= validity_days <= 365:
        raise AuthorityError("key validity must be between 1 and 365 days")
    require_uuid(owner_approval_id, "owner approval ID")

    protected_root = ensure_private_root(root, create=True)
    registry_path = protected_root / "trust" / "authority.json"
    if registry_path.exists():
        raise AuthorityError("authority is already enrolled; use rotation")

    private_bytes, public_bytes, public_key = encrypted_key_material(passphrase)
    fingerprint = public_fingerprint(public_key)
    key_id = key_id_for(public_key, observed)
    valid_from = timestamp(observed)
    expires_at = timestamp(observed + timedelta(days=validity_days))
    enrollment_digest = key_enrollment_digest(
        authority_id=AUTHORITY_ID,
        custodian_id=custodian_id,
        key_id=key_id,
        fingerprint=fingerprint,
        valid_from=valid_from,
        expires_at=expires_at,
        owner_approval_id=owner_approval_id,
    )
    private_path = protected_root / "private" / f"{key_id}.private.pem"
    public_path = protected_root / "public" / f"{key_id}.public.pem"
    atomic_private_write(private_path, private_bytes)
    atomic_private_write(public_path, public_bytes)
    key = {
        "key_id": key_id,
        "algorithm": "Ed25519",
        "public_key_file": f"public/{key_id}.public.pem",
        "private_key_file": f"private/{key_id}.private.pem",
        "public_key_sha256": fingerprint,
        "valid_from": valid_from,
        "expires_at": expires_at,
        "status": "active",
        "enrollment_digest": enrollment_digest,
        "owner_approval_id": owner_approval_id,
    }
    registry = seal_registry(
        {
            "contract": AUTHORITY_CONTRACT,
            "authority": {
                "id": AUTHORITY_ID,
                "role": AUTHORITY_ROLE,
                "scope": SCOPE,
                "custodian": {"id": custodian_id, "name": custodian_name.strip()},
            },
            "independent_review": {
                "required": True,
                "reviewer": {
                    "id": reviewer_id,
                    "name": reviewer_name.strip(),
                    "role": "Enterprise Independent Qualification Reviewer",
                },
                "issuer_may_not_review": True,
                "maximum_age_hours": int(MAX_REVIEW_AGE.total_seconds() // 3600),
            },
            "keys": [key],
            "issuer_utility_sha256": utility_digest(),
            "enrolled_at": valid_from,
        }
    )
    atomic_private_json(registry_path, registry)
    receipt = {
        "contract": "enterprise-release-authority-enrollment/v1",
        "authority_id": AUTHORITY_ID,
        "custodian": registry["authority"]["custodian"],
        "reviewer": registry["independent_review"]["reviewer"],
        "key_id": key_id,
        "public_key_sha256": fingerprint,
        "valid_from": valid_from,
        "expires_at": expires_at,
        "enrollment_digest": enrollment_digest,
        "registry_digest": registry["registry_digest"],
        "issuer_utility_sha256": registry["issuer_utility_sha256"],
        "owner_approval_id": owner_approval_id,
        "private_key_reference": str(private_path),
        "public_key_reference": str(public_path),
    }
    atomic_private_json(protected_root / "receipts" / "enrollment.json", receipt)
    append_audit(
        protected_root,
        "authority.enrolled",
        {
            "authority_id": AUTHORITY_ID,
            "custodian_id": custodian_id,
            "reviewer_id": reviewer_id,
            "key_id": key_id,
            "enrollment_digest": enrollment_digest,
            "owner_approval_id": owner_approval_id,
        },
        now=observed,
    )
    return receipt


def validate_registry(
    registry_path: Path,
    trusted_key_path: Path,
    *,
    expected_key_id: str,
    now: datetime | None = None,
    for_issuance: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], Ed25519PublicKey]:
    registry = protected_json(registry_path, "authority registry")
    required = {
        "contract",
        "authority",
        "independent_review",
        "keys",
        "issuer_utility_sha256",
        "enrolled_at",
        "registry_digest",
    }
    if set(registry) != required or registry.get("contract") != AUTHORITY_CONTRACT:
        raise AuthorityError("authority registry contract is invalid")
    supplied_registry_digest = registry.get("registry_digest")
    if supplied_registry_digest != object_digest(registry_without_digest(registry)):
        raise AuthorityError("authority registry digest is invalid")
    if registry.get("issuer_utility_sha256") != utility_digest():
        raise AuthorityError("authority registry is not bound to this issuer utility")
    authority = registry.get("authority")
    if not isinstance(authority, dict) or authority.get("id") != AUTHORITY_ID:
        raise AuthorityError("authority registry identity is invalid")
    if authority.get("role") != AUTHORITY_ROLE or authority.get("scope") != SCOPE:
        raise AuthorityError("authority registry role or scope is invalid")
    review = registry.get("independent_review")
    if not isinstance(review, dict):
        raise AuthorityError("independent-review policy is invalid")
    custodian = authority.get("custodian")
    reviewer = review.get("reviewer")
    if (
        not isinstance(custodian, dict)
        or not isinstance(reviewer, dict)
        or review.get("required") is not True
        or review.get("issuer_may_not_review") is not True
        or reviewer.get("id") == custodian.get("id")
    ):
        raise AuthorityError("independent-review policy is invalid")

    keys = registry.get("keys")
    if not isinstance(keys, list):
        raise AuthorityError("authority key registry is invalid")
    if sum(key.get("status") == "active" for key in keys if isinstance(key, dict)) != 1:
        raise AuthorityError("authority registry must contain exactly one active key")
    matches = [
        key
        for key in keys
        if isinstance(key, dict) and key.get("key_id") == expected_key_id
    ]
    if len(matches) != 1:
        raise AuthorityError("trusted key ID is not uniquely enrolled")
    key = matches[0]
    allowed_statuses = {"active"} if for_issuance else {"active", "verification_only"}
    if key.get("status") not in allowed_statuses:
        raise AuthorityError("authority key is not active for this operation")
    if key.get("algorithm") != "Ed25519":
        raise AuthorityError("authority key algorithm is invalid")
    if (
        key.get("public_key_file") != f"public/{expected_key_id}.public.pem"
        or key.get("private_key_file") != f"private/{expected_key_id}.private.pem"
    ):
        raise AuthorityError("authority key custody references are invalid")
    require_uuid(str(key.get("owner_approval_id")), "key owner approval ID")
    observed = (now or utc_now()).astimezone(timezone.utc)
    valid_from = parse_time(key.get("valid_from"), "key valid_from")
    expires_at = parse_time(key.get("expires_at"), "key expires_at")
    if observed < valid_from or observed >= expires_at:
        raise AuthorityError("authority key is not currently valid")
    if key.get("status") == "verification_only":
        verify_until = parse_time(key.get("verify_until"), "key verify_until")
        if observed >= verify_until:
            raise AuthorityError(
                "rotated authority key verification window has expired"
            )
    public_bytes = protected_file(trusted_key_path, "trusted authority public key")
    try:
        public_key = load_pem_public_key(public_bytes)
    except ValueError as exc:
        raise AuthorityError("trusted authority public key is invalid") from exc
    if not isinstance(public_key, Ed25519PublicKey):
        raise AuthorityError("trusted authority public key is not Ed25519")
    fingerprint = public_fingerprint(public_key)
    if key.get("public_key_sha256") != fingerprint:
        raise AuthorityError("trusted authority public key fingerprint is not enrolled")
    expected_enrollment = key_enrollment_digest(
        authority_id=AUTHORITY_ID,
        custodian_id=str(custodian.get("id")),
        key_id=expected_key_id,
        fingerprint=fingerprint,
        valid_from=str(key.get("valid_from")),
        expires_at=str(key.get("expires_at")),
        owner_approval_id=str(key.get("owner_approval_id")),
    )
    if key.get("enrollment_digest") != expected_enrollment:
        raise AuthorityError("authority key enrollment digest is invalid")
    return registry, key, public_key


def validate_release_binding(
    *,
    candidate_sha: str,
    migration_head: str,
    backup_receipt_sha256: str,
    restore_receipt_sha256: str,
    rollback_target_sha: str,
    rollback_target_release: str,
) -> None:
    require_sha(candidate_sha, "candidate SHA", SHA40)
    if not MIGRATION_HEAD.fullmatch(migration_head):
        raise AuthorityError("migration head is invalid")
    require_sha(backup_receipt_sha256, "backup receipt SHA")
    require_sha(restore_receipt_sha256, "restore receipt SHA")
    require_sha(rollback_target_sha, "rollback target SHA", SHA40)
    if not rollback_target_release.strip():
        raise AuthorityError("rollback target release is required")


def validate_review(
    review_path: Path,
    registry: dict[str, Any],
    *,
    candidate_sha: str,
    migration_head: str,
    backup_receipt_sha256: str,
    restore_receipt_sha256: str,
    rollback_target_sha: str,
    rollback_target_release: str,
    now: datetime,
) -> tuple[dict[str, Any], str]:
    review = protected_json(review_path, "independent review receipt")
    required = {
        "contract",
        "review_id",
        "candidate_sha",
        "migration_head",
        "backup_receipt_sha256",
        "restore_receipt_sha256",
        "rollback_target",
        "scope",
        "reviewer",
        "evidence_archive_sha256",
        "mandatory_gates_passed",
        "defects",
        "decision",
        "reviewed_at",
    }
    if set(review) != required or review.get("contract") != REVIEW_CONTRACT:
        raise AuthorityError("independent review receipt contract is invalid")
    try:
        uuid.UUID(str(review.get("review_id")))
    except ValueError as exc:
        raise AuthorityError("independent review ID is invalid") from exc
    reviewer = review.get("reviewer")
    enrolled_reviewer = registry["independent_review"]["reviewer"]
    custodian = registry["authority"]["custodian"]
    if not isinstance(reviewer, dict) or reviewer != enrolled_reviewer:
        raise AuthorityError("independent reviewer is not enrolled")
    if reviewer.get("id") == custodian.get("id"):
        raise AuthorityError("authority custodian cannot independently review")
    rollback = review.get("rollback_target")
    expected = {
        "candidate_sha": candidate_sha,
        "migration_head": migration_head,
        "backup_receipt_sha256": backup_receipt_sha256,
        "restore_receipt_sha256": restore_receipt_sha256,
        "scope": SCOPE,
    }
    for field, value in expected.items():
        if review.get(field) != value:
            raise AuthorityError(
                f"independent review {field} does not match release request"
            )
    if rollback != {"sha": rollback_target_sha, "release": rollback_target_release}:
        raise AuthorityError(
            "independent review rollback target does not match release request"
        )
    require_sha(
        str(review.get("evidence_archive_sha256")), "review evidence archive SHA"
    )
    if review.get("mandatory_gates_passed") is not True:
        raise AuthorityError("independent review has not passed every mandatory gate")
    if review.get("defects") != [] or review.get("decision") != "APPROVE":
        raise AuthorityError(
            "independent review has unresolved defects or is not approved"
        )
    reviewed_at = parse_time(review.get("reviewed_at"), "reviewed_at")
    if reviewed_at > now or now - reviewed_at > MAX_REVIEW_AGE:
        raise AuthorityError("independent review receipt is stale or future-dated")
    return review, digest(protected_file(review_path, "independent review receipt"))


def load_private_key(path: Path, passphrase: bytes) -> Ed25519PrivateKey:
    try:
        key = load_pem_private_key(
            protected_file(path, "authority private key"), passphrase
        )
    except (TypeError, ValueError) as exc:
        raise AuthorityError("authority private key could not be unlocked") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise AuthorityError("authority private key is not Ed25519")
    return key


def issue_approval(
    root: Path,
    *,
    registry_path: Path,
    trusted_key_path: Path,
    private_key_path: Path,
    expected_key_id: str,
    review_path: Path,
    candidate_sha: str,
    migration_head: str,
    backup_receipt_sha256: str,
    restore_receipt_sha256: str,
    rollback_target_sha: str,
    rollback_target_release: str,
    output_path: Path,
    passphrase: bytes,
    ttl_hours: int = 1,
    now: datetime | None = None,
) -> dict[str, Any]:
    observed = (now or utc_now()).astimezone(timezone.utc)
    if not 1 <= ttl_hours <= 24:
        raise AuthorityError("approval lifetime must be between 1 and 24 hours")
    validate_release_binding(
        candidate_sha=candidate_sha,
        migration_head=migration_head,
        backup_receipt_sha256=backup_receipt_sha256,
        restore_receipt_sha256=restore_receipt_sha256,
        rollback_target_sha=rollback_target_sha,
        rollback_target_release=rollback_target_release,
    )
    registry, enrolled_key, public_key = validate_registry(
        registry_path,
        trusted_key_path,
        expected_key_id=expected_key_id,
        now=observed,
        for_issuance=True,
    )
    review, review_digest = validate_review(
        review_path,
        registry,
        candidate_sha=candidate_sha,
        migration_head=migration_head,
        backup_receipt_sha256=backup_receipt_sha256,
        restore_receipt_sha256=restore_receipt_sha256,
        rollback_target_sha=rollback_target_sha,
        rollback_target_release=rollback_target_release,
        now=observed,
    )
    private_key = load_private_key(private_key_path, passphrase)
    if public_fingerprint(private_key.public_key()) != public_fingerprint(public_key):
        raise AuthorityError("authority private key does not match enrolled public key")
    expires_at = observed + timedelta(hours=ttl_hours)
    key_expiry = parse_time(enrolled_key["expires_at"], "key expires_at")
    if expires_at > key_expiry:
        raise AuthorityError("approval would outlive the enrolled authority key")
    authority = registry["authority"]
    custodian = authority["custodian"]
    unsigned: dict[str, Any] = {
        "contract": APPROVAL_CONTRACT,
        "approval_id": str(uuid.uuid4()),
        "candidate_sha": candidate_sha,
        "migration_head": migration_head,
        "backup_receipt_sha256": backup_receipt_sha256,
        "restore_receipt_sha256": restore_receipt_sha256,
        "rollback_target": {
            "sha": rollback_target_sha,
            "release": rollback_target_release,
        },
        "scope": SCOPE,
        "issued_at": timestamp(observed),
        "expires_at": timestamp(expires_at),
        "authorized_issuer": {
            "id": authority["id"],
            "role": authority["role"],
            "custodian_id": custodian["id"],
            "custodian_name": custodian["name"],
            "key_id": expected_key_id,
        },
        "authority_enrollment_digest": enrolled_key["enrollment_digest"],
        "independent_review": {
            "review_id": review["review_id"],
            "reviewer": review["reviewer"],
            "review_receipt_sha256": review_digest,
            "evidence_archive_sha256": review["evidence_archive_sha256"],
            "reviewed_at": review["reviewed_at"],
        },
    }
    artifact_digest = object_digest(unsigned)
    signed = {**unsigned, "artifact_digest": artifact_digest}
    signature = private_key.sign(canonical(signed))
    artifact = {
        **signed,
        "signature": {
            "algorithm": "Ed25519",
            "encoding": "base64",
            "value": base64.b64encode(signature).decode(),
        },
    }
    atomic_private_json(output_path, artifact)
    append_audit(
        ensure_private_root(root),
        "approval.issued",
        {
            "approval_id": artifact["approval_id"],
            "artifact_digest": artifact_digest,
            "candidate_sha": candidate_sha,
            "key_id": expected_key_id,
            "review_id": review["review_id"],
            "expires_at": artifact["expires_at"],
        },
        now=observed,
    )
    return artifact


def validate_approval(
    artifact_path: Path,
    registry_path: Path,
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
    observed = (now or utc_now()).astimezone(timezone.utc)
    validate_release_binding(
        candidate_sha=candidate_sha,
        migration_head=migration_head,
        backup_receipt_sha256=backup_receipt_sha256,
        restore_receipt_sha256=restore_receipt_sha256,
        rollback_target_sha=rollback_target_sha,
        rollback_target_release=rollback_target_release,
    )
    registry, enrolled_key, public_key = validate_registry(
        registry_path,
        trusted_key_path,
        expected_key_id=expected_key_id,
        now=observed,
    )
    artifact = protected_json(artifact_path, "approval artifact")
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
        "authority_enrollment_digest",
        "independent_review",
        "artifact_digest",
        "signature",
    }
    if set(artifact) != required or artifact.get("contract") != APPROVAL_CONTRACT:
        raise AuthorityError("approval artifact fields do not match v2 contract")
    try:
        uuid.UUID(str(artifact.get("approval_id")))
    except ValueError as exc:
        raise AuthorityError("approval ID is invalid") from exc
    expected_values = {
        "candidate_sha": candidate_sha,
        "migration_head": migration_head,
        "backup_receipt_sha256": backup_receipt_sha256,
        "restore_receipt_sha256": restore_receipt_sha256,
        "scope": SCOPE,
    }
    for field, expected in expected_values.items():
        if artifact.get(field) != expected:
            raise AuthorityError(f"approval {field} does not match requested release")
    if artifact.get("rollback_target") != {
        "sha": rollback_target_sha,
        "release": rollback_target_release,
    }:
        raise AuthorityError(
            "approval rollback target does not match requested release"
        )
    issuer = artifact.get("authorized_issuer")
    authority = registry["authority"]
    custodian = authority["custodian"]
    expected_issuer = {
        "id": authority["id"],
        "role": authority["role"],
        "custodian_id": custodian["id"],
        "custodian_name": custodian["name"],
        "key_id": expected_key_id,
    }
    if issuer != expected_issuer:
        raise AuthorityError("approval issuer does not match enrolled authority")
    if artifact.get("authority_enrollment_digest") != enrolled_key["enrollment_digest"]:
        raise AuthorityError("approval is not bound to the enrolled authority key")
    review = artifact.get("independent_review")
    enrolled_reviewer = registry["independent_review"]["reviewer"]
    if not isinstance(review, dict) or review.get("reviewer") != enrolled_reviewer:
        raise AuthorityError("approval independent review is not enrolled")
    require_sha(str(review.get("review_receipt_sha256")), "review receipt SHA")
    require_sha(
        str(review.get("evidence_archive_sha256")), "review evidence archive SHA"
    )
    try:
        uuid.UUID(str(review.get("review_id")))
    except ValueError as exc:
        raise AuthorityError("approval independent review ID is invalid") from exc
    issued = parse_time(artifact.get("issued_at"), "issued_at")
    expires = parse_time(artifact.get("expires_at"), "expires_at")
    reviewed = parse_time(review.get("reviewed_at"), "reviewed_at")
    if expires <= issued or expires - issued > MAX_APPROVAL_TTL:
        raise AuthorityError("approval lifetime is invalid")
    if reviewed > issued or issued - reviewed > MAX_REVIEW_AGE:
        raise AuthorityError("approval is not backed by a current independent review")
    if observed < issued or observed >= expires:
        raise AuthorityError("approval is expired or not yet valid")
    supplied_digest = artifact.get("artifact_digest")
    require_sha(str(supplied_digest), "artifact digest")
    unsigned = dict(artifact)
    signature = unsigned.pop("signature")
    unsigned.pop("artifact_digest")
    if supplied_digest != object_digest(unsigned):
        raise AuthorityError("approval artifact digest does not match its contents")
    if not isinstance(signature, dict) or set(signature) != {
        "algorithm",
        "encoding",
        "value",
    }:
        raise AuthorityError("approval signature is invalid")
    if signature.get("algorithm") != "Ed25519" or signature.get("encoding") != "base64":
        raise AuthorityError("approval signature algorithm is invalid")
    signature_value = signature.get("value")
    if not isinstance(signature_value, str):
        raise AuthorityError("approval signature encoding is invalid")
    try:
        signature_bytes = base64.b64decode(signature_value, validate=True)
    except (ValueError, binascii.Error, TypeError) as exc:
        raise AuthorityError("approval signature encoding is invalid") from exc
    if len(signature_bytes) != 64:
        raise AuthorityError("approval signature length is invalid")
    try:
        public_key.verify(
            signature_bytes, canonical({**unsigned, "artifact_digest": supplied_digest})
        )
    except Exception as exc:  # cryptography exposes InvalidSignature outside stdlib
        raise AuthorityError(
            "approval signature does not verify against enrolled authority"
        ) from exc
    return {
        "contract": APPROVAL_CONTRACT,
        "approval_id": str(artifact["approval_id"]),
        "candidate_sha": candidate_sha,
        "migration_head": migration_head,
        "scope": SCOPE,
        "issuer": AUTHORITY_ID,
        "custodian": str(custodian["name"]),
        "key_id": expected_key_id,
        "expires_at": timestamp(expires),
        "artifact_digest": str(supplied_digest),
        "review_id": str(review["review_id"]),
    }


def rotate_key(
    root: Path,
    *,
    registry_path: Path,
    current_key_id: str,
    current_private_key_path: Path,
    current_passphrase: bytes,
    new_passphrase: bytes,
    owner_approval_id: str,
    validity_days: int = 90,
    now: datetime | None = None,
) -> dict[str, Any]:
    observed = (now or utc_now()).astimezone(timezone.utc)
    require_uuid(owner_approval_id, "owner approval ID")
    registry = protected_json(registry_path, "authority registry")
    if registry.get("registry_digest") != object_digest(
        registry_without_digest(registry)
    ):
        raise AuthorityError("authority registry digest is invalid")
    registry_authority = registry.get("authority")
    if (
        registry.get("contract") != AUTHORITY_CONTRACT
        or not isinstance(registry_authority, dict)
        or registry_authority.get("id") != AUTHORITY_ID
        or registry.get("issuer_utility_sha256") != utility_digest()
    ):
        raise AuthorityError("authority registry identity or issuer utility is invalid")
    current_matches = [
        key for key in registry.get("keys", []) if key.get("key_id") == current_key_id
    ]
    if len(current_matches) != 1 or current_matches[0].get("status") != "active":
        raise AuthorityError("current authority key is not active")
    current_private = load_private_key(current_private_key_path, current_passphrase)
    if (
        public_fingerprint(current_private.public_key())
        != current_matches[0]["public_key_sha256"]
    ):
        raise AuthorityError("current private key does not authorize rotation")
    private_bytes, public_bytes, public_key = encrypted_key_material(new_passphrase)
    fingerprint = public_fingerprint(public_key)
    new_key_id = key_id_for(public_key, observed)
    valid_from = timestamp(observed)
    expires_at = timestamp(observed + timedelta(days=validity_days))
    custodian_id = registry["authority"]["custodian"]["id"]
    enrollment_digest = key_enrollment_digest(
        authority_id=AUTHORITY_ID,
        custodian_id=custodian_id,
        key_id=new_key_id,
        fingerprint=fingerprint,
        valid_from=valid_from,
        expires_at=expires_at,
        owner_approval_id=owner_approval_id,
    )
    protected_root = ensure_private_root(root)
    private_path = protected_root / "private" / f"{new_key_id}.private.pem"
    public_path = protected_root / "public" / f"{new_key_id}.public.pem"
    atomic_private_write(private_path, private_bytes)
    atomic_private_write(public_path, public_bytes)
    for key in registry["keys"]:
        if key["key_id"] == current_key_id:
            key["status"] = "verification_only"
            key["verify_until"] = timestamp(observed + MAX_APPROVAL_TTL)
    registry["keys"].append(
        {
            "key_id": new_key_id,
            "algorithm": "Ed25519",
            "public_key_file": f"public/{new_key_id}.public.pem",
            "private_key_file": f"private/{new_key_id}.private.pem",
            "public_key_sha256": fingerprint,
            "valid_from": valid_from,
            "expires_at": expires_at,
            "status": "active",
            "enrollment_digest": enrollment_digest,
            "owner_approval_id": owner_approval_id,
        }
    )
    sealed = seal_registry(registry)
    atomic_private_json(registry_path, sealed)
    append_audit(
        protected_root,
        "authority.key_rotated",
        {
            "previous_key_id": current_key_id,
            "new_key_id": new_key_id,
            "enrollment_digest": enrollment_digest,
            "owner_approval_id": owner_approval_id,
        },
        now=observed,
    )
    return {
        "key_id": new_key_id,
        "public_key_sha256": fingerprint,
        "expires_at": expires_at,
        "enrollment_digest": enrollment_digest,
        "public_key_reference": str(public_path),
        "private_key_reference": str(private_path),
    }


def revoke_key(
    root: Path,
    *,
    registry_path: Path,
    key_id: str,
    private_key_path: Path,
    passphrase: bytes,
    reason: str,
    owner_approval_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not reason.strip():
        raise AuthorityError("revocation reason is required")
    observed = (now or utc_now()).astimezone(timezone.utc)
    require_uuid(owner_approval_id, "owner approval ID")
    registry = protected_json(registry_path, "authority registry")
    if registry.get("registry_digest") != object_digest(
        registry_without_digest(registry)
    ):
        raise AuthorityError("authority registry digest is invalid")
    registry_authority = registry.get("authority")
    if (
        registry.get("contract") != AUTHORITY_CONTRACT
        or not isinstance(registry_authority, dict)
        or registry_authority.get("id") != AUTHORITY_ID
        or registry.get("issuer_utility_sha256") != utility_digest()
    ):
        raise AuthorityError("authority registry identity or issuer utility is invalid")
    matches = [key for key in registry.get("keys", []) if key.get("key_id") == key_id]
    if len(matches) != 1 or matches[0].get("status") == "revoked":
        raise AuthorityError("authority key is unavailable or already revoked")
    private_key = load_private_key(private_key_path, passphrase)
    if public_fingerprint(private_key.public_key()) != matches[0]["public_key_sha256"]:
        raise AuthorityError("private key does not authorize revocation")
    matches[0]["status"] = "revoked"
    matches[0]["revoked_at"] = timestamp(observed)
    matches[0]["revocation_reason"] = reason.strip()
    matches[0]["revocation_approval_id"] = owner_approval_id
    sealed = seal_registry(registry)
    atomic_private_json(registry_path, sealed)
    append_audit(
        ensure_private_root(root),
        "authority.key_revoked",
        {
            "key_id": key_id,
            "reason": reason.strip(),
            "owner_approval_id": owner_approval_id,
        },
        now=observed,
    )
    return {"key_id": key_id, "status": "revoked", "revoked_at": timestamp(observed)}


def prompt_secret(label: str, *, confirm: bool = False) -> bytes:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise AuthorityError(f"{label} requires an interactive owner terminal")
    first = getpass.getpass(f"{label}: ").encode()
    if confirm:
        second = getpass.getpass(f"Confirm {label}: ").encode()
        if first != second:
            raise AuthorityError("private-key passphrases do not match")
    return first


def require_phrase(expected: str) -> None:
    if not sys.stdin.isatty():
        raise AuthorityError("owner confirmation requires an interactive terminal")
    supplied = input(f"Type exactly '{expected}' to continue: ").strip()
    if supplied != expected:
        raise AuthorityError("owner confirmation phrase did not match")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)

    enroll = commands.add_parser("enroll")
    enroll.add_argument("--authority-root", type=Path, required=True)
    enroll.add_argument("--custodian-id", default="michael-fouse")
    enroll.add_argument("--custodian-name", default="Michael Fouse")
    enroll.add_argument("--reviewer-id", required=True)
    enroll.add_argument("--reviewer-name", required=True)
    enroll.add_argument("--owner-approval-id", required=True)
    enroll.add_argument("--validity-days", type=int, default=90)

    issue = commands.add_parser("issue")
    issue.add_argument("--authority-root", type=Path, required=True)
    issue.add_argument("--registry", type=Path, required=True)
    issue.add_argument("--trusted-key", type=Path, required=True)
    issue.add_argument("--private-key", type=Path, required=True)
    issue.add_argument("--key-id", required=True)
    issue.add_argument("--review-receipt", type=Path, required=True)
    issue.add_argument("--candidate-sha", required=True)
    issue.add_argument("--migration-head", required=True)
    issue.add_argument("--backup-receipt-sha256", required=True)
    issue.add_argument("--restore-receipt-sha256", required=True)
    issue.add_argument("--rollback-target-sha", required=True)
    issue.add_argument("--rollback-target-release", required=True)
    issue.add_argument("--ttl-hours", type=int, default=1)
    issue.add_argument("--output", type=Path, required=True)

    validate = commands.add_parser("validate")
    validate.add_argument("--artifact", type=Path, required=True)
    validate.add_argument("--registry", type=Path, required=True)
    validate.add_argument("--trusted-key", type=Path, required=True)
    validate.add_argument("--key-id", required=True)
    validate.add_argument("--candidate-sha", required=True)
    validate.add_argument("--migration-head", required=True)
    validate.add_argument("--backup-receipt-sha256", required=True)
    validate.add_argument("--restore-receipt-sha256", required=True)
    validate.add_argument("--rollback-target-sha", required=True)
    validate.add_argument("--rollback-target-release", required=True)

    rotate = commands.add_parser("rotate")
    rotate.add_argument("--authority-root", type=Path, required=True)
    rotate.add_argument("--registry", type=Path, required=True)
    rotate.add_argument("--current-key-id", required=True)
    rotate.add_argument("--current-private-key", type=Path, required=True)
    rotate.add_argument("--owner-approval-id", required=True)
    rotate.add_argument("--validity-days", type=int, default=90)

    revoke = commands.add_parser("revoke")
    revoke.add_argument("--authority-root", type=Path, required=True)
    revoke.add_argument("--registry", type=Path, required=True)
    revoke.add_argument("--key-id", required=True)
    revoke.add_argument("--private-key", type=Path, required=True)
    revoke.add_argument("--reason", required=True)
    revoke.add_argument("--owner-approval-id", required=True)

    audit = commands.add_parser("verify-audit")
    audit.add_argument("--authority-root", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "enroll":
            require_phrase("ENROLL TWELVEHATS BETA AUTHORITY")
            secret = prompt_secret(
                "Encrypted authority private-key passphrase", confirm=True
            )
            output = create_enrollment(
                args.authority_root,
                custodian_id=args.custodian_id,
                custodian_name=args.custodian_name,
                reviewer_id=args.reviewer_id,
                reviewer_name=args.reviewer_name,
                owner_approval_id=args.owner_approval_id,
                passphrase=secret,
                validity_days=args.validity_days,
            )
        elif args.command == "issue":
            require_phrase("ISSUE BETA RELEASE APPROVAL")
            secret = prompt_secret("Authority private-key passphrase")
            output = issue_approval(
                args.authority_root,
                registry_path=args.registry,
                trusted_key_path=args.trusted_key,
                private_key_path=args.private_key,
                expected_key_id=args.key_id,
                review_path=args.review_receipt,
                candidate_sha=args.candidate_sha,
                migration_head=args.migration_head,
                backup_receipt_sha256=args.backup_receipt_sha256,
                restore_receipt_sha256=args.restore_receipt_sha256,
                rollback_target_sha=args.rollback_target_sha,
                rollback_target_release=args.rollback_target_release,
                output_path=args.output,
                passphrase=secret,
                ttl_hours=args.ttl_hours,
            )
        elif args.command == "validate":
            output = validate_approval(
                args.artifact,
                args.registry,
                args.trusted_key,
                expected_key_id=args.key_id,
                candidate_sha=args.candidate_sha,
                migration_head=args.migration_head,
                backup_receipt_sha256=args.backup_receipt_sha256,
                restore_receipt_sha256=args.restore_receipt_sha256,
                rollback_target_sha=args.rollback_target_sha,
                rollback_target_release=args.rollback_target_release,
            )
        elif args.command == "rotate":
            require_phrase("ROTATE TWELVEHATS BETA AUTHORITY KEY")
            current_secret = prompt_secret("Current authority private-key passphrase")
            new_secret = prompt_secret(
                "New encrypted authority private-key passphrase", confirm=True
            )
            output = rotate_key(
                args.authority_root,
                registry_path=args.registry,
                current_key_id=args.current_key_id,
                current_private_key_path=args.current_private_key,
                current_passphrase=current_secret,
                new_passphrase=new_secret,
                owner_approval_id=args.owner_approval_id,
                validity_days=args.validity_days,
            )
        elif args.command == "revoke":
            require_phrase("REVOKE TWELVEHATS BETA AUTHORITY KEY")
            secret = prompt_secret("Authority private-key passphrase")
            output = revoke_key(
                args.authority_root,
                registry_path=args.registry,
                key_id=args.key_id,
                private_key_path=args.private_key,
                passphrase=secret,
                reason=args.reason,
                owner_approval_id=args.owner_approval_id,
            )
        else:
            output = verify_audit(ensure_private_root(args.authority_root))
    except AuthorityError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"result": "PASS", **output}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
