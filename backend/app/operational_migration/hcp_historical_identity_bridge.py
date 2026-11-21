"""Deterministic opaque-HCP-to-canonical Customer and Location bridge.

HCP changed provider identity domains between the retained legacy import and the
current read-only packet.  This planner never treats a name by itself as identity.
It requires either admitted successor lineage or at least two independent exact
evidence dimensions, and it fails closed when those dimensions disagree.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Final

CONTRACT: Final = "hcp-historical-identity-bridge/v1"


class BridgeDisposition(StrEnum):
    EXACT_LINEAGE = "EXACT_LINEAGE"
    CORROBORATED_EXACT = "CORROBORATED_EXACT"
    ALREADY_BOUND = "ALREADY_BOUND"
    AMBIGUOUS = "AMBIGUOUS"
    QUARANTINED = "QUARANTINED"


@dataclass(frozen=True, slots=True)
class AddressEvidence:
    source_location_id: str
    line1: str
    line2: str | None
    city: str
    state: str
    postal_code: str


@dataclass(frozen=True, slots=True)
class SourceCustomerEvidence:
    source_customer_id: str
    display_name: str
    email: str | None
    phones: tuple[str, ...]
    locations: tuple[AddressEvidence, ...]
    successor_native_id: str | None = None


@dataclass(frozen=True, slots=True)
class CanonicalLocationEvidence:
    native_location_id: str
    address: AddressEvidence
    existing_source_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CanonicalCustomerEvidence:
    native_customer_id: str
    display_name: str
    email: str | None
    phones: tuple[str, ...]
    locations: tuple[CanonicalLocationEvidence, ...]
    existing_source_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LocationBridgeDecision:
    source_location_id: str
    native_location_id: str | None
    disposition: BridgeDisposition
    reason: str


@dataclass(frozen=True, slots=True)
class CustomerBridgeDecision:
    source_customer_id: str
    native_customer_id: str | None
    disposition: BridgeDisposition
    evidence_dimensions: tuple[str, ...]
    candidate_native_ids: tuple[str, ...]
    locations: tuple[LocationBridgeDecision, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class HistoricalIdentityBridgePlan:
    contract: str
    source_count: int
    bridged: int
    quarantined: int
    ambiguous: int
    duplicates_prevented: int
    unexplained: int
    decisions: tuple[CustomerBridgeDecision, ...]
    digest: str

    def verify(self) -> None:
        payload = asdict(self)
        observed = payload.pop("digest")
        if self.contract != CONTRACT or observed != _digest(payload):
            raise ValueError("historical identity bridge digest mismatch")
        dispositions = Counter(row.disposition for row in self.decisions)
        bridged = sum(
            dispositions[item]
            for item in (
                BridgeDisposition.EXACT_LINEAGE,
                BridgeDisposition.CORROBORATED_EXACT,
                BridgeDisposition.ALREADY_BOUND,
            )
        )
        if (
            self.source_count != len(self.decisions)
            or self.bridged != bridged
            or self.quarantined != dispositions[BridgeDisposition.QUARANTINED]
            or self.ambiguous != dispositions[BridgeDisposition.AMBIGUOUS]
            or self.unexplained != 0
        ):
            raise ValueError("historical identity bridge counts are inconsistent")


def build_historical_identity_bridge(
    *,
    source: tuple[SourceCustomerEvidence, ...],
    canonical: tuple[CanonicalCustomerEvidence, ...],
) -> HistoricalIdentityBridgePlan:
    """Classify every source Customer and its Locations without fuzzy matching."""
    source_ids = [row.source_customer_id for row in source]
    native_ids = [row.native_customer_id for row in canonical]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("source Customer identities must be unique")
    if len(native_ids) != len(set(native_ids)):
        raise ValueError("canonical Customer identities must be unique")

    by_native = {row.native_customer_id: row for row in canonical}
    existing: dict[str, list[CanonicalCustomerEvidence]] = defaultdict(list)
    indexes: dict[str, dict[str, list[CanonicalCustomerEvidence]]] = {
        name: defaultdict(list) for name in ("name", "email", "phone", "address")
    }
    for row in canonical:
        for source_id in row.existing_source_ids:
            existing[source_id].append(row)
        indexes["name"][_text(row.display_name)].append(row)
        if email := _email(row.email):
            indexes["email"][email].append(row)
        for phone in {_phone(value) for value in row.phones} - {""}:
            indexes["phone"][phone].append(row)
        for location in row.locations:
            indexes["address"][_address(location.address)].append(row)

    decisions: list[CustomerBridgeDecision] = []
    claimed_targets: dict[str, str] = {}
    duplicates_prevented = 0
    for source_row in sorted(source, key=lambda value: value.source_customer_id):
        decision = _classify_customer(source_row, by_native, existing, indexes)
        native_customer_id = decision.native_customer_id
        if native_customer_id:
            prior = claimed_targets.get(native_customer_id)
            if prior and prior != source_row.source_customer_id:
                duplicates_prevented += 1
                decision = CustomerBridgeDecision(
                    source_customer_id=source_row.source_customer_id,
                    native_customer_id=None,
                    disposition=BridgeDisposition.AMBIGUOUS,
                    evidence_dimensions=decision.evidence_dimensions,
                    candidate_native_ids=(native_customer_id,),
                    locations=(),
                    reason="multiple opaque source Customers claim one canonical Customer",
                )
            else:
                claimed_targets[native_customer_id] = source_row.source_customer_id
        decisions.append(decision)

    counts = Counter(row.disposition for row in decisions)
    bridged = sum(
        counts[item]
        for item in (
            BridgeDisposition.EXACT_LINEAGE,
            BridgeDisposition.CORROBORATED_EXACT,
            BridgeDisposition.ALREADY_BOUND,
        )
    )
    payload = {
        "contract": CONTRACT,
        "source_count": len(source),
        "bridged": bridged,
        "quarantined": counts[BridgeDisposition.QUARANTINED],
        "ambiguous": counts[BridgeDisposition.AMBIGUOUS],
        "duplicates_prevented": duplicates_prevented,
        "unexplained": 0,
        "decisions": tuple(decisions),
    }
    result = HistoricalIdentityBridgePlan(
        contract=CONTRACT,
        source_count=len(source),
        bridged=bridged,
        quarantined=counts[BridgeDisposition.QUARANTINED],
        ambiguous=counts[BridgeDisposition.AMBIGUOUS],
        duplicates_prevented=duplicates_prevented,
        unexplained=0,
        decisions=tuple(decisions),
        digest=_digest(payload),
    )
    result.verify()
    return result


def _classify_customer(
    source: SourceCustomerEvidence,
    by_native: dict[str, CanonicalCustomerEvidence],
    existing: dict[str, list[CanonicalCustomerEvidence]],
    indexes: dict[str, dict[str, list[CanonicalCustomerEvidence]]],
) -> CustomerBridgeDecision:
    already = existing.get(source.source_customer_id, [])
    if len(already) == 1:
        return _bound_decision(
            source, already[0], BridgeDisposition.ALREADY_BOUND, ("source_identity",)
        )
    if len(already) > 1:
        return _ambiguous(source, already, ("source_identity",), "duplicate binding")
    if source.successor_native_id:
        target = by_native.get(source.successor_native_id)
        if target is None:
            return _quarantine(source, "successor lineage target is absent")
        return _bound_decision(
            source, target, BridgeDisposition.EXACT_LINEAGE, ("successor_lineage",)
        )

    evidence: dict[str, set[str]] = defaultdict(set)
    for candidate in indexes["name"].get(_text(source.display_name), []):
        evidence[candidate.native_customer_id].add("name")
    if email := _email(source.email):
        for candidate in indexes["email"].get(email, []):
            evidence[candidate.native_customer_id].add("email")
    for phone in {_phone(value) for value in source.phones} - {""}:
        for candidate in indexes["phone"].get(phone, []):
            evidence[candidate.native_customer_id].add("phone")
    for location in source.locations:
        for candidate in indexes["address"].get(_address(location), []):
            evidence[candidate.native_customer_id].add("address")

    qualified = {
        native_id: dimensions
        for native_id, dimensions in evidence.items()
        if _qualified(dimensions)
    }
    if len(qualified) == 1:
        native_id, matched_dimensions = next(iter(qualified.items()))
        return _bound_decision(
            source,
            by_native[native_id],
            BridgeDisposition.CORROBORATED_EXACT,
            tuple(sorted(matched_dimensions)),
        )
    if qualified:
        candidates = [by_native[native_id] for native_id in sorted(qualified)]
        all_dimensions: tuple[str, ...] = tuple(
            sorted(set().union(*qualified.values()))
        )
        return _ambiguous(
            source, candidates, all_dimensions, "multiple corroborated exact candidates"
        )
    return _quarantine(source, "no candidate has two independent exact dimensions")


def _qualified(dimensions: set[str]) -> bool:
    # A display name is corroboration, never sufficient identity.  Contact and
    # address are independent evidence groups; email/phone together also qualify.
    return (
        len(dimensions) >= 2
        and dimensions != {"name", "address"}
        or "address" in dimensions
        and bool(dimensions & {"email", "phone"})
        or {"email", "phone"}.issubset(dimensions)
    )


def _bound_decision(
    source: SourceCustomerEvidence,
    target: CanonicalCustomerEvidence,
    disposition: BridgeDisposition,
    dimensions: tuple[str, ...],
) -> CustomerBridgeDecision:
    classified = [_classify_location(item, target) for item in source.locations]
    claims = Counter(
        item.native_location_id for item in classified if item.native_location_id
    )
    locations = tuple(
        LocationBridgeDecision(
            item.source_location_id,
            None,
            BridgeDisposition.AMBIGUOUS,
            "multiple retained Locations claim one canonical Location",
        )
        if item.native_location_id and claims[item.native_location_id] > 1
        else item
        for item in classified
    )
    return CustomerBridgeDecision(
        source_customer_id=source.source_customer_id,
        native_customer_id=target.native_customer_id,
        disposition=disposition,
        evidence_dimensions=dimensions,
        candidate_native_ids=(target.native_customer_id,),
        locations=locations,
        reason="unique deterministic Customer successor",
    )


def _classify_location(
    source: AddressEvidence, target: CanonicalCustomerEvidence
) -> LocationBridgeDecision:
    already = [
        row
        for row in target.locations
        if source.source_location_id in row.existing_source_ids
    ]
    if len(already) == 1:
        return LocationBridgeDecision(
            source.source_location_id,
            already[0].native_location_id,
            BridgeDisposition.ALREADY_BOUND,
            "existing exact SOURCE.4 Location binding",
        )
    matches = [
        row for row in target.locations if _address(row.address) == _address(source)
    ]
    if len(matches) == 1:
        if matches[0].existing_source_ids:
            return LocationBridgeDecision(
                source.source_location_id,
                None,
                BridgeDisposition.AMBIGUOUS,
                "canonical Location already has another SOURCE.4 identity",
            )
        return LocationBridgeDecision(
            source.source_location_id,
            matches[0].native_location_id,
            BridgeDisposition.CORROBORATED_EXACT,
            "exact normalized address inside bound Customer",
        )
    return LocationBridgeDecision(
        source.source_location_id,
        None,
        BridgeDisposition.AMBIGUOUS if matches else BridgeDisposition.QUARANTINED,
        "multiple exact Locations inside bound Customer"
        if matches
        else "no exact Location inside bound Customer",
    )


def _ambiguous(
    source: SourceCustomerEvidence,
    candidates: list[CanonicalCustomerEvidence],
    dimensions: tuple[str, ...],
    reason: str,
) -> CustomerBridgeDecision:
    return CustomerBridgeDecision(
        source.source_customer_id,
        None,
        BridgeDisposition.AMBIGUOUS,
        dimensions,
        tuple(sorted(row.native_customer_id for row in candidates)),
        (),
        reason,
    )


def _quarantine(source: SourceCustomerEvidence, reason: str) -> CustomerBridgeDecision:
    return CustomerBridgeDecision(
        source.source_customer_id,
        None,
        BridgeDisposition.QUARANTINED,
        (),
        (),
        (),
        reason,
    )


def _text(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    return " ".join(re.findall(r"[a-z0-9]+", normalized))


def _email(value: str | None) -> str:
    return (value or "").strip().casefold()


def _phone(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    return digits[-10:] if len(digits) >= 10 else digits


def _address(value: AddressEvidence) -> str:
    return "|".join(
        _text(item)
        for item in (
            value.line1,
            value.line2,
            value.city,
            value.state,
            value.postal_code,
        )
    )


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, default=asdict, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
