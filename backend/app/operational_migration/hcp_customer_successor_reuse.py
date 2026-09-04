"""Manifest-bound, non-mutating resolution of reusable Preview Customers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customer_migration.adapter_import import ReviewedCustomerAggregate
from app.customer_migration.models import (
    CustomerSourceIdentity,
    ServiceLocationSourceIdentity,
)
from app.customers.models import Customer, CustomerContact, ServiceLocation
from app.operational_migration.hcp_successor_reconciliation import (
    LEGACY_SOURCE_SYSTEM,
    PrivateSuccessorManifest,
)
from app.operational_migration.hcp_successor_reuse import QualifiedSuccessorManifest
from app.platform.permissions.authorization import AuthorizationContext


class CustomerSuccessorReuseError(ValueError):
    pass


class CustomerSuccessorReuseResolver:
    """Resolve only exact, manifest-authorized legacy targets in the same Branch."""

    def __init__(
        self, manifest: PrivateSuccessorManifest | QualifiedSuccessorManifest
    ) -> None:
        self._customers = {
            item.source_id: getattr(item, "target_id", None)
            or getattr(item, "native_id", None)
            for item in manifest.entries
            if item.domain == "customer"
            and (
                getattr(item, "target_id", None)
                or getattr(item, "native_id", None)
            )
        }
        self._locations = {
            item.source_id: getattr(item, "target_id", None)
            or getattr(item, "native_id", None)
            for item in manifest.entries
            if item.domain == "service_location"
            and (
                getattr(item, "target_id", None)
                or getattr(item, "native_id", None)
            )
        }

    async def __call__(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        aggregate: ReviewedCustomerAggregate,
    ) -> tuple[Customer, tuple[ServiceLocation, ...]] | None:
        target = self._customers.get(aggregate.source_identity)
        if target is None:
            return None
        if context.active_branch is None:
            raise CustomerSuccessorReuseError("successor active Branch missing")
        identity = await session.scalar(
            select(CustomerSourceIdentity).where(
                CustomerSourceIdentity.company_id == context.company.id,
                CustomerSourceIdentity.branch_id == context.active_branch.id,
                CustomerSourceIdentity.source_system == LEGACY_SOURCE_SYSTEM,
                CustomerSourceIdentity.source_customer_id == aggregate.source_identity,
            )
        )
        if identity is None or str(identity.customer_id) != target:
            raise CustomerSuccessorReuseError("successor Customer manifest drift")
        customer = await session.get(Customer, identity.customer_id)
        if customer is None or customer.company_id != context.company.id:
            raise CustomerSuccessorReuseError("successor Customer scope conflict")
        proposed = aggregate.customer
        if (
            customer.display_name != proposed.display_name
            or customer.legal_name != proposed.legal_name
            or customer.customer_type != proposed.customer_type.value
        ):
            raise CustomerSuccessorReuseError("successor Customer field conflict")

        if aggregate.contact is not None:
            contact = await session.get(CustomerContact, customer.primary_contact_id)
            proposed_contact = aggregate.contact
            if (
                contact is None
                or contact.customer_id != customer.id
                or contact.first_name != proposed_contact.first_name
                or contact.last_name != proposed_contact.last_name
                or contact.normalized_email != proposed_contact.email
            ):
                raise CustomerSuccessorReuseError(
                    "successor Contact relationship conflict"
                )

        locations: list[ServiceLocation] = []
        for source_id, proposed_location in zip(
            aggregate.service_location_source_identities,
            aggregate.service_locations,
            strict=True,
        ):
            target_location = self._locations.get(source_id)
            identity_location = await session.scalar(
                select(ServiceLocationSourceIdentity).where(
                    ServiceLocationSourceIdentity.company_id == context.company.id,
                    ServiceLocationSourceIdentity.branch_id == context.active_branch.id,
                    ServiceLocationSourceIdentity.source_system == LEGACY_SOURCE_SYSTEM,
                    ServiceLocationSourceIdentity.source_location_id == source_id,
                )
            )
            if (
                target_location is None
                or identity_location is None
                or str(identity_location.service_location_id) != target_location
                or identity_location.customer_id != customer.id
            ):
                raise CustomerSuccessorReuseError("successor Location manifest drift")
            location = await session.get(
                ServiceLocation, identity_location.service_location_id
            )
            comparable = (
                "address",
                "address_line_2",
                "city",
                "state",
                "postal_code",
                "country",
            )
            if location is None or any(
                getattr(location, field) != getattr(proposed_location, field)
                for field in comparable
            ):
                raise CustomerSuccessorReuseError("successor Location field conflict")
            locations.append(location)
        return customer, tuple(locations)
