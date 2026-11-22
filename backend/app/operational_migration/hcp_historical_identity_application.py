"""Durable application of an evidence-backed historical HCP identity plan."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customer_migration.models import (
    CustomerSourceIdentity,
    ServiceLocationSourceIdentity,
)
from app.operational_migration.hcp_historical_identity_bridge import (
    BridgeDisposition,
    HistoricalIdentityBridgePlan,
    _digest,
)
from app.operational_migration.models import HcpSource4NativeBindingEvidence

LEGACY_SOURCE = "housecall_pro"
SOURCE4_SOURCE = "housecall_pro_source4"
APPLICATION_CONTRACT = "hcp-historical-identity-application/v1"


@dataclass(frozen=True, slots=True)
class ApplicationCounts:
    source: int
    already_bound: int
    newly_bound: int
    ambiguous: int
    quarantined: int
    unmatched: int
    duplicates_prevented: int
    unexplained: int


@dataclass(frozen=True, slots=True)
class HistoricalIdentityApplicationResult:
    customers: ApplicationCounts
    locations: ApplicationCounts


class HistoricalIdentityBridgeApplication:
    """Apply only admitted deterministic decisions inside the caller transaction.

    Database uniqueness constraints remain the final concurrency guard. Replays
    read the exact source and target identities and therefore perform no writes.
    """

    def __init__(
        self,
        *,
        company_id: UUID,
        branch_id: UUID,
        master_run_id: UUID,
        customer_run_id: UUID,
        package_digest: str,
    ) -> None:
        self.company_id = company_id
        self.branch_id = branch_id
        self.master_run_id = master_run_id
        self.customer_run_id = customer_run_id
        self.package_digest = package_digest

    async def apply(
        self, session: AsyncSession, plan: HistoricalIdentityBridgePlan
    ) -> HistoricalIdentityApplicationResult:
        plan.verify()
        customer: Counter[str] = Counter()
        location: Counter[str] = Counter()
        customer["source"] = plan.source_count
        customer["duplicates_prevented"] = plan.duplicates_prevented

        for decision in plan.decisions:
            if decision.disposition is BridgeDisposition.AMBIGUOUS:
                customer["ambiguous"] += 1
                continue
            if decision.disposition is BridgeDisposition.QUARANTINED:
                key = (
                    "unmatched"
                    if decision.reason.startswith("no candidate")
                    else "quarantined"
                )
                customer[key] += 1
                continue
            if decision.native_customer_id is None:
                customer["unexplained"] += 1
                continue

            identity, created = await self._customer(
                session, decision.source_customer_id, UUID(decision.native_customer_id)
            )
            customer["newly_bound" if created else "already_bound"] += 1
            for item in decision.locations:
                location["source"] += 1
                if item.disposition is BridgeDisposition.AMBIGUOUS:
                    location["ambiguous"] += 1
                elif item.native_location_id is None:
                    location["unmatched"] += 1
                else:
                    made = await self._location(
                        session,
                        customer_identity=identity,
                        source_id=item.source_location_id,
                        native_id=UUID(item.native_location_id),
                    )
                    location["newly_bound" if made else "already_bound"] += 1

        return HistoricalIdentityApplicationResult(
            customers=_counts(customer), locations=_counts(location)
        )

    async def _customer(
        self, session: AsyncSession, source_id: str, native_id: UUID
    ) -> tuple[CustomerSourceIdentity, bool]:
        existing = await session.scalar(
            select(CustomerSourceIdentity).where(
                CustomerSourceIdentity.company_id == self.company_id,
                CustomerSourceIdentity.source_system == SOURCE4_SOURCE,
                CustomerSourceIdentity.source_customer_id == source_id,
            )
        )
        if existing is not None:
            if existing.customer_id != native_id:
                raise ValueError(
                    f"SOURCE.4 Customer identity target changed: {source_id}:"
                    f"{existing.customer_id}:{native_id}"
                )
            return existing, False
        target = await session.scalar(
            select(CustomerSourceIdentity).where(
                CustomerSourceIdentity.company_id == self.company_id,
                CustomerSourceIdentity.source_system == SOURCE4_SOURCE,
                CustomerSourceIdentity.customer_id == native_id,
            )
        )
        if target is not None:
            raise ValueError("canonical Customer already has another SOURCE.4 identity")
        legacy = await self._legacy_customer(session, native_id)
        identity = CustomerSourceIdentity(
            company_id=self.company_id,
            branch_id=self.branch_id,
            customer_id=native_id,
            source_system=SOURCE4_SOURCE,
            source_customer_id=source_id,
            first_run_id=self.customer_run_id,
        )
        session.add(identity)
        await session.flush()
        await self._evidence(
            session, "customer", source_id, native_id, legacy, identity
        )
        return identity, True

    async def _location(
        self,
        session: AsyncSession,
        *,
        customer_identity: CustomerSourceIdentity,
        source_id: str,
        native_id: UUID,
    ) -> bool:
        existing = await session.scalar(
            select(ServiceLocationSourceIdentity).where(
                ServiceLocationSourceIdentity.company_id == self.company_id,
                ServiceLocationSourceIdentity.source_system == SOURCE4_SOURCE,
                ServiceLocationSourceIdentity.source_location_id == source_id,
            )
        )
        if existing is not None:
            if (
                existing.service_location_id != native_id
                or existing.customer_id != customer_identity.customer_id
            ):
                raise ValueError("SOURCE.4 Location identity target changed")
            return False
        target = await session.scalar(
            select(ServiceLocationSourceIdentity).where(
                ServiceLocationSourceIdentity.company_id == self.company_id,
                ServiceLocationSourceIdentity.source_system == SOURCE4_SOURCE,
                ServiceLocationSourceIdentity.service_location_id == native_id,
            )
        )
        if target is not None:
            raise ValueError("canonical Location already has another SOURCE.4 identity")
        legacy_location = await session.scalar(
            select(ServiceLocationSourceIdentity).where(
                ServiceLocationSourceIdentity.company_id == self.company_id,
                ServiceLocationSourceIdentity.source_system == LEGACY_SOURCE,
                ServiceLocationSourceIdentity.service_location_id == native_id,
                ServiceLocationSourceIdentity.customer_id
                == customer_identity.customer_id,
            )
        )
        legacy: CustomerSourceIdentity | ServiceLocationSourceIdentity
        if legacy_location is None:
            # Some legacy imports retained Customer lineage but did not create a
            # provider Location crosswalk. The already-bound parent Customer plus
            # exact in-parent address is still deterministic relationship evidence.
            legacy = await self._legacy_customer(session, customer_identity.customer_id)
        else:
            legacy = legacy_location
        digest = _digest(
            {
                "contract": APPLICATION_CONTRACT,
                "source_id": source_id,
                "native_id": str(native_id),
            }
        )
        identity = ServiceLocationSourceIdentity(
            company_id=self.company_id,
            branch_id=self.branch_id,
            master_run_id=self.master_run_id,
            customer_source_identity_id=customer_identity.id,
            service_location_id=native_id,
            customer_id=customer_identity.customer_id,
            source_system=SOURCE4_SOURCE,
            source_location_id=source_id,
            source_digest=digest,
            package_digest=self.package_digest,
            transformation_version=APPLICATION_CONTRACT,
            transformation_digest=digest,
            source_context={
                "predecessor_lineage_identity_id": str(legacy.id),
                "predecessor_lineage_domain": (
                    "service_location"
                    if isinstance(legacy, ServiceLocationSourceIdentity)
                    else "customer"
                ),
                "location_rule": "exact_address_inside_deterministically_bound_customer",
            },
            first_run_id=self.customer_run_id,
        )
        session.add(identity)
        await session.flush()
        await self._evidence(
            session, "service_location", source_id, native_id, legacy, identity
        )
        return True

    async def _legacy_customer(
        self, session: AsyncSession, native_id: UUID
    ) -> CustomerSourceIdentity:
        value = await session.scalar(
            select(CustomerSourceIdentity).where(
                CustomerSourceIdentity.company_id == self.company_id,
                CustomerSourceIdentity.source_system == LEGACY_SOURCE,
                CustomerSourceIdentity.customer_id == native_id,
            )
        )
        if value is None:
            raise ValueError("deterministic Customer lacks predecessor lineage")
        return value

    async def _evidence(
        self,
        session: AsyncSession,
        domain: str,
        source_id: str,
        native_id: UUID,
        legacy: CustomerSourceIdentity | ServiceLocationSourceIdentity,
        source4: CustomerSourceIdentity | ServiceLocationSourceIdentity,
    ) -> None:
        digest = _digest(
            {
                "contract": APPLICATION_CONTRACT,
                "domain": domain,
                "source_id": source_id,
                "native_id": str(native_id),
                "legacy_identity_id": str(legacy.id),
                "source4_identity_id": str(source4.id),
                "package_digest": self.package_digest,
            }
        )
        session.add(
            HcpSource4NativeBindingEvidence(
                company_id=self.company_id,
                branch_id=self.branch_id,
                master_run_id=self.master_run_id,
                domain=domain,
                source4_source_id=source_id,
                native_id=native_id,
                legacy_source_identity_id=legacy.id,
                source4_source_identity_id=source4.id,
                package_digest=self.package_digest,
                predecessor_source_digest=digest,
                binding_digest=digest,
                evidence={
                    "contract": APPLICATION_CONTRACT,
                    "identity_rule": "deterministic_exact_evidence_and_predecessor_lineage",
                    "plan_mutation_authority": "canonical_crosswalk_only",
                },
            )
        )
        await session.flush()


def _counts(values: Counter[str]) -> ApplicationCounts:
    explained = sum(
        values[key]
        for key in (
            "already_bound",
            "newly_bound",
            "ambiguous",
            "quarantined",
            "unmatched",
        )
    )
    return ApplicationCounts(
        source=values["source"],
        already_bound=values["already_bound"],
        newly_bound=values["newly_bound"],
        ambiguous=values["ambiguous"],
        quarantined=values["quarantined"],
        unmatched=values["unmatched"],
        duplicates_prevented=values["duplicates_prevented"],
        unexplained=values["source"] - explained,
    )
