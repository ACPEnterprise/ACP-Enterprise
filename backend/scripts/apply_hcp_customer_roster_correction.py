"""Apply an owner-approved HCP Customer CSV to an isolated ACP database.

The command is exact-provider-ID only. It never reads or writes HCP, never
deletes a native record, and preserves a Customer for review when a native
Customer update occurred after its provider binding was created.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from collections import Counter
from pathlib import Path
from uuid import UUID

from app import main as application_model_registry  # noqa: F401
from app.customer_migration.housecall_pro_adapter import (
    AdaptedCustomerRecord,
    HousecallProCustomerExportAdapter,
)
from app.customer_migration.models import (
    CustomerMigrationException,
    CustomerMigrationRun,
    CustomerSourceIdentity,
    utc_now,
)
from app.customers.models import Customer, CustomerContact, ServiceLocation
from app.customers.normalization import (
    build_normalized_address,
    normalize_email,
    normalize_phone,
    normalize_search_text,
)
from app.customers.service import CustomerService
from app.database.session import AsyncSessionFactory, engine
from app.events.models import BusinessEvent
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import CustomerPermission
from app.platform.permissions.models import Permission
from app.platform.users.models import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

SOURCE_SYSTEM = "housecall_pro"
CONTRACT = "hcp-customer-roster-correction/v1"


def _changed(target: object, field: str, value: object) -> bool:
    if getattr(target, field) == value:
        return False
    setattr(target, field, value)
    return True


async def _context(
    session: AsyncSession, *, company_id: UUID, branch_id: UUID, actor_id: UUID
) -> AuthorizationContext:
    company = await session.get(Company, company_id)
    branch = await session.get(Branch, branch_id)
    actor = await session.get(User, actor_id)
    membership = await session.scalar(
        select(Membership).where(
            Membership.company_id == company_id, Membership.user_id == actor_id
        )
    )
    permission = await session.scalar(
        select(Permission).where(Permission.code == CustomerPermission.MANAGE)
    )
    if None in (company, branch, actor, membership, permission):
        raise ValueError("isolated acceptance authority is incomplete")
    return AuthorizationContext(
        user=actor,
        company=company,
        membership=membership,
        authorized_branches=(branch,),
        active_branch=branch,
        effective_roles=(),
        effective_permissions=(permission,),
        credential_version=1,
        authorization_version=1,
    )


async def _native_change_after_binding(
    session: AsyncSession, identity: CustomerSourceIdentity
) -> bool:
    event = await session.scalar(
        select(BusinessEvent.id)
        .where(
            BusinessEvent.company_id == identity.company_id,
            BusinessEvent.entity_type == "customer",
            BusinessEvent.entity_id == identity.customer_id,
            BusinessEvent.event_type == "customer.updated",
            BusinessEvent.occurred_at > identity.created_at,
        )
        .limit(1)
    )
    return event is not None


async def _apply_contact(
    session: AsyncSession, customer: Customer, record: AdaptedCustomerRecord
) -> bool:
    source = record.contact
    if source is None:
        return False
    contact = await session.scalar(
        select(CustomerContact)
        .where(CustomerContact.customer_id == customer.id)
        .order_by(CustomerContact.is_preferred.desc(), CustomerContact.created_at)
        .limit(1)
    )
    if contact is None:
        contact = CustomerContact(
            customer_id=customer.id,
            first_name=source.first_name,
            last_name=source.last_name,
            title=source.title,
            email=normalize_email(source.email) if source.email else None,
            normalized_email=normalize_email(source.email) if source.email else None,
            mobile_phone=source.mobile_phone,
            normalized_mobile_phone=(
                normalize_phone(source.mobile_phone) if source.mobile_phone else None
            ),
            office_phone=source.office_phone,
            normalized_office_phone=(
                normalize_phone(source.office_phone) if source.office_phone else None
            ),
            is_preferred=True,
            active=True,
        )
        session.add(contact)
        await session.flush()
        customer.primary_contact_id = contact.id
        return True
    changed = False
    values = {
        "first_name": source.first_name,
        "last_name": source.last_name,
        "title": source.title,
        "email": normalize_email(source.email) if source.email else None,
        "normalized_email": normalize_email(source.email) if source.email else None,
        "mobile_phone": source.mobile_phone,
        "normalized_mobile_phone": (
            normalize_phone(source.mobile_phone) if source.mobile_phone else None
        ),
        "office_phone": source.office_phone,
        "normalized_office_phone": (
            normalize_phone(source.office_phone) if source.office_phone else None
        ),
    }
    for field, value in values.items():
        changed |= _changed(contact, field, value)
    return changed


async def _apply_locations(
    session: AsyncSession,
    *,
    context: AuthorizationContext,
    customer: Customer,
    record: AdaptedCustomerRecord,
    service: CustomerService,
) -> tuple[int, int]:
    existing = list(
        (
            await session.scalars(
                select(ServiceLocation).where(
                    ServiceLocation.customer_id == customer.id
                )
            )
        ).all()
    )
    addresses = {item.normalized_address for item in existing}
    added = duplicates = 0
    for location in record.service_locations:
        normalized = build_normalized_address(
            location.address,
            location.address_line_2,
            location.city,
            location.state,
            location.postal_code,
        )
        if normalized in addresses:
            duplicates += 1
            continue
        await service.stage_migrated_service_location(
            session, context=context, customer_id=customer.id, data=location
        )
        addresses.add(normalized)
        added += 1
    return added, duplicates


async def apply(args: argparse.Namespace) -> dict[str, object]:
    source = args.source.read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    if digest != args.sha256:
        raise ValueError("Customer CSV digest mismatch")
    report = HousecallProCustomerExportAdapter().transform(
        source, expected_source_sha256=args.sha256
    )
    if report.source != 5464 or report.accepted + report.rejected + report.duplicate != report.source:
        raise ValueError("Customer CSV row accounting mismatch")
    records = {item.source_id: item for item in report.records}
    counts: Counter[str] = Counter()
    service = CustomerService()
    async with AsyncSessionFactory() as session, session.begin():
        context = await _context(
            session,
            company_id=args.company_id,
            branch_id=args.branch_id,
            actor_id=args.actor_id,
        )
        run = CustomerMigrationRun(
            company_id=args.company_id,
            branch_id=args.branch_id,
            initiated_by_user_id=args.actor_id,
            source_system=SOURCE_SYSTEM,
            source_sha256=digest,
            mode="import",
            status="running",
            source_count=report.source,
            unresolved_count=report.source,
        )
        session.add(run)
        await session.flush()
        identities = {
            item.source_customer_id: item
            for item in (
                await session.scalars(
                    select(CustomerSourceIdentity).where(
                        CustomerSourceIdentity.company_id == args.company_id,
                        CustomerSourceIdentity.source_system == SOURCE_SYSTEM,
                        CustomerSourceIdentity.source_customer_id.in_(records),
                    )
                )
            ).all()
        }
        for source_id, record in sorted(records.items()):
            identity = identities.get(source_id)
            if identity is None:
                customer = await service.stage_migrated_customer(
                    session,
                    context=context,
                    customer_data=record.customer,
                    contact_data=record.contact,
                    service_location_data=(
                        record.service_locations[0]
                        if record.service_locations
                        else None
                    ),
                    billing_address_data=record.billing_address,
                )
                identity = CustomerSourceIdentity(
                    company_id=args.company_id,
                    branch_id=args.branch_id,
                    customer_id=customer.id,
                    source_system=SOURCE_SYSTEM,
                    source_customer_id=source_id,
                    first_run_id=run.id,
                )
                session.add(identity)
                await session.flush()
                remaining = record.service_locations[1:]
                for location in remaining:
                    await service.stage_migrated_service_location(
                        session,
                        context=context,
                        customer_id=customer.id,
                        data=location,
                    )
                counts["new_customers"] += 1
                counts["locations_added"] += len(record.service_locations)
                continue
            customer = await session.get(Customer, identity.customer_id)
            if customer is None or customer.company_id != args.company_id:
                counts["quarantined"] += 1
                continue
            tenant_defect = customer.display_name.strip().lower() == (
                "all county plumbing and leak"
            ) and record.customer.display_name.strip().lower() != (
                "all county plumbing and leak"
            )
            if await _native_change_after_binding(session, identity) and not tenant_defect:
                counts["quarantined"] += 1
                session.add(
                    CustomerMigrationException(
                        run_id=run.id,
                        row_number=record.row_number,
                        entity_type="customer",
                        source_id_sha256=hashlib.sha256(source_id.encode()).hexdigest(),
                        disposition="unresolved",
                        reason_code="newer_native_change_review_required",
                        detail="Exact provider binding preserved; native change requires review.",
                    )
                )
                continue
            changed = False
            values = {
                "display_name": record.customer.display_name,
                "normalized_name": normalize_search_text(record.customer.display_name),
                "legal_name": record.customer.legal_name,
                "customer_type": record.customer.customer_type.value,
                "status": record.customer.status.value,
                "marketing_source": record.customer.marketing_source,
                "notes": record.customer.notes,
                "first_name": record.contact.first_name if record.contact else None,
                "last_name": record.contact.last_name if record.contact else None,
                "business_name": record.customer.legal_name,
                "primary_phone": (
                    record.contact.mobile_phone if record.contact else None
                ),
                "email": (
                    normalize_email(record.contact.email)
                    if record.contact and record.contact.email
                    else None
                ),
            }
            for field, value in values.items():
                changed |= _changed(customer, field, value)
            changed |= await _apply_contact(session, customer, record)
            added, duplicate_locations = await _apply_locations(
                session,
                context=context,
                customer=customer,
                record=record,
                service=service,
            )
            counts["locations_added"] += added
            counts["duplicate_locations_prevented"] += duplicate_locations
            counts["updated_customers" if changed or added else "replayed_customers"] += 1
        counts["canonical"] = report.accepted - counts["quarantined"]
        counts["duplicates"] = report.duplicate
        counts["unexplained"] = report.source - (
            counts["canonical"] + counts["quarantined"] + counts["duplicates"]
        )
        run.accepted_count = counts["canonical"]
        run.rejected_count = report.rejected
        run.duplicate_count = report.duplicate
        run.unresolved_count = counts["quarantined"]
        run.status = "completed"
        run.completed_at = utc_now()
    return {
        "contract": CONTRACT,
        "source_sha256": digest,
        "transformation_sha256": report.transformation_sha256,
        "source_rows": report.source,
        "counts": dict(sorted(counts.items())),
        "child_exceptions": len(report.child_exceptions),
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--source", type=Path, required=True)
    value.add_argument("--sha256", required=True)
    value.add_argument("--company-id", type=UUID, required=True)
    value.add_argument("--branch-id", type=UUID, required=True)
    value.add_argument("--actor-id", type=UUID, required=True)
    return value


async def main_async() -> None:
    try:
        print(json.dumps(await apply(parser().parse_args()), sort_keys=True))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main_async())
