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


@dataclass(frozen=True)
class DuplicateLookup:
    normalized_name: str
    normalized_emails: tuple[str, ...]
    normalized_phones: tuple[str, ...]
    normalized_address: str | None


class CustomerAdapterImportPolicy:
    """Provider-neutral admission and duplicate policy for reviewed Customers."""

    @staticmethod
    def expected_counts(
        selected: Sequence[ReviewedAggregate],
    ) -> ImportCountBoundary:
        return ImportCountBoundary(
            customers=len(selected),
            contacts=sum(item.contact is not None for item in selected),
            service_locations=sum(len(item.service_locations) for item in selected),
            billing_addresses=sum(
                item.billing_address is not None for item in selected
            ),
            business_events=sum(
                1
                + (item.contact is not None)
                + len(item.service_locations)
                + (item.billing_address is not None)
                for item in selected
            ),
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
