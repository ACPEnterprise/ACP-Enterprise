import hashlib
import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.customers.normalization import (
    build_normalized_address,
    normalize_email,
    normalize_phone,
    normalize_search_text,
)
from app.customers.schemas import ContactCreate, CustomerCreate, ServiceLocationCreate


class ReviewedAggregate(Protocol):
    @property
    def source_identity_sha256(self) -> str: ...

    @property
    def customer(self) -> CustomerCreate: ...

    @property
    def contact(self) -> ContactCreate | None: ...

    @property
    def service_locations(self) -> tuple[ServiceLocationCreate, ...]: ...

    @property
    def billing_address(self) -> ServiceLocationCreate | None: ...


@dataclass(frozen=True)
class ImportCountBoundary:
    customers: int
    contacts: int
    service_locations: int
    billing_addresses: int
    business_events: int


EVENT_POPULATION_VERSION = "customer-import-event-population/v1"


@dataclass(frozen=True)
class CustomerEventPopulation:
    """Canonical distinction between admission and emitted domain events."""

    customer_admission_events: int
    customer_domain_events: int
    contact_projection_events: int
    service_location_projection_events: int
    billing_address_projection_events: int
    audit_events_in_boundary: int
    lineage_events_in_boundary: int
    aggregate_domain_events: int
    digest: str

    def validate(self) -> None:
        counts = (
            self.customer_admission_events,
            self.customer_domain_events,
            self.contact_projection_events,
            self.service_location_projection_events,
            self.billing_address_projection_events,
            self.audit_events_in_boundary,
            self.lineage_events_in_boundary,
            self.aggregate_domain_events,
        )
        if any(value < 0 for value in counts):
            raise ValueError("event-population counts cannot be negative")
        if self.customer_admission_events != self.customer_domain_events:
            raise ValueError("every admitted Customer requires one Customer domain event")
        if self.aggregate_domain_events != sum(counts[1:5]):
            raise ValueError("aggregate domain-event count does not reconcile")
        if self.audit_events_in_boundary or self.lineage_events_in_boundary:
            raise ValueError("audit and lineage events are outside admission boundary")
        if len(self.digest) != 64:
            raise ValueError("event-population digest is required")


@dataclass(frozen=True)
class DuplicateLookup:
    normalized_name: str
    normalized_emails: tuple[str, ...]
    normalized_phones: tuple[str, ...]
    normalized_address: str | None


class CustomerAdapterImportPolicy:
    """Provider-neutral admission and duplicate policy for reviewed Customers."""

    @staticmethod
    def event_population(
        selected: Sequence[ReviewedAggregate],
    ) -> CustomerEventPopulation:
        events: list[tuple[str, str, int]] = []
        admissions: list[str] = []
        for aggregate in selected:
            identity = aggregate.source_identity_sha256
            if not identity or len(identity) != 64:
                raise ValueError("authoritative source identity digest is required")
            admissions.append(identity)
            events.append(("customer", identity, 0))
            if aggregate.contact is not None:
                events.append(("contact", identity, 0))
            events.extend(
                ("service_location", identity, ordinal)
                for ordinal, _ in enumerate(aggregate.service_locations)
            )
            if aggregate.billing_address is not None:
                events.append(("billing_address", identity, 0))
        if len(admissions) != len(set(admissions)):
            raise ValueError("duplicate Customer admission event identity")
        if len(events) != len(set(events)):
            raise ValueError("duplicate aggregate domain-event identity")
        categories = {
            category: sum(item[0] == category for item in events)
            for category in (
                "customer",
                "contact",
                "service_location",
                "billing_address",
            )
        }
        payload = {
            "contract": EVENT_POPULATION_VERSION,
            "customer_admission_identities": sorted(admissions),
            "aggregate_domain_event_identities": sorted(events),
            "audit_events_in_boundary": 0,
            "lineage_events_in_boundary": 0,
        }
        population = CustomerEventPopulation(
            customer_admission_events=len(admissions),
            customer_domain_events=categories["customer"],
            contact_projection_events=categories["contact"],
            service_location_projection_events=categories["service_location"],
            billing_address_projection_events=categories["billing_address"],
            audit_events_in_boundary=0,
            lineage_events_in_boundary=0,
            aggregate_domain_events=len(events),
            digest=hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        )
        population.validate()
        return population

    @staticmethod
    def expected_counts(
        selected: Sequence[ReviewedAggregate],
    ) -> ImportCountBoundary:
        population = CustomerAdapterImportPolicy.event_population(selected)
        return ImportCountBoundary(
            customers=population.customer_domain_events,
            contacts=population.contact_projection_events,
            service_locations=population.service_location_projection_events,
            billing_addresses=population.billing_address_projection_events,
            business_events=population.aggregate_domain_events,
        )

    @staticmethod
    def duplicate_members(
        aggregates: Sequence[ReviewedAggregate],
    ) -> frozenset[str]:
        """Return no hard exclusions from non-authoritative profile similarity.

        Provider-native identity is the admission key. Names, contact values, and
        addresses are useful reconciliation signals but cannot prove that two
        source Customers are the same person or business.
        """
        return frozenset()

    @staticmethod
    def similarity_evidence(
        aggregates: Sequence[ReviewedAggregate],
    ) -> dict[str, tuple[tuple[str, ...], ...]]:
        """Return deterministic review clusters without changing admission."""
        signals: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        for aggregate in aggregates:
            identity = aggregate.source_identity_sha256
            signals["name"][normalize_search_text(aggregate.customer.display_name)].add(
                identity
            )
            contact = aggregate.contact
            if contact is not None:
                if contact.email:
                    signals["email"][normalize_email(contact.email)].add(identity)
                for phone in (contact.mobile_phone, contact.office_phone):
                    if phone:
                        signals["phone"][normalize_phone(phone)].add(identity)
            for location in aggregate.service_locations + (
                (aggregate.billing_address,)
                if aggregate.billing_address is not None
                else ()
            ):
                signals["address"][
                    build_normalized_address(
                        location.address,
                        location.address_line_2,
                        location.city,
                        location.state,
                        location.postal_code,
                    )
                ].add(identity)
        clusters: dict[str, list[tuple[str, ...]]] = defaultdict(list)
        for groups in signals.values():
            for signal, identities in groups.items():
                if len(identities) > 1:
                    clusters[signal].append(tuple(sorted(identities)))
        return {
            signal: tuple(sorted(values))
            for signal, values in sorted(clusters.items())
        }

    @staticmethod
    def duplicate_lookup(aggregate: ReviewedAggregate) -> DuplicateLookup:
        contact = aggregate.contact
        emails = (
            (normalize_email(contact.email),)
            if contact is not None and contact.email
            else ()
        )
        phones = tuple(
            normalize_phone(phone)
            for phone in (
                contact.mobile_phone if contact else None,
                contact.office_phone if contact else None,
            )
            if phone
        )
        location = (
            aggregate.service_locations[0] if aggregate.service_locations else None
        )
        normalized_address = (
            build_normalized_address(
                location.address,
                location.address_line_2,
                location.city,
                location.state,
                location.postal_code,
            )
            if location is not None
            else None
        )
        return DuplicateLookup(
            normalized_name=normalize_search_text(aggregate.customer.display_name),
            normalized_emails=emails,
            normalized_phones=phones,
            normalized_address=normalized_address,
        )

    @staticmethod
    def candidate_hashes(
        aggregate: ReviewedAggregate,
    ) -> dict[tuple[str, int], str]:
        def payload_sha256(
            model: CustomerCreate | ContactCreate | ServiceLocationCreate,
        ) -> str:
            payload = model.model_dump(mode="json")
            return hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode()
            ).hexdigest()

        expected = {("customer", 0): payload_sha256(aggregate.customer)}
        if aggregate.contact is not None:
            expected[("contact", 0)] = payload_sha256(aggregate.contact)
        for ordinal, location in enumerate(aggregate.service_locations):
            expected[("service_location", ordinal)] = payload_sha256(location)
        if aggregate.billing_address is not None:
            expected[("billing_address", 0)] = payload_sha256(aggregate.billing_address)
        return expected


customer_adapter_import_policy = CustomerAdapterImportPolicy()
