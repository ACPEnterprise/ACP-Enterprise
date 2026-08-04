"""Provider-neutral acquisition and reconciliation of native location identity."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum

IDENTITY_CONTRACT_VERSION = "native-service-location-identity/v1"


class LocationIdentityClassification(StrEnum):
    ACQUIRED = "acquired"
    MISSING_SOURCE_IDENTIFIER = "missing_source_location_identifier"
    DUPLICATE_SOURCE_IDENTIFIER = "duplicate_source_identifier"
    SOURCE_IDENTIFIER_MULTIPLE_LOCATIONS = (
        "source_identifier_multiple_candidate_locations"
    )
    ADDRESS_MULTIPLE_SOURCE_IDENTIFIERS = (
        "normalized_address_multiple_source_identifiers"
    )
    SOURCE_CUSTOMER_MISMATCH = "source_customer_mismatch"
    MISSING_PARENT_CUSTOMER = "missing_parent_customer"
    INCOMPLETE_ADDRESS = "incomplete_address"
    EXISTING_ACP_IDENTITY_CONFLICT = "existing_acp_identity_conflict"
    PREVIOUSLY_IMPORTED_IDENTITY_MISMATCH = "previously_imported_identity_mismatch"
    RECONCILIATION_REQUIRED = "reconciliation_required"


@dataclass(frozen=True)
class NativeLocationObservation:
    provider: str
    native_location_id: str | None
    native_customer_id: str | None
    source_artifact_sha256: str
    source_record_sha256: str
    normalized_address_sha256: str | None
    address_complete: bool
    candidate_location_keys: tuple[str, ...] = ()
    authoritative_parent_customer_sha256: str | None = None
    existing_acp_identity_conflict: bool = False
    reconciliation_required: bool = False


@dataclass(frozen=True)
class AcceptedLocationIdentity:
    source_location_id_sha256: str
    source_customer_id_sha256: str
    acp_service_location_id: str


@dataclass(frozen=True)
class LocationIdentityResult:
    observation_sha256: str
    source_location_id_sha256: str | None
    source_customer_id_sha256: str | None
    classification: LocationIdentityClassification
    readiness: str
    evidence_digest: str


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def scoped_identity(provider: str, entity_type: str, native_id: str) -> str:
    """Hash an identifier with provider and entity scope; never persist its raw form."""
    return _digest([provider.strip().lower(), entity_type, native_id.strip()])


def reconcile_native_locations(
    observations: tuple[NativeLocationObservation, ...],
    *,
    known_customer_hashes: frozenset[str] = frozenset(),
    accepted_identities: tuple[AcceptedLocationIdentity, ...] = (),
) -> tuple[LocationIdentityResult, ...]:
    """Return stable, fail-closed results without address-based identity merging."""
    prepared = []
    for item in observations:
        location_hash = (
            scoped_identity(item.provider, "service_location", item.native_location_id)
            if item.native_location_id and item.native_location_id.strip()
            else None
        )
        customer_hash = (
            scoped_identity(item.provider, "customer", item.native_customer_id)
            if item.native_customer_id and item.native_customer_id.strip()
            else None
        )
        observation_hash = _digest(
            [
                IDENTITY_CONTRACT_VERSION,
                item.provider.lower(),
                item.source_artifact_sha256,
                item.source_record_sha256,
            ]
        )
        prepared.append((item, observation_hash, location_hash, customer_hash))

    location_counts: dict[str, int] = {}
    location_candidates: dict[str, set[str]] = {}
    address_locations: dict[str, set[str]] = {}
    for item, _, location_hash, _ in prepared:
        if location_hash:
            location_counts[location_hash] = location_counts.get(location_hash, 0) + 1
            location_candidates.setdefault(location_hash, set()).update(
                item.candidate_location_keys
            )
            if item.normalized_address_sha256:
                address_locations.setdefault(item.normalized_address_sha256, set()).add(
                    location_hash
                )
    accepted = {item.source_location_id_sha256: item for item in accepted_identities}

    results = []
    for item, observation_hash, location_hash, customer_hash in prepared:
        classification = LocationIdentityClassification.ACQUIRED
        if location_hash is None:
            classification = LocationIdentityClassification.MISSING_SOURCE_IDENTIFIER
        elif customer_hash is None or customer_hash not in known_customer_hashes:
            classification = LocationIdentityClassification.MISSING_PARENT_CUSTOMER
        elif (
            item.authoritative_parent_customer_sha256 is not None
            and item.authoritative_parent_customer_sha256 != customer_hash
        ):
            classification = LocationIdentityClassification.SOURCE_CUSTOMER_MISMATCH
        elif item.existing_acp_identity_conflict:
            classification = (
                LocationIdentityClassification.EXISTING_ACP_IDENTITY_CONFLICT
            )
        elif not item.address_complete:
            classification = LocationIdentityClassification.INCOMPLETE_ADDRESS
        elif len(location_candidates.get(location_hash, set())) > 1:
            classification = (
                LocationIdentityClassification.SOURCE_IDENTIFIER_MULTIPLE_LOCATIONS
            )
        elif location_counts.get(location_hash, 0) > 1:
            classification = LocationIdentityClassification.DUPLICATE_SOURCE_IDENTIFIER
        elif (
            item.normalized_address_sha256
            and len(address_locations[item.normalized_address_sha256]) > 1
        ):
            classification = (
                LocationIdentityClassification.ADDRESS_MULTIPLE_SOURCE_IDENTIFIERS
            )
        elif (
            location_hash in accepted
            and accepted[location_hash].source_customer_id_sha256 != customer_hash
        ):
            classification = (
                LocationIdentityClassification.PREVIOUSLY_IMPORTED_IDENTITY_MISMATCH
            )
        elif item.reconciliation_required:
            classification = LocationIdentityClassification.RECONCILIATION_REQUIRED
        readiness = (
            "ready"
            if classification is LocationIdentityClassification.ACQUIRED
            else "reconciliation_required"
        )
        digest = _digest(
            [
                IDENTITY_CONTRACT_VERSION,
                observation_hash,
                location_hash,
                customer_hash,
                classification.value,
                readiness,
            ]
        )
        results.append(
            LocationIdentityResult(
                observation_hash,
                location_hash,
                customer_hash,
                classification,
                readiness,
                digest,
            )
        )
    return tuple(sorted(results, key=lambda result: result.observation_sha256))


def preserve_pilot_boundary(before: tuple[str, ...], after: tuple[str, ...]) -> None:
    if before != after:
        raise ValueError("immutable pilot boundary changed")
