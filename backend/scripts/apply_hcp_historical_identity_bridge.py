"""Plan and durably apply retained HCP Customer/Location identity bindings."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import UUID

from app import main as application_main  # noqa: F401
from app.customer_migration.models import (
    CustomerSourceIdentity,
    ServiceLocationSourceIdentity,
)
from app.customers.models import Customer, CustomerContact, ServiceLocation
from app.database.session import AsyncSessionFactory
from app.operational_migration.hcp_historical_identity_application import (
    APPLICATION_CONTRACT,
    HistoricalIdentityBridgeApplication,
)
from app.operational_migration.hcp_historical_identity_bridge import (
    AddressEvidence,
    CanonicalCustomerEvidence,
    CanonicalLocationEvidence,
    SourceCustomerEvidence,
    build_historical_identity_bridge,
)
from app.operational_migration.models import (
    HcpMigrationMasterRun,
    HcpSource4NativeBindingEvidence,
)
from app.platform.company.models import Company  # noqa: F401
from sqlalchemy import select


def _rows(root: Path, family: str) -> Iterator[dict[str, Any]]:
    for path in sorted((root / "raw" / family).glob("*.json")):
        payload = json.loads(path.read_text())
        for row in payload.get(family, []):
            if family == "appointments" and path.stem.startswith("job-"):
                row = {**row, "_parent_job_id": path.stem.removeprefix("job-")}
            yield row


def _address(row: dict[str, Any], identity: str) -> AddressEvidence:
    return AddressEvidence(
        identity,
        str(row.get("street") or row.get("address_line_1") or ""),
        row.get("street_line_2") or row.get("address_line_2"),
        str(row.get("city") or ""),
        str(row.get("state") or ""),
        str(row.get("zip") or row.get("postal_code") or ""),
    )


async def run(
    root: Path, *, apply: bool, master_run_id: UUID | None = None
) -> dict[str, object]:
    source_jobs = list(_rows(root, "jobs"))
    job_addresses: defaultdict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for job in source_jobs:
        customer_id = str((job.get("customer") or {}).get("id") or "")
        address = job.get("address") or {}
        if customer_id and address.get("id"):
            job_addresses[customer_id][str(address["id"])] = address
    source = tuple(
        SourceCustomerEvidence(
            str(row["id"]),
            " ".join(
                part for part in (row.get("first_name"), row.get("last_name")) if part
            )
            or str(row.get("company") or ""),
            row.get("email"),
            tuple(
                str(value)
                for value in (
                    row.get("mobile_number"),
                    row.get("home_number"),
                    row.get("work_number"),
                )
                if value
            ),
            tuple(
                _address(item, identity)
                for identity, item in {
                    **job_addresses[str(row["id"])],
                    **{
                        str(item["id"]): item
                        for item in row.get("addresses") or []
                        if item.get("id")
                    },
                }.items()
            ),
        )
        for row in _rows(root, "customers")
    )
    async with AsyncSessionFactory() as session:
        master_query = select(HcpMigrationMasterRun)
        if master_run_id is not None:
            master_query = master_query.where(HcpMigrationMasterRun.id == master_run_id)
        else:
            master_query = master_query.order_by(
                HcpMigrationMasterRun.created_at.desc()
            )
        master = await session.scalar(master_query)
        if master is None:
            raise RuntimeError("HCP master run is unavailable")
        customers = (
            await session.scalars(
                select(Customer)
                .join(
                    CustomerSourceIdentity,
                    (CustomerSourceIdentity.customer_id == Customer.id)
                    & CustomerSourceIdentity.source_system.in_(
                        ("housecall_pro", "housecall_pro_source4")
                    ),
                )
                .where(Customer.company_id == master.company_id)
                .distinct()
            )
        ).all()
        customer_ids = [row.id for row in customers]
        contacts = (
            await session.scalars(
                select(CustomerContact).where(
                    CustomerContact.customer_id.in_(customer_ids)
                )
            )
        ).all()
        locations = (
            await session.scalars(
                select(ServiceLocation).where(
                    ServiceLocation.customer_id.in_(customer_ids)
                )
            )
        ).all()
        location_ids = [row.id for row in locations]
        location_identities = (
            await session.scalars(
                select(ServiceLocationSourceIdentity).where(
                    ServiceLocationSourceIdentity.service_location_id.in_(location_ids),
                    ServiceLocationSourceIdentity.source_system
                    == "housecall_pro_source4",
                )
            )
        ).all()
        identities = (
            await session.scalars(
                select(CustomerSourceIdentity).where(
                    CustomerSourceIdentity.customer_id.in_(customer_ids)
                )
            )
        ).all()
        by_contact: defaultdict[UUID, list[CustomerContact]] = defaultdict(list)
        by_location: defaultdict[UUID, list[ServiceLocation]] = defaultdict(list)
        by_identity: defaultdict[UUID, list[str]] = defaultdict(list)
        by_location_identity: defaultdict[UUID, list[str]] = defaultdict(list)
        for contact in contacts:
            by_contact[contact.customer_id].append(contact)
        for location in locations:
            by_location[location.customer_id].append(location)
        for identity in identities:
            if identity.source_system == "housecall_pro_source4":
                by_identity[identity.customer_id].append(identity.source_customer_id)
        for location_identity in location_identities:
            by_location_identity[location_identity.service_location_id].append(
                location_identity.source_location_id
            )
        canonical = tuple(
            CanonicalCustomerEvidence(
                str(customer.id),
                customer.display_name,
                customer.email
                or next(
                    (item.email for item in by_contact[customer.id] if item.email),
                    None,
                ),
                tuple(
                    value
                    for value in (
                        customer.primary_phone,
                        customer.secondary_phone,
                        *(item.mobile_phone for item in by_contact[customer.id]),
                        *(item.office_phone for item in by_contact[customer.id]),
                    )
                    if value
                ),
                tuple(
                    CanonicalLocationEvidence(
                        str(item.id),
                        AddressEvidence(
                            "",
                            item.address,
                            item.address_line_2,
                            item.city,
                            item.state,
                            item.postal_code,
                        ),
                        tuple(by_location_identity[item.id]),
                    )
                    for item in by_location[customer.id]
                ),
                tuple(by_identity[customer.id]),
            )
            for customer in customers
        )
        plan = build_historical_identity_bridge(source=source, canonical=canonical)
        result = None
        if apply:
            from app.customer_migration.models import CustomerMigrationRun

            customer_run = await session.scalar(
                select(CustomerMigrationRun).where(
                    CustomerMigrationRun.master_run_id == master.id
                )
            )
            if customer_run is None:
                raise RuntimeError("SOURCE.4 Customer run is unavailable")
            application = HistoricalIdentityBridgeApplication(
                company_id=master.company_id,
                branch_id=master.branch_id,
                master_run_id=master.id,
                customer_run_id=customer_run.id,
                package_digest=master.package_digest,
            )
            async with session.begin_nested():
                result = await application.apply(session, plan)
            await session.commit()
        dispositions: defaultdict[str, int] = defaultdict(int)
        for item in plan.decisions:
            dispositions[item.disposition.value] += 1
        richard = [
            item
            for item in plan.decisions
            if item.source_customer_id == "cus_4c14fc784bea4c2692995823a75c8deb"
        ]
        new_customer_ids = set(
            (
                await session.scalars(
                    select(HcpSource4NativeBindingEvidence.source4_source_id).where(
                        HcpSource4NativeBindingEvidence.company_id == master.company_id,
                        HcpSource4NativeBindingEvidence.domain == "customer",
                        HcpSource4NativeBindingEvidence.evidence["contract"].astext
                        == APPLICATION_CONTRACT,
                    )
                )
            ).all()
        )
        category: dict[str, str] = {}
        for item in plan.decisions:
            category[item.source_customer_id] = (
                "newly_bound"
                if item.source_customer_id in new_customer_ids
                else "already_bound"
                if item.native_customer_id
                else "ambiguous"
                if item.disposition.value == "AMBIGUOUS"
                else "unmatched"
            )
        source_by_id = {item.source_customer_id: item for item in source}
        domains: dict[str, dict[str, int]] = {}
        new_location_ids = set(
            (
                await session.scalars(
                    select(HcpSource4NativeBindingEvidence.source4_source_id).where(
                        HcpSource4NativeBindingEvidence.company_id == master.company_id,
                        HcpSource4NativeBindingEvidence.domain == "service_location",
                        HcpSource4NativeBindingEvidence.evidence["contract"].astext
                        == APPLICATION_CONTRACT,
                    )
                )
            ).all()
        )
        location_counts: defaultdict[str, int] = defaultdict(int)
        for item in plan.decisions:
            source_locations = source_by_id[item.source_customer_id].locations
            if category[item.source_customer_id] in {"ambiguous", "unmatched"}:
                location_counts[category[item.source_customer_id]] += len(
                    source_locations
                )
                continue
            for location_decision in item.locations:
                if location_decision.native_location_id is None:
                    location_counts[
                        "ambiguous"
                        if location_decision.disposition.value == "AMBIGUOUS"
                        else "unmatched"
                    ] += 1
                elif location_decision.source_location_id in new_location_ids:
                    location_counts["newly_bound"] += 1
                else:
                    location_counts["already_bound"] += 1
        location_source = sum(len(item.locations) for item in source)
        domains["locations"] = {
            "source": location_source,
            "already_bound": location_counts["already_bound"],
            "newly_bound": location_counts["newly_bound"],
            "ambiguous": location_counts["ambiguous"],
            "quarantined": 0,
            "unmatched": location_counts["unmatched"],
            "duplicates_prevented": 0,
            "unexplained": location_source - sum(location_counts.values()),
        }
        jobs = source_jobs
        job_customer = {
            str(item["id"]): str((item.get("customer") or {}).get("id") or "")
            for item in jobs
        }
        domain_rows: dict[str, list[str]] = {
            "jobs": [job_customer.get(str(item.get("id")), "") for item in jobs],
            "appointments": [
                job_customer.get(
                    str(
                        item.get("_parent_job_id")
                        or item.get("job_id")
                        or (item.get("job") or {}).get("id")
                    ),
                    "",
                )
                for item in _rows(root, "appointments")
            ],
            "estimates": [
                str((item.get("customer") or {}).get("id") or "")
                for item in _rows(root, "estimates")
            ],
        }
        invoices = list(_rows(root, "invoices"))
        domain_rows["invoices"] = [
            job_customer.get(str(item.get("job_id")), "") for item in invoices
        ]
        domain_rows["payments"] = [
            job_customer.get(str(item.get("job_id")), "")
            for item in invoices
            for _payment in item.get("payments") or []
        ]
        domain_rows["refunds"] = [
            job_customer.get(str(item.get("job_id")), "")
            for item in invoices
            for _refund in item.get("refunds") or []
        ]
        for domain, parents in domain_rows.items():
            counts: defaultdict[str, int] = defaultdict(int)
            for parent in parents:
                counts[category.get(parent, "unmatched")] += 1
            domains[domain] = {
                "source": len(parents),
                "already_bound": counts["already_bound"],
                "newly_bound": counts["newly_bound"],
                "ambiguous": counts["ambiguous"],
                "quarantined": 0,
                "unmatched": counts["unmatched"],
                "duplicates_prevented": 0,
                "unexplained": len(parents) - sum(counts.values()),
            }
        metrics = {domain: Counter(parents) for domain, parents in domain_rows.items()}
        native_status = {str(item.id): item.status for item in customers}
        decision_by_id = {item.source_customer_id: item for item in plan.decisions}
        selected: list[str] = ["cus_4c14fc784bea4c2692995823a75c8deb"]

        def add_best(predicate) -> None:
            options = [
                item
                for item in plan.decisions
                if item.source_customer_id not in selected and predicate(item)
            ]
            if options:
                selected.append(
                    max(
                        options,
                        key=lambda item: (
                            metrics["jobs"][item.source_customer_id]
                            + metrics["estimates"][item.source_customer_id]
                            + metrics["invoices"][item.source_customer_id]
                            + metrics["payments"][item.source_customer_id],
                            item.source_customer_id,
                        ),
                    ).source_customer_id
                )

        add_best(lambda item: item.disposition.value == "AMBIGUOUS")
        add_best(lambda item: item.disposition.value == "QUARANTINED")
        add_best(
            lambda item: (
                len(source_by_id[item.source_customer_id].locations) > 1
                and item.native_customer_id is not None
            )
        )
        add_best(
            lambda item: (
                metrics["jobs"][item.source_customer_id] >= 5
                and item.native_customer_id is not None
            )
        )
        add_best(
            lambda item: (
                metrics["estimates"][item.source_customer_id] > 0
                and item.native_customer_id is not None
            )
        )
        add_best(
            lambda item: (
                metrics["invoices"][item.source_customer_id] > 0
                and item.native_customer_id is not None
            )
        )
        add_best(
            lambda item: (
                metrics["payments"][item.source_customer_id] > 0
                and item.native_customer_id is not None
            )
        )
        add_best(
            lambda item: (
                item.native_customer_id is not None
                and native_status.get(item.native_customer_id) == "inactive"
            )
        )
        for item in plan.decisions:
            if len(selected) >= 20:
                break
            if item.source_customer_id not in selected and item.native_customer_id:
                selected.append(item.source_customer_id)
        cohort = []
        for source_id in selected:
            item = decision_by_id[source_id]
            evidence = source_by_id[source_id]
            cohort.append(
                {
                    "source_customer_id": source_id,
                    "name": evidence.display_name,
                    "disposition": category[source_id],
                    "locations": len(evidence.locations),
                    "jobs": metrics["jobs"][source_id],
                    "estimates": metrics["estimates"][source_id],
                    "invoices": metrics["invoices"][source_id],
                    "payments": metrics["payments"][source_id],
                    "canonical_status": native_status.get(
                        item.native_customer_id or ""
                    ),
                }
            )
        return {
            "plan_digest": plan.digest,
            "source": plan.source_count,
            "dispositions": dict(sorted(dispositions.items())),
            "duplicates_prevented": plan.duplicates_prevented,
            "unexplained": plan.unexplained,
            "application": (
                {
                    "customers": asdict(result.customers),
                    "locations": asdict(result.locations),
                }
                if result
                else None
            ),
            "domains": domains,
            "acceptance_cohort": cohort,
            "richard_ratliff": [
                {
                    "disposition": item.disposition.value,
                    "native_customer_id": item.native_customer_id,
                    "evidence_dimensions": item.evidence_dimensions,
                    "locations": len(
                        [
                            location
                            for location in item.locations
                            if location.native_location_id
                        ]
                    ),
                }
                for item in richard
            ],
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--master-run-id", type=UUID)
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(
                run(
                    args.source,
                    apply=args.apply,
                    master_run_id=args.master_run_id,
                )
            ),
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
