"""Deterministic HCP attachment reconciliation and resumable GET-only recovery."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

APPROVED_MEDIA_HOSTS = frozenset(
    {
        "housecall-web-request-attachments-production-us-west-2.s3-accelerate.amazonaws.com",
    }
)
APPROVED_MEDIA_PATH_PREFIXES = ("/request_attachments/files/", "/attachments/")

MediaDisposition = Literal["RECOVERED", "RETRIEVE", "MISSING_BODY"]


@dataclass(frozen=True, slots=True)
class AttachmentReference:
    source_attachment_id: str
    source_job_id: str
    source_customer_id: str
    source_updated_at: str | None
    original_file_name: str | None
    content_type: str | None
    signed_get_url: str | None


@dataclass(frozen=True, slots=True)
class RecoveredMedia:
    source_attachment_id: str
    content_sha256: str
    size_bytes: int
    artifact_name: str


@dataclass(frozen=True, slots=True)
class MediaRecoveryItem:
    reference: AttachmentReference
    disposition: MediaDisposition
    recovered: RecoveredMedia | None
    signed_get_url_sha256: str | None


@dataclass(frozen=True, slots=True)
class MediaRecoveryPlan:
    items: tuple[MediaRecoveryItem, ...]
    orphaned_media: tuple[RecoveredMedia, ...]
    counts: dict[str, int]
    plan_digest: str
    http_method_allowlist: tuple[str, ...] = ("GET",)
    provider_writes_allowed: bool = False


def _is_approved_get_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname in APPROVED_MEDIA_HOSTS
        and parsed.path.startswith(APPROVED_MEDIA_PATH_PREFIXES)
        and parsed.username is None
        and parsed.password is None
    )


def artifact_name(source_attachment_id: str) -> str:
    return f"attachment-{hashlib.sha256(source_attachment_id.encode()).hexdigest()}.bin"


def reconcile_media(
    references: tuple[AttachmentReference, ...],
    recovered_media: tuple[RecoveredMedia, ...],
) -> MediaRecoveryPlan:
    reference_ids = [row.source_attachment_id for row in references]
    recovered_ids = [row.source_attachment_id for row in recovered_media]
    if len(reference_ids) != len(set(reference_ids)):
        raise ValueError("duplicate HCP attachment reference")
    if len(recovered_ids) != len(set(recovered_ids)):
        raise ValueError("duplicate recovered HCP attachment")

    recovered_by_id = {row.source_attachment_id: row for row in recovered_media}
    items: list[MediaRecoveryItem] = []
    for reference in sorted(references, key=lambda row: row.source_attachment_id):
        if not all(
            (
                reference.source_attachment_id,
                reference.source_job_id,
                reference.source_customer_id,
            )
        ):
            raise ValueError("attachment source and parent identities are required")
        recovered = recovered_by_id.get(reference.source_attachment_id)
        if recovered is not None:
            if len(recovered.content_sha256) != 64 or recovered.size_bytes < 0:
                raise ValueError("recovered media evidence is invalid")
            if recovered.artifact_name != artifact_name(reference.source_attachment_id):
                raise ValueError("recovered media artifact identity mismatch")
            disposition: MediaDisposition = "RECOVERED"
        elif reference.signed_get_url is None:
            disposition = "MISSING_BODY"
        elif not _is_approved_get_url(reference.signed_get_url):
            raise ValueError("attachment URL is outside the approved GET scope")
        else:
            disposition = "RETRIEVE"
        url_digest = (
            hashlib.sha256(reference.signed_get_url.encode()).hexdigest()
            if reference.signed_get_url
            else None
        )
        items.append(MediaRecoveryItem(reference, disposition, recovered, url_digest))

    known = set(reference_ids)
    orphaned = tuple(
        sorted(
            (row for row in recovered_media if row.source_attachment_id not in known),
            key=lambda row: row.source_attachment_id,
        )
    )
    counts = {
        "references": len(references),
        "recovered": sum(row.disposition == "RECOVERED" for row in items),
        "retrieve": sum(row.disposition == "RETRIEVE" for row in items),
        "missing_body": sum(row.disposition == "MISSING_BODY" for row in items),
        "orphaned_media": len(orphaned),
    }
    canonical = {
        "items": [
            {
                "attachment": row.reference.source_attachment_id,
                "customer": row.reference.source_customer_id,
                "disposition": row.disposition,
                "job": row.reference.source_job_id,
                "recovered_sha256": (
                    row.recovered.content_sha256 if row.recovered else None
                ),
                "source_updated_at": row.reference.source_updated_at,
                "url_sha256": row.signed_get_url_sha256,
            }
            for row in items
        ],
        "orphans": [row.source_attachment_id for row in orphaned],
    }
    plan_digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return MediaRecoveryPlan(tuple(items), orphaned, counts, plan_digest)
