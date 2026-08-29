"""Deterministic native-identity matching for Enterprise Service Locations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

MATCHING_CONTRACT_VERSION = "native-service-location-matching/v1"


class NativeLocationMatchOutcome(StrEnum):
    MATCHED = "matched"
    NO_MATCH = "no_match"
    IDENTITY_NOT_READY = "identity_not_ready"
    DUPLICATE_NATIVE_IDENTITY = "duplicate_native_identity"
    AMBIGUOUS_ADDRESS = "ambiguous_address"
    ADDRESS_REVIEW_REQUIRED = "address_review_required"
    PARENT_MISMATCH = "parent_mismatch"
    EXISTING_BINDING_CONFLICT = "existing_binding_conflict"
    COMPANY_BRANCH_SCOPE_CONFLICT = "company_branch_scope_conflict"


@dataclass(frozen=True)
class AcquiredNativeLocation:
    identity_evidence_id: UUID
    company_id: UUID
    branch_id: UUID
    source_location_id_sha256: str | None
    source_customer_id_sha256: str | None
    customer_source_identity_id: UUID | None
    normalized_address_sha256: str | None
    readiness: str
    evidence_digest: str
    accepted_service_location_id: UUID | None = None


@dataclass(frozen=True)
class EnterpriseLocationCandidate:
    service_location_id: UUID
    company_id: UUID
    branch_id: UUID
    customer_id: UUID
    customer_source_identity_id: UUID
    source_customer_id_sha256: str
    normalized_address_sha256: str
    source_location_id_sha256: str | None = None


@dataclass(frozen=True)
class NativeLocationMatchResult:
    identity_evidence_id: UUID
    outcome: NativeLocationMatchOutcome
    service_location_id: UUID | None
    customer_id: UUID | None
    candidate_count: int
    input_digest: str
    evidence_digest: str


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def match_native_location(
    acquired: AcquiredNativeLocation,
    candidates: tuple[EnterpriseLocationCandidate, ...],
) -> NativeLocationMatchResult:
    """Match only authoritative identity; address matches remain owner-review evidence."""
    ordered = tuple(sorted(candidates, key=lambda item: str(item.service_location_id)))
    input_digest = _digest([MATCHING_CONTRACT_VERSION, acquired, ordered])
    outcome = NativeLocationMatchOutcome.NO_MATCH
    target: EnterpriseLocationCandidate | None = None
    candidate_count = 0

    if acquired.readiness != "ready" or acquired.source_location_id_sha256 is None:
        outcome = NativeLocationMatchOutcome.IDENTITY_NOT_READY
    else:
        native_matches = tuple(
            item
            for item in ordered
            if item.source_location_id_sha256 == acquired.source_location_id_sha256
        )
        scoped = tuple(
            item
            for item in native_matches
            if item.company_id == acquired.company_id
            and item.branch_id == acquired.branch_id
        )
        if native_matches and len(scoped) != len(native_matches):
            outcome = NativeLocationMatchOutcome.COMPANY_BRANCH_SCOPE_CONFLICT
            candidate_count = len(native_matches)
        elif len(scoped) > 1:
            outcome = NativeLocationMatchOutcome.DUPLICATE_NATIVE_IDENTITY
            candidate_count = len(scoped)
        elif len(scoped) == 1:
            candidate_count = 1
            candidate = scoped[0]
            if (
                acquired.customer_source_identity_id is None
                or candidate.customer_source_identity_id
                != acquired.customer_source_identity_id
                or candidate.source_customer_id_sha256
                != acquired.source_customer_id_sha256
            ):
                outcome = NativeLocationMatchOutcome.PARENT_MISMATCH
            elif (
                acquired.accepted_service_location_id is not None
                and acquired.accepted_service_location_id
                != candidate.service_location_id
            ):
                outcome = NativeLocationMatchOutcome.EXISTING_BINDING_CONFLICT
            else:
                outcome = NativeLocationMatchOutcome.MATCHED
                target = candidate
        else:
            address_matches = tuple(
                item
                for item in ordered
                if item.company_id == acquired.company_id
                and item.branch_id == acquired.branch_id
                and item.customer_source_identity_id
                == acquired.customer_source_identity_id
                and acquired.normalized_address_sha256 is not None
                and item.normalized_address_sha256 == acquired.normalized_address_sha256
            )
            candidate_count = len(address_matches)
            if len(address_matches) > 1:
                outcome = NativeLocationMatchOutcome.AMBIGUOUS_ADDRESS
            elif len(address_matches) == 1:
                outcome = NativeLocationMatchOutcome.ADDRESS_REVIEW_REQUIRED

    evidence_digest = _digest(
        [
            MATCHING_CONTRACT_VERSION,
            acquired.identity_evidence_id,
            outcome.value,
            target.service_location_id if target else None,
            target.customer_id if target else None,
            candidate_count,
            input_digest,
        ]
    )
    return NativeLocationMatchResult(
        identity_evidence_id=acquired.identity_evidence_id,
        outcome=outcome,
        service_location_id=target.service_location_id if target else None,
        customer_id=target.customer_id if target else None,
        candidate_count=candidate_count,
        input_digest=input_digest,
        evidence_digest=evidence_digest,
    )
