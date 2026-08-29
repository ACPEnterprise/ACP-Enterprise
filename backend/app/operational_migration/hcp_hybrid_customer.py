"""Source-faithful hybrid Customer admission for the sealed HCP.SOURCE.4 package."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from enum import StrEnum
from typing import Any, cast

from app.customer_migration.adapter_import import (
    BOUNDARY_VERSION,
    REVIEW_VERSION,
    ApprovedCustomerImportBoundary,
    ExpectedCustomerImportCounts,
    ReviewedCustomerAdapterOutput,
    ReviewedCustomerAggregate,
)
from app.customer_migration.adapter_import_policy import customer_adapter_import_policy
from app.customers.schemas import (
    ContactCreate,
    CustomerCreate,
    CustomerStatus,
    CustomerType,
    ServiceLocationCreate,
)

CUSTOMER_CONTRACT_VERSION = "hcp-source4-customer-api/v1"
DETAIL_CONTRACT_VERSION = "hcp-source4-customer-referenced-detail/v1"
HYBRID_ADMISSION_VERSION = "hcp-source4-hybrid-customer-admission/v1"
PARENT_CLOSURE_VERSION = "hcp-source4-job-customer-parent-closure/v1"

CUSTOMER_KEYS = frozenset(
    {
        "addresses",
        "company",
        "company_id",
        "company_name",
        "created_at",
        "email",
        "first_name",
        "home_number",
        "id",
        "kind",
        "last_name",
        "lead_source",
        "mobile_number",
        "notes",
        "notifications_enabled",
        "tags",
        "updated_at",
        "work_number",
    }
)
ADDRESS_KEYS = frozenset(
    {
        "city",
        "country",
        "id",
        "latitude",
        "longitude",
        "state",
        "street",
        "street_line_2",
        "type",
        "zip",
    }
)


def canonical_sha256(value: object) -> str:
    def normalize(item: object) -> object:
        if is_dataclass(item) and not isinstance(item, type):
            return normalize(asdict(cast(Any, item)))
        if isinstance(item, Mapping):
            return {str(key): normalize(child) for key, child in item.items()}
        if isinstance(item, (tuple, list)):
            return [normalize(child) for child in item]
        if isinstance(item, StrEnum):
            return item.value
        return item

    return hashlib.sha256(
        json.dumps(normalize(value), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class AssertionKind(StrEnum):
    API_LISTED = "API_LISTED"
    REFERENCED_DETAIL = "REFERENCED_DETAIL"
    CONTROL_EXPORT = "CONTROL_EXPORT"


class AdmissionOutcome(StrEnum):
    PERSISTABLE = "PERSISTABLE"
    EXPLICIT_EXCEPTION = "EXPLICIT_EXCEPTION"
    REJECTED = "REJECTED"
    INTENTIONALLY_NON_APPLICABLE = "INTENTIONALLY_NON_APPLICABLE"


class ParentOutcome(StrEnum):
    RESOLVED_TO_PERSISTABLE_CUSTOMER = "RESOLVED_TO_PERSISTABLE_CUSTOMER"
    RESOLVED_TO_EXPLICIT_EXCEPTION = "RESOLVED_TO_EXPLICIT_EXCEPTION"
    RESOLVED_TO_REJECTED_CUSTOMER = "RESOLVED_TO_REJECTED_CUSTOMER"
    MISSING_AUTHORITATIVE_CUSTOMER_EVIDENCE = "MISSING_AUTHORITATIVE_CUSTOMER_EVIDENCE"


@dataclass(frozen=True)
class CustomerAssertion:
    kind: AssertionKind
    source_identity: str
    payload: Mapping[str, Any]
    payload_digest: str
    container_digest: str

    @classmethod
    def source4(
        cls,
        *,
        kind: AssertionKind,
        payload: Mapping[str, Any],
        container_digest: str,
    ) -> CustomerAssertion:
        if kind not in {AssertionKind.API_LISTED, AssertionKind.REFERENCED_DETAIL}:
            raise ValueError("SOURCE.4 Customer assertion kind is invalid")
        if frozenset(payload) != CUSTOMER_KEYS:
            raise ValueError("unsupported SOURCE.4 Customer layout")
        native_id = payload.get("id")
        if not isinstance(native_id, str) or not native_id.startswith("cus_"):
            raise ValueError("authoritative HCP Customer native identity is required")
        addresses = payload.get("addresses")
        if not isinstance(addresses, list):
            raise TypeError("SOURCE.4 Customer addresses must be an acquired list")
        for address in addresses:
            if not isinstance(address, Mapping) or frozenset(address) != ADDRESS_KEYS:
                raise ValueError("unsupported SOURCE.4 Customer address layout")
        return cls(
            kind=kind,
            source_identity=native_id,
            payload=dict(payload),
            payload_digest=canonical_sha256(payload),
            container_digest=container_digest,
        )


@dataclass(frozen=True)
class ControlAssertion:
    """An independent control assertion; it is not an API identity crosswalk."""

    control_identity: str
    payload_digest: str
    disposition: str
    reason: str | None = None


@dataclass(frozen=True)
class HybridCustomerCandidate:
    native_customer_id: str
    membership: str
    outcome: AdmissionOutcome
    api_digest: str | None
    detail_digest: str | None
    control_digests: tuple[str, ...]
    conflict_fields: tuple[str, ...]
    contact_present: bool
    location_ids: tuple[str, ...]
    location_exception_ids: tuple[str, ...]
    reason: str | None
    acquired_payload: Mapping[str, Any]

    def lineage_context(
        self, package_digest: str, admission_digest: str
    ) -> dict[str, object]:
        return {
            "hybrid_admission_version": HYBRID_ADMISSION_VERSION,
            "hybrid_admission_digest": admission_digest,
            "source4_package_digest": package_digest,
            "api_assertion_digest": self.api_digest,
            "referenced_detail_assertion_digest": self.detail_digest,
            "control_assertion_digests": self.control_digests,
            "conflict_fields": self.conflict_fields,
            "membership": self.membership,
            "admission_outcome": self.outcome,
        }


@dataclass(frozen=True)
class HybridCustomerAdmission:
    version: str
    candidates: tuple[HybridCustomerCandidate, ...]
    unlinked_control_assertions: tuple[ControlAssertion, ...]
    digest: str

    @property
    def counts(self) -> dict[str, int]:
        values = {outcome.value: 0 for outcome in AdmissionOutcome}
        for item in self.candidates:
            values[item.outcome.value] += 1
        values["AUTHORITATIVE_UNION"] = len(self.candidates)
        values["UNLINKED_CONTROL_ASSERTIONS"] = len(self.unlinked_control_assertions)
        return values

    def validate(self) -> None:
        if self.version != HYBRID_ADMISSION_VERSION:
            raise ValueError("unsupported hybrid Customer admission version")
        identities = [item.native_customer_id for item in self.candidates]
        if identities != sorted(identities) or len(identities) != len(set(identities)):
            raise ValueError("hybrid Customer identities are not canonical and unique")
        if len(self.candidates) != sum(
            self.counts[outcome.value] for outcome in AdmissionOutcome
        ):
            raise ValueError("hybrid Customer reconciliation does not balance")
        if self.digest != _admission_digest(
            self.candidates, self.unlinked_control_assertions
        ):
            raise ValueError("hybrid Customer admission digest mismatch")


def _admission_digest(
    candidates: tuple[HybridCustomerCandidate, ...],
    controls: tuple[ControlAssertion, ...],
) -> str:
    return canonical_sha256(
        {
            "version": HYBRID_ADMISSION_VERSION,
            "candidates": candidates,
            "unlinked_control_assertions": controls,
        }
    )


def build_hybrid_admission(
    *,
    api_assertions: Iterable[CustomerAssertion],
    detail_assertions: Iterable[CustomerAssertion],
    control_assertions: Iterable[ControlAssertion] = (),
    authoritative_control_links: Mapping[str, str] | None = None,
) -> HybridCustomerAdmission:
    links = dict(authoritative_control_links or {})
    api = _unique_assertions(api_assertions, AssertionKind.API_LISTED)
    detail = _unique_assertions(detail_assertions, AssertionKind.REFERENCED_DETAIL)
    controls = tuple(sorted(control_assertions, key=lambda item: item.control_identity))
    control_by_id = {item.control_identity: item for item in controls}
    if len(control_by_id) != len(controls):
        raise ValueError("contradictory control identity")
    linked: dict[str, list[ControlAssertion]] = {}
    for control_id, native_id in links.items():
        if control_id not in control_by_id or native_id not in api | detail:
            raise ValueError("authoritative control link references unknown evidence")
        linked.setdefault(native_id, []).append(control_by_id[control_id])
    candidates: list[HybridCustomerCandidate] = []
    for native_id in sorted(api.keys() | detail.keys()):
        api_item, detail_item = api.get(native_id), detail.get(native_id)
        assertions = [item for item in (api_item, detail_item) if item]
        payload = assertions[0].payload
        conflict_fields: tuple[str, ...] = ()
        if (
            len(assertions) == 2
            and assertions[0].payload_digest != assertions[1].payload_digest
        ):
            conflict_fields = tuple(
                sorted(
                    k
                    for k in CUSTOMER_KEYS
                    if assertions[0].payload.get(k) != assertions[1].payload.get(k)
                )
            )
        has_name = any(
            isinstance(payload.get(key), str) and payload[key].strip()
            for key in ("company_name", "first_name", "last_name")
        )
        outcome = (
            AdmissionOutcome.PERSISTABLE
            if has_name
            else AdmissionOutcome.EXPLICIT_EXCEPTION
        )
        reason = None if has_name else "customer_display_identity_missing"
        complete: list[str] = []
        incomplete: list[str] = []
        for address in payload["addresses"]:
            address_id = address.get("id")
            authoritative = isinstance(address_id, str) and address_id.startswith(
                "adr_"
            )
            sufficient = authoritative and all(
                isinstance(address.get(k), str) and address[k].strip()
                for k in ("street", "city", "state", "zip")
            )
            (complete if sufficient else incomplete).append(
                str(address_id or canonical_sha256(address))
            )
        membership = (
            "API_AND_CONTROL"
            if linked.get(native_id) and api_item
            else "REFERENCED_DETAIL_AND_CONTROL"
            if linked.get(native_id)
            else "API_LISTED"
            if api_item
            else "REFERENCED_DETAIL_ONLY"
        )
        candidates.append(
            HybridCustomerCandidate(
                native_customer_id=native_id,
                membership=membership,
                outcome=outcome,
                api_digest=api_item.payload_digest if api_item else None,
                detail_digest=detail_item.payload_digest if detail_item else None,
                control_digests=tuple(
                    sorted(x.payload_digest for x in linked.get(native_id, []))
                ),
                conflict_fields=conflict_fields,
                contact_present=all(
                    isinstance(payload.get(k), str) and payload[k].strip()
                    for k in ("first_name", "last_name")
                ),
                location_ids=tuple(sorted(complete)),
                location_exception_ids=tuple(sorted(incomplete)),
                reason=reason,
                acquired_payload=dict(payload),
            )
        )
    unlinked = tuple(item for item in controls if item.control_identity not in links)
    result = HybridCustomerAdmission(
        version=HYBRID_ADMISSION_VERSION,
        candidates=tuple(candidates),
        unlinked_control_assertions=unlinked,
        digest=_admission_digest(tuple(candidates), unlinked),
    )
    result.validate()
    return result


def _unique_assertions(
    values: Iterable[CustomerAssertion], kind: AssertionKind
) -> dict[str, CustomerAssertion]:
    result: dict[str, CustomerAssertion] = {}
    for item in values:
        if item.kind != kind:
            raise ValueError("Customer assertion entered the wrong source collection")
        prior = result.get(item.source_identity)
        if prior and prior.payload_digest != item.payload_digest:
            raise ValueError("contradictory native Customer identity")
        result[item.source_identity] = item
    return result


@dataclass(frozen=True)
class JobParentClosure:
    version: str
    outcomes: tuple[tuple[str, str, ParentOutcome], ...]
    digest: str

    @property
    def counts(self) -> dict[str, int]:
        result = {item.value: 0 for item in ParentOutcome}
        for _, _, outcome in self.outcomes:
            result[outcome.value] += 1
        return result

    def validate(self) -> None:
        if self.version != PARENT_CLOSURE_VERSION:
            raise ValueError("unsupported parent closure version")
        if tuple(sorted(self.outcomes)) != self.outcomes:
            raise ValueError("parent closure is not canonical")
        if self.digest != canonical_sha256(
            {"version": self.version, "outcomes": self.outcomes}
        ):
            raise ValueError("parent closure digest mismatch")


def close_job_parents(
    job_customer_references: Iterable[tuple[str, str]],
    admission: HybridCustomerAdmission,
) -> JobParentClosure:
    admission.validate()
    by_id = {item.native_customer_id: item for item in admission.candidates}
    outcomes = []
    for job_id, customer_id in job_customer_references:
        item = by_id.get(customer_id)
        if item is None:
            outcome = ParentOutcome.MISSING_AUTHORITATIVE_CUSTOMER_EVIDENCE
        elif item.outcome == AdmissionOutcome.PERSISTABLE:
            outcome = ParentOutcome.RESOLVED_TO_PERSISTABLE_CUSTOMER
        elif item.outcome == AdmissionOutcome.EXPLICIT_EXCEPTION:
            outcome = ParentOutcome.RESOLVED_TO_EXPLICIT_EXCEPTION
        else:
            outcome = ParentOutcome.RESOLVED_TO_REJECTED_CUSTOMER
        outcomes.append((job_id, customer_id, outcome))
    canonical = tuple(sorted(outcomes))
    result = JobParentClosure(
        version=PARENT_CLOSURE_VERSION,
        outcomes=canonical,
        digest=canonical_sha256(
            {"version": PARENT_CLOSURE_VERSION, "outcomes": canonical}
        ),
    )
    result.validate()
    return result


def build_reviewed_customer_output(
    admission: HybridCustomerAdmission,
) -> tuple[ReviewedCustomerAdapterOutput, ApprovedCustomerImportBoundary]:
    """Project admitted assertions without altering or replacing source evidence."""
    admission.validate()
    aggregates: list[ReviewedCustomerAggregate] = []
    child_exceptions: list[str] = []
    for row_number, candidate in enumerate(admission.candidates, start=2):
        if candidate.outcome != AdmissionOutcome.PERSISTABLE:
            continue
        payload = candidate.acquired_payload
        child_exceptions.extend(
            canonical_sha256(
                {"customer": candidate.native_customer_id, "location": location_id}
            )
            for location_id in candidate.location_exception_ids
        )
        first = str(payload.get("first_name") or "").strip()
        last = str(payload.get("last_name") or "").strip()
        company = str(payload.get("company_name") or "").strip()
        display_name = company or " ".join(x for x in (first, last) if x)
        customer = CustomerCreate(
            customer_type=(
                CustomerType.COMMERCIAL
                if payload.get("kind") == "business"
                else CustomerType.RESIDENTIAL
            ),
            display_name=display_name,
            legal_name=company or None,
            marketing_source=payload.get("lead_source"),
            notes=payload.get("notes"),
            status=CustomerStatus.ACTIVE,
        )
        contact: ContactCreate | None = None
        if first and last:
            try:
                contact = ContactCreate(
                    first_name=first,
                    last_name=last,
                    email=payload.get("email"),
                    mobile_phone=payload.get("mobile_number"),
                    office_phone=payload.get("work_number")
                    or payload.get("home_number"),
                    is_preferred=True,
                )
            except ValueError:
                child_exceptions.append(
                    canonical_sha256(
                        {"customer": candidate.native_customer_id, "child": "contact"}
                    )
                )
        locations: list[ServiceLocationCreate] = []
        complete_ids = set(candidate.location_ids)
        for address in payload.get("addresses", []):
            if address.get("id") not in complete_ids:
                continue
            country = str(address.get("country") or "US").strip().upper()
            if country in {"USA", "UNITED STATES", "UNITED STATES OF AMERICA"}:
                country = "US"
            try:
                locations.append(
                    ServiceLocationCreate(
                        nickname=address.get("type"),
                        address=address["street"],
                        address_line_2=address.get("street_line_2"),
                        city=address["city"],
                        state=address["state"],
                        postal_code=address["zip"],
                        country=country,
                        gps_latitude=address.get("latitude"),
                        gps_longitude=address.get("longitude"),
                    )
                )
            except ValueError:
                child_exceptions.append(
                    canonical_sha256(
                        {
                            "customer": candidate.native_customer_id,
                            "location": address["id"],
                        }
                    )
                )
        source_digest = candidate.api_digest or candidate.detail_digest
        assert source_digest is not None
        aggregates.append(
            ReviewedCustomerAggregate(
                row_number=row_number,
                source_identity=candidate.native_customer_id,
                source_identity_sha256=hashlib.sha256(
                    candidate.native_customer_id.encode()
                ).hexdigest(),
                source_row_sha256=source_digest,
                customer_json=customer.model_dump_json(),
                contact_json=contact.model_dump_json() if contact else None,
                service_location_json=tuple(
                    item.model_dump_json() for item in locations
                ),
            billing_address_json=None,
            service_location_source_identities=tuple(
                address["id"]
                for address in payload.get("addresses", [])
                if address.get("id") in complete_ids
            ),
        )
        )
    rejected = tuple(
        sorted(
            hashlib.sha256(item.native_customer_id.encode()).hexdigest()
            for item in admission.candidates
            if item.outcome != AdmissionOutcome.PERSISTABLE
        )
    )
    source_digest = admission.digest
    transformation_digest = canonical_sha256(
        {"contract": HYBRID_ADMISSION_VERSION, "admission": admission.digest}
    )
    values: dict[str, object] = {
        "review_version": REVIEW_VERSION,
        "source_system": "housecall_pro_source4",
        "source_sha256": source_digest,
        "schema_version": HYBRID_ADMISSION_VERSION,
        "transformation_sha256": transformation_digest,
        "source_count": len(admission.candidates),
        "accepted_count": len(aggregates),
        "rejected_count": len(rejected),
        "duplicate_count": 0,
        "aggregates": tuple(aggregates),
        "rejected_source_identities": rejected,
        "duplicate_source_identities": (),
        "child_exception_source_identities": tuple(sorted(set(child_exceptions))),
    }
    reviewed = ReviewedCustomerAdapterOutput(
        review_version=REVIEW_VERSION,
        source_system="housecall_pro_source4",
        source_sha256=source_digest,
        schema_version=HYBRID_ADMISSION_VERSION,
        transformation_sha256=transformation_digest,
        source_count=len(admission.candidates),
        accepted_count=len(aggregates),
        rejected_count=len(rejected),
        duplicate_count=0,
        aggregates=tuple(aggregates),
        rejected_source_identities=rejected,
        duplicate_source_identities=(),
        child_exception_source_identities=tuple(sorted(set(child_exceptions))),
        review_sha256=canonical_sha256(
            {**values, "aggregates": [item.__dict__ for item in aggregates]}
        ),
    )
    reviewed.validate_integrity()
    approved = tuple(item.source_identity_sha256 for item in aggregates)
    event_population = customer_adapter_import_policy.event_population(aggregates)
    boundary = ApprovedCustomerImportBoundary(
        boundary_version=BOUNDARY_VERSION,
        source_sha256=source_digest,
        schema_version=HYBRID_ADMISSION_VERSION,
        pilot_boundary_sha256=hashlib.sha256(
            json.dumps(approved, separators=(",", ":")).encode()
        ).hexdigest(),
        approved_source_identities=approved,
        expected=ExpectedCustomerImportCounts(
            customers=len(aggregates),
            contacts=sum(item.contact_json is not None for item in aggregates),
            service_locations=sum(
                len(item.service_location_json) for item in aggregates
            ),
            billing_addresses=0,
            business_events=event_population.aggregate_domain_events,
            customer_admission_events=event_population.customer_admission_events,
            event_population_digest=event_population.digest,
        ),
    )
    boundary.validate()
    return reviewed, boundary
