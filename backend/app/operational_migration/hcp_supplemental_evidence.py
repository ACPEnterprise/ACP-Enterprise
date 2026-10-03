"""Fail-closed HCP attachment, membership, and review evidence authority.

The provider API is not assumed to enumerate these domains completely.  This
module therefore consumes sealed exports/manifests and produces deterministic
evidence packets without treating an absent API result as an empty population.
It does not mutate native business records.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path, PurePath
from typing import Any, Final

CONTRACT: Final = "hcp-supplemental-evidence/v1"
ATTACHMENT_DOMAINS: Final = frozenset(
    {"customer", "job", "estimate", "open_work"}
)


class AttachmentState(StrEnum):
    AVAILABLE = "AVAILABLE"
    IMPORTED = "IMPORTED"
    FAILED = "FAILED"
    MISSING_SOURCE = "MISSING_SOURCE"
    UNKNOWN_PROVIDER_INVENTORY = "UNKNOWN_PROVIDER_INVENTORY"
    RETRY_REQUIRED = "RETRY_REQUIRED"
    OWNER_EXPORT_REQUIRED = "OWNER_EXPORT_REQUIRED"


class EvidenceDisposition(StrEnum):
    SOURCE = "SOURCE"
    ADMITTED = "ADMITTED"
    HELD = "HELD"
    UNKNOWN = "UNKNOWN"
    UNEXPLAINED = "UNEXPLAINED"


@dataclass(frozen=True)
class CustodyResult:
    storage_reference: str
    content_digest: str
    byte_size: int
    replayed: bool


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def import_attachment_content(
    *,
    source_path: Path,
    custody_root: Path,
    company_id: str,
    provider_attachment_id: str,
    expected_digest: str,
    expected_size: int,
) -> CustodyResult:
    """Copy a verified source object into immutable, company-scoped custody."""
    _path_component(company_id, "company_id")
    _identity(provider_attachment_id, "provider_attachment_id")
    _sha256(expected_digest, "expected_digest")
    if expected_size < 0:
        raise ValueError("expected_size must not be negative")
    if not source_path.is_file() or source_path.is_symlink():
        raise ValueError("attachment source must be a regular file")
    actual_size = source_path.stat().st_size
    actual_digest = file_sha256(source_path)
    if actual_size != expected_size or actual_digest != expected_digest:
        raise ValueError("attachment content does not match sealed metadata")

    company_root = custody_root / company_id
    company_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(company_root, 0o700)
    target = company_root / actual_digest
    if target.exists():
        if not target.is_file() or file_sha256(target) != actual_digest:
            raise ValueError("custody digest collision or corrupted replay target")
        return CustodyResult(
            f"hcp-custody:{company_id}:{actual_digest}",
            actual_digest,
            actual_size,
            True,
        )

    temporary = company_root / f".{actual_digest}.partial"
    try:
        with source_path.open("rb") as source, temporary.open("xb") as destination:
            shutil.copyfileobj(source, destination)
            destination.flush()
            os.fsync(destination.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return CustodyResult(
        f"hcp-custody:{company_id}:{actual_digest}",
        actual_digest,
        actual_size,
        False,
    )


def attachment_retry_queue(packet: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """Return a deterministic queue without converting permanent gaps to retries."""
    if packet.get("contract") != CONTRACT or packet.get("domain") != "attachments":
        raise ValueError("attachment retry queue requires an attachment packet")
    records = packet.get("records")
    if not isinstance(records, list):
        raise TypeError("attachment packet records must be a list")
    retryable = {
        AttachmentState.FAILED.value,
        AttachmentState.RETRY_REQUIRED.value,
    }
    return tuple(
        sorted(
            (
                {
                    "provider_attachment_id": row["provider_attachment_id"],
                    "parent_type": row["parent_type"],
                    "parent_source_id": row["parent_source_id"],
                    "prior_state": row["state"],
                    "prior_error_reason": row["error_reason"],
                }
                for row in records
                if isinstance(row, Mapping)
                and row.get("state") in retryable
                and row.get("provider_attachment_id") is not None
            ),
            key=lambda row: str(row["provider_attachment_id"]),
        )
    )


def build_attachment_authority(
    *,
    company_id: str,
    acquired_at: str,
    inventory_complete: bool,
    records: Iterable[Mapping[str, Any]],
    known_parents: Mapping[str, set[str]],
) -> dict[str, Any]:
    """Seal attachment metadata and preserve unknown provider inventory."""
    _identity(company_id, "company_id")
    _time(acquired_at, "acquired_at")
    normalized: list[dict[str, Any]] = []
    identities: set[str] = set()
    for raw in records:
        source_id = _identity(raw.get("provider_attachment_id"), "attachment identity")
        if source_id in identities:
            raise ValueError(f"duplicate provider attachment identity: {source_id}")
        identities.add(source_id)
        parent_type = _identity(raw.get("parent_type"), "parent_type")
        if parent_type not in ATTACHMENT_DOMAINS:
            raise ValueError(f"unsupported attachment parent type: {parent_type}")
        parent_id = _identity(raw.get("parent_source_id"), "parent_source_id")
        state = AttachmentState(_identity(raw.get("state"), "attachment state"))
        filename = _safe_filename(raw.get("filename"))
        media_type = _identity(raw.get("media_type"), "media_type")
        created_at = _optional_time(raw.get("created_at"), "created_at")
        digest_value = raw.get("content_digest")
        byte_size = raw.get("byte_size")
        custody = raw.get("storage_reference")
        error_reason = raw.get("error_reason")
        if state is AttachmentState.IMPORTED:
            _sha256(digest_value, "content_digest")
            if not isinstance(byte_size, int) or byte_size < 0:
                raise ValueError("imported attachment requires a valid byte_size")
            if not isinstance(custody, str) or not custody.startswith("hcp-custody:"):
                raise ValueError("imported attachment requires opaque custody reference")
        if state in {AttachmentState.FAILED, AttachmentState.RETRY_REQUIRED}:
            _identity(error_reason, "error_reason")
        parent_known = parent_id in known_parents.get(parent_type, set())
        disposition = _attachment_disposition(state, parent_known)
        normalized.append(
            {
                "provider_attachment_id": source_id,
                "parent_type": parent_type,
                "parent_source_id": parent_id,
                "parent_known": parent_known,
                "filename": filename,
                "media_type": media_type,
                "created_at": created_at,
                "uploader_reference": raw.get("uploader_reference"),
                "content_digest": digest_value,
                "byte_size": byte_size,
                "storage_reference": custody,
                "state": state.value,
                "disposition": disposition.value,
                "error_reason": error_reason,
                "provenance": _provenance(raw.get("provenance")),
            }
        )
    if not inventory_complete:
        normalized.append(
            {
                "provider_attachment_id": None,
                "parent_type": None,
                "parent_source_id": None,
                "parent_known": None,
                "filename": None,
                "media_type": None,
                "created_at": None,
                "uploader_reference": None,
                "content_digest": None,
                "byte_size": None,
                "storage_reference": None,
                "state": AttachmentState.UNKNOWN_PROVIDER_INVENTORY.value,
                "disposition": EvidenceDisposition.UNKNOWN.value,
                "error_reason": "provider inventory completeness is not authoritative",
                "provenance": {"source": "provider_inventory_boundary"},
            }
        )
    return _packet("attachments", company_id, acquired_at, normalized)


def build_membership_authority(
    *, company_id: str, acquired_at: str, records: Iterable[Mapping[str, Any]]
) -> dict[str, Any]:
    """Classify provider service plans without manufacturing current entitlement."""
    normalized: list[dict[str, Any]] = []
    identities: set[str] = set()
    for raw in records:
        source_id = _identity(raw.get("provider_plan_id"), "provider_plan_id")
        if source_id in identities:
            raise ValueError(f"duplicate provider plan identity: {source_id}")
        identities.add(source_id)
        customer_id = _identity(raw.get("customer_source_id"), "customer_source_id")
        source_version = _identity(raw.get("source_version"), "source_version")
        status = _identity(raw.get("status"), "status")
        start = _optional_date(raw.get("start_date"), "start_date")
        end = _optional_date(raw.get("end_date"), "end_date")
        if start and end and end < start:
            raise ValueError("service plan end_date precedes start_date")
        current_assertion = raw.get("current_assertion") is True
        native_agreement_id = raw.get("native_service_agreement_id")
        if native_agreement_id:
            disposition = EvidenceDisposition.ADMITTED
        elif current_assertion:
            disposition = EvidenceDisposition.HELD
        else:
            disposition = EvidenceDisposition.SOURCE
        normalized.append(
            {
                "provider_plan_id": source_id,
                "customer_source_id": customer_id,
                "native_service_agreement_id": native_agreement_id,
                "status": status,
                "start_date": start,
                "end_date": end,
                "recurring_obligations": raw.get("recurring_obligations"),
                "benefits": raw.get("benefits"),
                "source_version": source_version,
                "current_assertion": current_assertion,
                "history_only": not current_assertion,
                "disposition": disposition.value,
                "provenance": _provenance(raw.get("provenance")),
            }
        )
    return _packet("memberships", company_id, acquired_at, normalized)


def build_review_authority(
    *, company_id: str, acquired_at: str, records: Iterable[Mapping[str, Any]]
) -> dict[str, Any]:
    """Seal historical reviews separately from public/marketing authority."""
    normalized: list[dict[str, Any]] = []
    identities: set[str] = set()
    for raw in records:
        source_id = _identity(raw.get("provider_review_id"), "provider_review_id")
        if source_id in identities:
            raise ValueError(f"duplicate provider review identity: {source_id}")
        identities.add(source_id)
        rating = raw.get("rating")
        if not isinstance(rating, (int, float)) or isinstance(rating, bool):
            raise TypeError("review rating must be numeric")
        if float(rating) < 0 or float(rating) > 5:
            raise ValueError("review rating must be between zero and five")
        review_date = _optional_time(raw.get("reviewed_at"), "reviewed_at")
        if review_date is None:
            raise ValueError("reviewed_at is required")
        customer_id = raw.get("customer_source_id")
        job_id = raw.get("job_source_id")
        if customer_id is not None:
            _identity(customer_id, "customer_source_id")
        if job_id is not None:
            _identity(job_id, "job_source_id")
        normalized.append(
            {
                "provider_review_id": source_id,
                "rating": float(rating),
                "review_text": raw.get("review_text"),
                "reviewed_at": review_date,
                "customer_source_id": customer_id,
                "job_source_id": job_id,
                "disposition": EvidenceDisposition.SOURCE.value,
                "authority": "OPERATIONAL_HISTORY_ONLY",
                "public_marketing_authority": False,
                "provenance": _provenance(raw.get("provenance")),
            }
        )
    return _packet("reviews", company_id, acquired_at, normalized)


def build_supplemental_delta(
    *, domain: str, prior_packet: Mapping[str, Any] | None, current_packet: Mapping[str, Any]
) -> dict[str, Any]:
    """Return exact identity/digest changes and completeness counts."""
    if current_packet.get("contract") != CONTRACT or current_packet.get("domain") != domain:
        raise ValueError("current supplemental packet contract/domain mismatch")
    if prior_packet is not None and (
        prior_packet.get("contract") != CONTRACT or prior_packet.get("domain") != domain
    ):
        raise ValueError("prior supplemental packet contract/domain mismatch")
    identity_key = {
        "attachments": "provider_attachment_id",
        "memberships": "provider_plan_id",
        "reviews": "provider_review_id",
    }.get(domain)
    if identity_key is None:
        raise ValueError("unsupported supplemental delta domain")
    prior = _identified_records(prior_packet, identity_key) if prior_packet else {}
    current = _identified_records(current_packet, identity_key)
    changes: list[dict[str, str]] = []
    for source_id in sorted(set(prior) | set(current)):
        if source_id not in prior:
            state = "CREATE"
        elif source_id not in current:
            state = "SOURCE_UNAVAILABLE"
        elif digest(prior[source_id]) == digest(current[source_id]):
            state = "UNCHANGED"
        else:
            state = "CHANGED_REVIEW_REQUIRED"
        changes.append({"source_id": source_id, "state": state})
    result: dict[str, Any] = {
        "contract": "hcp-supplemental-delta/v1",
        "domain": domain,
        "prior_digest": prior_packet.get("digest") if prior_packet else None,
        "current_digest": current_packet.get("digest"),
        "counts": current_packet["counts"],
        "changes": changes,
    }
    result["digest"] = digest(result)
    return result


def _packet(
    domain: str, company_id: str, acquired_at: str, records: list[dict[str, Any]]
) -> dict[str, Any]:
    _identity(company_id, "company_id")
    _time(acquired_at, "acquired_at")
    records.sort(key=lambda row: json.dumps(row, sort_keys=True))
    dispositions = Counter(str(row["disposition"]) for row in records)
    packet: dict[str, Any] = {
        "contract": CONTRACT,
        "domain": domain,
        "company_id": company_id,
        "acquired_at": acquired_at,
        "counts": {
            "source": dispositions[EvidenceDisposition.SOURCE.value],
            "admitted": dispositions[EvidenceDisposition.ADMITTED.value],
            "held": dispositions[EvidenceDisposition.HELD.value],
            "unknown": dispositions[EvidenceDisposition.UNKNOWN.value],
            "unexplained": dispositions[EvidenceDisposition.UNEXPLAINED.value],
        },
        "records": records,
        "guardrails": {
            "exact_provider_identity_only": True,
            "absence_is_zero": False,
            "native_mutation_authorized": False,
        },
    }
    packet["digest"] = digest(packet)
    return packet


def _attachment_disposition(
    state: AttachmentState, parent_known: bool
) -> EvidenceDisposition:
    if not parent_known:
        return EvidenceDisposition.HELD
    if state is AttachmentState.IMPORTED:
        return EvidenceDisposition.ADMITTED
    if state is AttachmentState.AVAILABLE:
        return EvidenceDisposition.SOURCE
    if state in {
        AttachmentState.FAILED,
        AttachmentState.MISSING_SOURCE,
        AttachmentState.RETRY_REQUIRED,
        AttachmentState.OWNER_EXPORT_REQUIRED,
    }:
        return EvidenceDisposition.HELD
    return EvidenceDisposition.UNKNOWN


def _identified_records(
    packet: Mapping[str, Any], identity_key: str
) -> dict[str, Mapping[str, Any]]:
    records = packet.get("records")
    if not isinstance(records, list):
        raise TypeError("supplemental packet records must be a list")
    return {
        str(row[identity_key]): row
        for row in records
        if isinstance(row, Mapping) and row.get(identity_key) is not None
    }


def _identity(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value.strip()


def _path_component(value: object, label: str) -> str:
    result = _identity(value, label)
    if PurePath(result).name != result or result in {".", ".."}:
        raise ValueError(f"{label} must be a single safe path component")
    return result


def _sha256(value: object, label: str) -> str:
    result = _identity(value, label).lower()
    if len(result) != 64 or any(char not in "0123456789abcdef" for char in result):
        raise ValueError(f"{label} must be SHA-256")
    return result


def _safe_filename(value: object) -> str:
    result = _identity(value, "filename")
    if PurePath(result).name != result or result in {".", ".."}:
        raise ValueError("attachment filename must not contain a path")
    return result


def _time(value: object, label: str) -> str:
    result = _identity(value, label)
    parsed = datetime.fromisoformat(result.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware")
    return result


def _optional_time(value: object, label: str) -> str | None:
    return None if value is None else _time(value, label)


def _optional_date(value: object, label: str) -> str | None:
    if value is None:
        return None
    result = _identity(value, label)
    date.fromisoformat(result)
    return result


def _provenance(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("provenance object is required")
    source = _identity(value.get("source"), "provenance.source")
    version = value.get("version")
    if version is not None:
        _identity(version, "provenance.version")
    return {"source": source, "version": version}
