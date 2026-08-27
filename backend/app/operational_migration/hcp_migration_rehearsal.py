"""Source-faithful HCP migration-candidate rehearsal contracts.

The contracts deliberately stop before persistence. They preserve provider
identity and source digests while separating automatic candidates, explicit
exceptions, owner decisions, cutover-only decisions, and legacy evidence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

CONTRACT_VERSION = "hcp-migration-rehearsal/v1"
PROVIDER = "housecall_pro"


class CandidateDisposition(StrEnum):
    AUTOMATIC = "automatic"
    EXPLICIT_EXCEPTION = "explicit_exception"
    OWNER_DISPOSITION = "owner_disposition"
    CUTOVER_ONLY = "cutover_only"
    LEGACY_NON_BLOCKING = "legacy_non_blocking"


class RelationshipEvidence(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    ABSENT = "ABSENT"
    CONFLICTING = "CONFLICTING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class MigrationCandidate:
    entity: str
    native_id: str
    source_digest: str
    history_layer: str
    disposition: CandidateDisposition
    relationship_evidence: RelationshipEvidence
    parent_native_ids: tuple[str, ...] = ()
    exception_codes: tuple[str, ...] = ()
    transformation_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not self.entity or not self.native_id:
            raise ValueError("entity and provider-native identity are required")
        if len(self.source_digest) != 64:
            raise ValueError("a source digest is required")
        if len(self.parent_native_ids) != len(set(self.parent_native_ids)):
            raise ValueError("duplicate parent identity")
        if self.relationship_evidence is RelationshipEvidence.AVAILABLE and any(
            not value for value in self.parent_native_ids
        ):
            raise ValueError("available relationships cannot contain missing IDs")


@dataclass(frozen=True)
class DecisionPattern:
    code: str
    record_count: int
    priority: int
    options: tuple[str, ...]
    evidence_digest: str

    def __post_init__(self) -> None:
        if not self.code or self.record_count < 1 or not self.options:
            raise ValueError("a decision pattern requires evidence and options")
        if len(self.evidence_digest) != 64:
            raise ValueError("decision evidence digest is invalid")


@dataclass(frozen=True)
class RehearsalResult:
    source_package_sha256: str
    candidate_counts: dict[str, int]
    disposition_counts: dict[str, int]
    exception_counts: dict[str, int]
    decision_patterns: tuple[DecisionPattern, ...]
    candidate_digest: str
    replay_digest: str

    @property
    def deterministic(self) -> bool:
        return self.candidate_digest == self.replay_digest


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode()
    ).hexdigest()


def seal_candidates(candidates: tuple[MigrationCandidate, ...]) -> str:
    """Seal candidates in native-identity order and reject duplicates."""
    identities = [(item.entity, item.native_id) for item in candidates]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate provider-native candidate identity")
    ordered = sorted(candidates, key=lambda item: (item.entity, item.native_id))
    return canonical_sha256(
        {
            "contract": CONTRACT_VERSION,
            "provider": PROVIDER,
            "candidates": [asdict(item) for item in ordered],
        }
    )


def verify_manifest_self_digest(manifest: dict[str, Any]) -> str:
    """Fail closed unless a protected package manifest verifies exactly."""
    payload = dict(manifest)
    declared = payload.pop("manifest_sha256", None)
    actual = canonical_sha256(payload)
    if not isinstance(declared, str) or declared != actual:
        raise ValueError("source package manifest digest mismatch")
    return declared


def verify_company_scope(company_evidence_digests: tuple[str, ...]) -> str:
    """Require one corroborated provider Company before candidate handoff."""
    unique = set(company_evidence_digests)
    if len(unique) != 1 or any(len(value) != 64 for value in unique):
        raise ValueError("candidate package must resolve to exactly one Company")
    return next(iter(unique))


def build_rehearsal_result(
    *,
    source_package_sha256: str,
    candidates: tuple[MigrationCandidate, ...],
    decision_patterns: tuple[DecisionPattern, ...],
) -> RehearsalResult:
    digest = seal_candidates(candidates)
    candidate_counts: dict[str, int] = {}
    dispositions: dict[str, int] = {}
    exceptions: dict[str, int] = {}
    for item in candidates:
        candidate_counts[item.entity] = candidate_counts.get(item.entity, 0) + 1
        key = item.disposition.value
        dispositions[key] = dispositions.get(key, 0) + 1
        for code in item.exception_codes:
            exceptions[code] = exceptions.get(code, 0) + 1
    return RehearsalResult(
        source_package_sha256=source_package_sha256,
        candidate_counts=dict(sorted(candidate_counts.items())),
        disposition_counts=dict(sorted(dispositions.items())),
        exception_counts=dict(sorted(exceptions.items())),
        decision_patterns=tuple(sorted(decision_patterns, key=lambda item: item.priority)),
        candidate_digest=digest,
        replay_digest=seal_candidates(tuple(reversed(candidates))),
    )
