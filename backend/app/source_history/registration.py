"""Tenant-scoped registration of sealed historical source manifests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SealedSourceManifest:
    provider: str
    company_id: UUID
    source_digest: str
    object_count: int
    acquired_at: str
    get_only: bool
    manifest_digest: str


@dataclass(frozen=True, slots=True)
class SourceRegistration:
    registration_id: str
    provider: str
    company_id: UUID
    source_digest: str
    manifest_digest: str
    object_count: int
    provenance: dict[str, object]
    read_only: bool = True
    admitted_as_native: bool = False


def canonical_manifest_digest(manifest: SealedSourceManifest) -> str:
    value = {
        "provider": manifest.provider,
        "company_id": str(manifest.company_id),
        "source_digest": manifest.source_digest,
        "object_count": manifest.object_count,
        "acquired_at": manifest.acquired_at,
        "get_only": manifest.get_only,
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def register_sealed_source(
    manifest: SealedSourceManifest | None, *, expected_company_id: UUID
) -> SourceRegistration:
    if manifest is None:
        raise ValueError("sealed source manifest is unavailable")
    if manifest.company_id != expected_company_id:
        raise PermissionError("sealed source tenant binding mismatch")
    if not manifest.get_only:
        raise ValueError("sealed source manifest is not read-only")
    if manifest.object_count < 0:
        raise ValueError("sealed source object count is invalid")
    for name, digest in (
        ("source", manifest.source_digest),
        ("manifest", manifest.manifest_digest),
    ):
        if len(digest) != 64:
            raise ValueError(f"sealed {name} digest is invalid")
    if canonical_manifest_digest(manifest) != manifest.manifest_digest:
        raise ValueError("sealed source manifest checksum mismatch")
    identity = hashlib.sha256(
        f"{manifest.company_id}:{manifest.provider}:{manifest.source_digest}".encode()
    ).hexdigest()
    return SourceRegistration(
        identity,
        manifest.provider,
        manifest.company_id,
        manifest.source_digest,
        manifest.manifest_digest,
        manifest.object_count,
        {
            "acquired_at": manifest.acquired_at,
            "get_only": True,
            "custody": "sealed_manifest",
        },
    )
