"""Fail-closed contracts for multi-property Customer location expansion."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.customer_migration.housecall_pro_adapter import (
    ADDRESS_FIELDS,
    REQUIRED_ADDRESS_FIELDS,
    detect_customer_export_contract,
)
from app.customers.normalization import build_normalized_address

LOCATION_EVIDENCE_VERSION = "customer-location-evidence/v1"
LOCATION_IDENTITY_VERSION = "hcp-customer-address-group/v1"
LOCATION_REVIEW_VERSION = "customer-location-owner-review/v1"


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: str | bytes) -> str:
    return hashlib.sha256(
        value.encode() if isinstance(value, str) else value
    ).hexdigest()


class CustomerLocationClassification(StrEnum):
    CONFIRMED_MULTI_PROPERTY_CUSTOMER = "confirmed_multi_property_customer"
    DUPLICATE_LOCATION = "duplicate_location"
    INCOMPLETE_ADDRESS = "incomplete_address"
    AMBIGUOUS_CUSTOMER = "ambiguous_customer"
    AMBIGUOUS_SERVICE_LOCATION = "ambiguous_service_location"
    RESIDENTIAL_ANOMALY = "residential_anomaly"
    COMMERCIAL_PROPERTY_MANAGER = "commercial_property_manager"
    EXISTING_MIGRATED_LOCATION = "existing_migrated_location"
    NEWLY_DISCOVERABLE_LOCATION = "newly_discoverable_location"
    UNSUPPORTED_SOURCE_EVIDENCE = "unsupported_source_evidence"


class LocationOwnerDisposition(StrEnum):
    APPROVE_LOCATION = "approve_location"
    REJECT_LOCATION = "reject_location"
    DUPLICATE_LOCATION = "duplicate_location"
    DEFER = "defer"
    CORRECTION = "correction"
    UNRELATED_CUSTOMER = "unrelated_customer"


@dataclass(frozen=True)
class SourceLocationEvidence:
    source_customer_id_sha256: str
    address_group_number: int
    source_group_sha256: str
    derived_identity: str
    native_source_location_id: str | None
    prior_source_group_sha256: str | None

    @property
    def executable(self) -> bool:
        return self.native_source_location_id is not None


@dataclass(frozen=True)
class LocationReviewSubject:
    customer_classification: CustomerLocationClassification
    source_customer_id_sha256: str
    locations: tuple[SourceLocationEvidence, ...]
    classifications: tuple[CustomerLocationClassification, ...]
    recommended_disposition: LocationOwnerDisposition
    evidence_sha256: str


@dataclass(frozen=True)
class LocationExpansionReadiness:
    evidence_version: str
    source_sha256: str
    schema_version: str
    schema_fingerprint: str
    source_rows: int
    accepted_customer_rows: int
    multi_property_customers: int
    complete_service_locations: int
    classification_totals: dict[str, int]
    subjects: tuple[LocationReviewSubject, ...]
    execution_gate: str
    evidence_sha256: str


def _rows(source: bytes) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(source.decode("utf-8-sig"), newline=""))
    headers = list(reader.fieldnames or ())
    return headers, [{key: value or "" for key, value in row.items()} for row in reader]


def _groups(row: Mapping[str, str]) -> tuple[tuple[int, dict[str, str]], ...]:
    values: list[tuple[int, dict[str, str]]] = []
    for number in range(1, 62):
        group = {
            field: row.get(f"Address_{number} {field}", "").strip()
            for field in ADDRESS_FIELDS
        }
        if any(group.values()):
            values.append((number, group))
    return tuple(values)


def _complete(group: Mapping[str, str]) -> bool:
    return all(group[field] for field in REQUIRED_ADDRESS_FIELDS)


def _billing(group: Mapping[str, str]) -> bool:
    return group["Billing?"].lower() == "true"


def _normalized_address(group: Mapping[str, str]) -> str:
    return build_normalized_address(
        group["Street Line 1"],
        group["Street Line 2"] or None,
        group["City"],
        group["State"],
        group["Postal Code"],
    )


def _group_history(source: bytes | None) -> dict[tuple[str, int], str]:
    if source is None:
        return {}
    headers, rows = _rows(source)
    if detect_customer_export_contract(headers) is None:
        raise ValueError("prior Customer export schema is unregistered")
    history: dict[tuple[str, int], str] = {}
    for row in rows:
        customer_id = row.get("ID", "").strip()
        if not customer_id:
            continue
        for number, group in _groups(row):
            history[(customer_id, number)] = _sha256(_canonical(group))
    return history


def classify_location_expansion(
    *,
    source: bytes,
    prior_source: bytes | None,
    imported_customer_ids: Sequence[str],
    ambiguous_customer_id_sha256: Sequence[str] = (),
) -> LocationExpansionReadiness:
    """Classify exact address-group evidence without name or fuzzy matching."""
    headers, rows = _rows(source)
    contract = detect_customer_export_contract(headers)
    if contract is None:
        raise ValueError("Customer location expansion requires a registered schema")
    prior = _group_history(prior_source)
    imported = set(imported_customer_ids)
    ambiguous = set(ambiguous_customer_id_sha256)
    counts: Counter[str] = Counter()
    subjects: list[LocationReviewSubject] = []
    accepted = 0
    complete_locations = 0
    multi_property_customers = 0
    for row in rows:
        customer_id = row.get("ID", "").strip()
        customer_hash = _sha256(customer_id) if customer_id else ""
        customer_type = row.get("Customer Type", "").strip().lower()
        groups = _groups(row)
        service_groups = tuple(
            (number, group)
            for number, group in groups
            if not _billing(group) and _complete(group)
        )
        incomplete = tuple(
            (number, group)
            for number, group in groups
            if not _billing(group) and not _complete(group)
        )
        contact_values = tuple(
            row.get(field, "").strip()
            for field in (
                "First Name",
                "Last Name",
                "Email",
                "Mobile Number",
                "Home Number",
                "Work Number",
                "Role",
            )
        )
        unresolved_contact = any(contact_values) and not all(contact_values[:2])
        if (
            not customer_id
            or customer_type not in {"business", "homeowner"}
            or unresolved_contact
        ):
            continue
        accepted += 1
        complete_locations += len(service_groups)
        if len(service_groups) <= 1 and not incomplete:
            continue
        locations: list[SourceLocationEvidence] = []
        facets: set[CustomerLocationClassification] = set()
        address_counts = Counter(
            _normalized_address(group) for _, group in service_groups
        )
        if incomplete:
            facets.add(CustomerLocationClassification.INCOMPLETE_ADDRESS)
            counts[CustomerLocationClassification.INCOMPLETE_ADDRESS.value] += len(
                incomplete
            )
        if customer_hash in ambiguous:
            facets.add(CustomerLocationClassification.AMBIGUOUS_CUSTOMER)
            counts[CustomerLocationClassification.AMBIGUOUS_CUSTOMER.value] += 1
        if customer_type == "business":
            facets.add(CustomerLocationClassification.COMMERCIAL_PROPERTY_MANAGER)
            counts[
                CustomerLocationClassification.COMMERCIAL_PROPERTY_MANAGER.value
            ] += 1
        else:
            facets.add(CustomerLocationClassification.RESIDENTIAL_ANOMALY)
            counts[CustomerLocationClassification.RESIDENTIAL_ANOMALY.value] += 1
        for number, group in service_groups:
            group_sha = _sha256(_canonical(group))
            previous = prior.get((customer_id, number))
            identity = _sha256(
                _canonical(
                    {
                        "identity_version": LOCATION_IDENTITY_VERSION,
                        "source_customer_id": customer_id,
                        "address_group_number": number,
                    }
                )
            )
            locations.append(
                SourceLocationEvidence(
                    source_customer_id_sha256=customer_hash,
                    address_group_number=number,
                    source_group_sha256=group_sha,
                    derived_identity=identity,
                    native_source_location_id=None,
                    prior_source_group_sha256=previous,
                )
            )
            if address_counts[_normalized_address(group)] > 1:
                facets.add(CustomerLocationClassification.DUPLICATE_LOCATION)
                counts[CustomerLocationClassification.DUPLICATE_LOCATION.value] += 1
            if previous is not None and previous != group_sha:
                facets.add(CustomerLocationClassification.AMBIGUOUS_SERVICE_LOCATION)
                counts[
                    CustomerLocationClassification.AMBIGUOUS_SERVICE_LOCATION.value
                ] += 1
            facet = (
                CustomerLocationClassification.EXISTING_MIGRATED_LOCATION
                if customer_id in imported and number == service_groups[0][0]
                else CustomerLocationClassification.NEWLY_DISCOVERABLE_LOCATION
            )
            facets.add(facet)
            counts[facet.value] += 1
            counts[
                CustomerLocationClassification.UNSUPPORTED_SOURCE_EVIDENCE.value
            ] += 1
        if len(service_groups) > 1:
            multi_property_customers += 1
            if (
                customer_type == "business"
                and customer_hash not in ambiguous
                and not incomplete
            ):
                counts[
                    CustomerLocationClassification.CONFIRMED_MULTI_PROPERTY_CUSTOMER.value
                ] += 1
        primary = (
            CustomerLocationClassification.AMBIGUOUS_CUSTOMER
            if CustomerLocationClassification.AMBIGUOUS_CUSTOMER in facets
            else CustomerLocationClassification.INCOMPLETE_ADDRESS
            if CustomerLocationClassification.INCOMPLETE_ADDRESS in facets
            else CustomerLocationClassification.RESIDENTIAL_ANOMALY
            if CustomerLocationClassification.RESIDENTIAL_ANOMALY in facets
            else CustomerLocationClassification.CONFIRMED_MULTI_PROPERTY_CUSTOMER
        )
        recommended = (
            LocationOwnerDisposition.CORRECTION
            if CustomerLocationClassification.INCOMPLETE_ADDRESS in facets
            else LocationOwnerDisposition.DEFER
        )
        evidence_payload = {
            "review_version": LOCATION_REVIEW_VERSION,
            "source_customer_id_sha256": customer_hash,
            "locations": [location.__dict__ for location in locations],
            "classifications": sorted(item.value for item in facets),
            "recommended_disposition": recommended.value,
        }
        subjects.append(
            LocationReviewSubject(
                customer_classification=primary,
                source_customer_id_sha256=customer_hash,
                locations=tuple(locations),
                classifications=tuple(sorted(facets, key=lambda item: item.value)),
                recommended_disposition=recommended,
                evidence_sha256=_sha256(_canonical(evidence_payload)),
            )
        )
    for classification in CustomerLocationClassification:
        counts.setdefault(classification.value, 0)
    payload = {
        "evidence_version": LOCATION_EVIDENCE_VERSION,
        "source_sha256": _sha256(source),
        "schema_version": contract.version,
        "schema_fingerprint": _sha256(_canonical(headers)),
        "source_rows": len(rows),
        "accepted_customer_rows": accepted,
        "multi_property_customers": multi_property_customers,
        "complete_service_locations": complete_locations,
        "classification_totals": dict(sorted(counts.items())),
        "subjects": [subject.__dict__ for subject in subjects],
        "execution_gate": "BLOCKED — NATIVE SERVICE LOCATION ID REQUIRED",
    }
    return LocationExpansionReadiness(
        evidence_version=LOCATION_EVIDENCE_VERSION,
        source_sha256=_sha256(source),
        schema_version=contract.version,
        schema_fingerprint=_sha256(_canonical(headers)),
        source_rows=len(rows),
        accepted_customer_rows=accepted,
        multi_property_customers=multi_property_customers,
        complete_service_locations=complete_locations,
        classification_totals=dict(sorted(counts.items())),
        subjects=tuple(subjects),
        execution_gate="BLOCKED — NATIVE SERVICE LOCATION ID REQUIRED",
        evidence_sha256=_sha256(_canonical(payload)),
    )


def validate_owner_disposition(
    subject: LocationReviewSubject, disposition: LocationOwnerDisposition
) -> None:
    if disposition is LocationOwnerDisposition.APPROVE_LOCATION and any(
        not location.executable for location in subject.locations
    ):
        raise ValueError("approval requires a native stable Service Location identity")


def exact_job_unlock_counts(
    *, exact_multi_property_address_matches: int, nonmatching_addresses: int
) -> dict[str, int]:
    if exact_multi_property_address_matches < 0 or nonmatching_addresses < 0:
        raise ValueError("Job reconciliation counts must be nonnegative")
    return {
        "potentially_unlocked_after_approved_location_import": exact_multi_property_address_matches,
        "owner_review_required": nonmatching_addresses,
        "currently_unlocked": 0,
    }
