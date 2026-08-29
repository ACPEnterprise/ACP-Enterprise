"""Source-faithful, read-only Housecall Pro acquisition evidence contracts.

This module deliberately contains no HTTP client and no credentials.  It seals
already-acquired provider payloads and keeps acquisition, cutover selection, and
Enterprise acceptance as three independent facts.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

CONTRACT_VERSION = "hcp-source-acquisition/v1"
PROVIDER = "housecall_pro"


class AcquisitionMechanism(StrEnum):
    PUBLIC_API = "public_api"
    NATIVE_EXPORT = "native_export"
    SUPPORT_EXPORT = "support_export"


class ReconciliationState(StrEnum):
    UNCOMPARED = "uncompared"
    CONSISTENT = "consistent"
    CONFLICT = "conflict"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class SourceRelationship:
    relationship: str
    parent_entity: str
    parent_native_id: str | None


@dataclass(frozen=True)
class SnapshotIdentity:
    extraction_id: str
    acquired_at: datetime
    mechanism: AcquisitionMechanism
    source_environment: str
    scope: str
    request_started_at: datetime
    request_completed_at: datetime
    page_count: int
    record_count: int
    raw_artifact_sha256: str


@dataclass(frozen=True)
class SourceEnvelope:
    provider: str
    native_entity: str
    native_id: str
    source_status: str | None
    source_created_at: str | None
    source_updated_at: str | None
    acquired_at: datetime
    extraction_id: str
    relationships: tuple[SourceRelationship, ...]
    company_evidence: Mapping[str, Any] | None
    branch_evidence: Mapping[str, Any] | None
    source_digest: str
    raw_payload: Mapping[str, Any]


@dataclass(frozen=True)
class MigrationHandoff:
    source: SourceEnvelope
    transformation_version: str
    cutover_disposition: str | None
    enterprise_operational_state: str | None
    accepted_enterprise_id: str | None
    reconciliation_state: ReconciliationState


@dataclass(frozen=True)
class SourceAssertion:
    provider: str
    native_entity: str
    native_id: str
    field: str
    original_value: Any
    source_digest: str


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def seal_source_envelope(
    *,
    native_entity: str,
    native_id: str,
    raw_payload: Mapping[str, Any],
    snapshot: SnapshotIdentity,
    source_status: str | None = None,
    source_created_at: str | None = None,
    source_updated_at: str | None = None,
    relationships: tuple[SourceRelationship, ...] = (),
    company_evidence: Mapping[str, Any] | None = None,
    branch_evidence: Mapping[str, Any] | None = None,
) -> SourceEnvelope:
    """Seal a provider payload without normalizing or inventing its values."""
    if not native_entity or not native_id:
        raise ValueError("native entity and native ID are required")
    if snapshot.acquired_at.tzinfo is None:
        raise ValueError("acquisition timestamp must be timezone-aware")
    if any(not r.parent_native_id for r in relationships):
        raise ValueError("missing relationships must be omitted, never fabricated")
    payload = dict(raw_payload)
    return SourceEnvelope(
        provider=PROVIDER,
        native_entity=native_entity,
        native_id=native_id,
        source_status=source_status,
        source_created_at=source_created_at,
        source_updated_at=source_updated_at,
        acquired_at=snapshot.acquired_at,
        extraction_id=snapshot.extraction_id,
        relationships=relationships,
        company_evidence=dict(company_evidence) if company_evidence else None,
        branch_evidence=dict(branch_evidence) if branch_evidence else None,
        source_digest=sha256(payload),
        raw_payload=payload,
    )


def preserve_conflict(*assertions: SourceAssertion) -> tuple[SourceAssertion, ...]:
    """Return all source assertions in deterministic order; choose no winner."""
    if len({(a.provider, a.native_entity, a.native_id, a.field) for a in assertions}) != len(assertions):
        raise ValueError("duplicate source assertion")
    return tuple(sorted(assertions, key=lambda a: (a.field, a.provider, a.native_entity, a.native_id)))


def evidence_key(
    *, entity: str, provider: str, native_id: str, corroborators: Mapping[str, Any]
) -> str:
    """Build a comparison key from native identity plus non-name corroborators.

    This is an evidence-bucketing key, not an automatic identity decision.
    Names are intentionally rejected as sole corroboration.
    """
    safe = {k: v for k, v in corroborators.items() if v not in (None, "", [], {})}
    non_name = {k: v for k, v in safe.items() if "name" not in k.lower()}
    if not provider or not native_id or not non_name:
        raise ValueError("native identity and a non-name corroborator are required")
    return sha256(
        {
            "contract": CONTRACT_VERSION,
            "entity": entity,
            "provider": provider,
            "native_id": native_id,
            "corroborators": non_name,
        }
    )
