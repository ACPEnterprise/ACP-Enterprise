"""Deterministic consolidation of provider-native Customer identities."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, replace
from enum import StrEnum
from uuid import UUID

from app.customer_migration.native_location_identity import scoped_identity

CONSOLIDATION_CONTRACT_VERSION = "native-customer-identity-consolidation/v1"


class NativeCustomerConsolidationOutcome(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    MISSING_SOURCE_IDENTIFIER = "missing_source_identifier"
    DUPLICATE_SOURCE_EVIDENCE = "duplicate_source_evidence"
    CONFLICTING_SOURCE_EVIDENCE = "conflicting_source_evidence"
    AMBIGUOUS_TARGET = "ambiguous_target"
    EXISTING_BINDING_CONFLICT = "existing_binding_conflict"
    COMPANY_BRANCH_SCOPE_CONFLICT = "company_branch_scope_conflict"
    MULTIPLE_NATIVE_IDENTITIES_ONE_CUSTOMER = "multiple_native_identities_one_customer"


@dataclass(frozen=True)
class NativeCustomerObservation:
    company_id: UUID
    branch_id: UUID
    provider: str
    native_customer_id: str | None
    source_artifact_sha256: str
    source_record_sha256: str
    claimed_customer_id: UUID | None = None


@dataclass(frozen=True)
class EnterpriseCustomerIdentityCandidate:
    company_id: UUID
    branch_id: UUID
    customer_source_identity_id: UUID
    customer_id: UUID
    source_customer_id_sha256: str


@dataclass(frozen=True)
class NativeCustomerConsolidationResult:
    source_identity_key: str
    source_customer_id_sha256: str | None
    outcome: NativeCustomerConsolidationOutcome
    customer_source_identity_id: UUID | None
    customer_id: UUID | None
    observation_count: int
    input_digest: str
    evidence_digest: str


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def consolidate_native_customers(
    observations: tuple[NativeCustomerObservation, ...],
    candidates: tuple[EnterpriseCustomerIdentityCandidate, ...],
) -> tuple[NativeCustomerConsolidationResult, ...]:
    """Resolve exact scoped identities and fail closed on every conflicting cardinality."""
    groups: dict[str, list[tuple[NativeCustomerObservation, str | None]]] = defaultdict(
        list
    )
    for observation in observations:
        native_hash = (
            scoped_identity(
                observation.provider, "customer", observation.native_customer_id
            )
            if observation.native_customer_id and observation.native_customer_id.strip()
            else None
        )
        key = native_hash or _digest(
            [
                "missing",
                observation.provider.lower(),
                observation.source_artifact_sha256,
                observation.source_record_sha256,
            ]
        )
        groups[key].append((observation, native_hash))

    ordered_candidates = tuple(
        sorted(
            candidates,
            key=lambda item: (item.source_customer_id_sha256, str(item.customer_id)),
        )
    )
    results: list[NativeCustomerConsolidationResult] = []
    for key in sorted(groups):
        members = tuple(
            sorted(groups[key], key=lambda item: item[0].source_record_sha256)
        )
        native_hash = members[0][1]
        input_digest = _digest(
            [CONSOLIDATION_CONTRACT_VERSION, members, ordered_candidates]
        )
        outcome = NativeCustomerConsolidationOutcome.UNRESOLVED
        target: EnterpriseCustomerIdentityCandidate | None = None
        claimed = {
            item.claimed_customer_id for item, _ in members if item.claimed_customer_id
        }
        record_digests = [item.source_record_sha256 for item, _ in members]
        if native_hash is None:
            outcome = NativeCustomerConsolidationOutcome.MISSING_SOURCE_IDENTIFIER
        elif len(claimed) > 1:
            outcome = NativeCustomerConsolidationOutcome.CONFLICTING_SOURCE_EVIDENCE
        elif len(record_digests) != len(set(record_digests)):
            outcome = NativeCustomerConsolidationOutcome.DUPLICATE_SOURCE_EVIDENCE
        else:
            matches = tuple(
                item
                for item in ordered_candidates
                if item.source_customer_id_sha256 == native_hash
            )
            scoped = tuple(
                item
                for item in matches
                if item.company_id == members[0][0].company_id
                and item.branch_id == members[0][0].branch_id
            )
            if matches and len(scoped) != len(matches):
                outcome = (
                    NativeCustomerConsolidationOutcome.COMPANY_BRANCH_SCOPE_CONFLICT
                )
            elif len(scoped) > 1:
                outcome = NativeCustomerConsolidationOutcome.AMBIGUOUS_TARGET
            elif len(scoped) == 1:
                candidate = scoped[0]
                if claimed and candidate.customer_id not in claimed:
                    outcome = (
                        NativeCustomerConsolidationOutcome.EXISTING_BINDING_CONFLICT
                    )
                else:
                    outcome = NativeCustomerConsolidationOutcome.RESOLVED
                    target = candidate
        evidence_digest = _digest(
            [
                CONSOLIDATION_CONTRACT_VERSION,
                key,
                outcome.value,
                target.customer_source_identity_id if target else None,
                target.customer_id if target else None,
                len(members),
                input_digest,
            ]
        )
        results.append(
            NativeCustomerConsolidationResult(
                key,
                native_hash,
                outcome,
                target.customer_source_identity_id if target else None,
                target.customer_id if target else None,
                len(members),
                input_digest,
                evidence_digest,
            )
        )

    resolved_by_customer: dict[UUID, list[int]] = defaultdict(list)
    for index, result in enumerate(results):
        if (
            result.outcome is NativeCustomerConsolidationOutcome.RESOLVED
            and result.customer_id
        ):
            resolved_by_customer[result.customer_id].append(index)
    for indexes in resolved_by_customer.values():
        if len(indexes) > 1:
            for index in indexes:
                prior = results[index]
                outcome = NativeCustomerConsolidationOutcome.MULTIPLE_NATIVE_IDENTITIES_ONE_CUSTOMER
                results[index] = replace(
                    prior,
                    outcome=outcome,
                    customer_source_identity_id=None,
                    customer_id=None,
                    evidence_digest=_digest(
                        [
                            CONSOLIDATION_CONTRACT_VERSION,
                            prior.source_identity_key,
                            outcome.value,
                            None,
                            None,
                            prior.observation_count,
                            prior.input_digest,
                        ]
                    ),
                )
    return tuple(results)
