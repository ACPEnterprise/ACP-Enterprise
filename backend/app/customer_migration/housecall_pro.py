import csv
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
from app.customers.schemas import (
    ContactCreate,
    CustomerCreate,
    CustomerStatus,
    CustomerType,
    ServiceLocationCreate,
)
from app.customers.service import CustomerService
from app.platform.permissions.authorization import AuthorizationContext

SOURCE_SYSTEM = "housecall_pro"

# This is a deliberately explicit staging contract. Header normalization accepts
# capitalization/spaces, but does not guess how to split a combined address.
SUPPORTED_HEADERS = frozenset(
    {
        "customer_id",
        "display_name",
        "first_name",
        "last_name",
        "role",
        "company",
        "emails",
        "mobile_number",
        "home_number",
        "work_number",
        "lead_source",
        "customer_notes",
        "type",
        "service_address",
        "service_address_line_2",
        "service_city",
        "service_state",
        "service_postal_code",
        "service_country",
        "service_address_notes",
        "billing_address",
        "billing_address_line_2",
        "billing_city",
        "billing_state",
        "billing_postal_code",
        "billing_country",
        "billing_address_notes",
    }
)


def normalized_header(value: str) -> str:
    return "_".join(value.strip().lower().replace("/", " ").split())


@dataclass(frozen=True)
class MigrationReport:
    run_id: str
    mode: str
    source: int
    accepted: int
    rejected: int
    duplicate: int
    unresolved: int

    def as_dict(self) -> dict[str, str | int]:
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "source": self.source,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "duplicate": self.duplicate,
            "unresolved": self.unresolved,
        }


@dataclass(frozen=True)
class ParsedCustomer:
    source_id: str
    customer: CustomerCreate
    contact: ContactCreate | None
    service_location: ServiceLocationCreate | None
    billing_address: ServiceLocationCreate | None


class UnresolvedRowError(ValueError):
    pass


def _optional(row: dict[str, str], key: str) -> str | None:
    value = row.get(key, "").strip()
    return value or None


def _address(row: dict[str, str], prefix: str) -> ServiceLocationCreate | None:
    first = _optional(row, f"{prefix}_address")
    components = {
        "city": _optional(row, f"{prefix}_city"),
        "state": _optional(row, f"{prefix}_state"),
        "postal_code": _optional(row, f"{prefix}_postal_code"),
    }
    if not first and not any(components.values()):
        return None
    if not first or not all(components.values()):
        raise UnresolvedRowError(
            f"{prefix}_address requires separate address, city, state, and postal code"
        )
    city = components["city"]
    state = components["state"]
    postal_code = components["postal_code"]
    assert city is not None and state is not None and postal_code is not None
    return ServiceLocationCreate(
        address=first,
        address_line_2=_optional(row, f"{prefix}_address_line_2"),
        city=city,
        state=state,
        postal_code=postal_code,
        country=_optional(row, f"{prefix}_country") or "US",
        property_notes=_optional(row, f"{prefix}_address_notes"),
    )


def parse_customer(row: dict[str, str]) -> ParsedCustomer:
    source_id = _optional(row, "customer_id")
    if source_id is None:
        raise UnresolvedRowError("customer_id is required for safe idempotency")
    if len(source_id) > 191:
        raise ValueError("customer_id exceeds 191 characters")
    first = _optional(row, "first_name")
    last = _optional(row, "last_name")
    company = _optional(row, "company")
    display_candidate = _optional(row, "display_name") or " ".join(
        value for value in (first, last) if value
    )
    display = display_candidate or company
    if display is None:
        raise UnresolvedRowError("display_name, person name, or company is required")
    customer_type = (
        CustomerType.COMMERCIAL
        if (_optional(row, "type") or "").lower() == "business" or company
        else CustomerType.RESIDENTIAL
    )
    emails = [
        value.strip()
        for value in (_optional(row, "emails") or "").split(",")
        if value.strip()
    ]
    if len(emails) > 1:
        raise UnresolvedRowError("multiple emails require explicit contact resolution")
    mobile = _optional(row, "mobile_number") or _optional(row, "home_number")
    office = _optional(row, "work_number")
    contact = None
    if any((first, last, emails, mobile, office)):
        if not first or not last:
            raise UnresolvedRowError(
                "contact first_name and last_name are required; missing names are not fabricated"
            )
        contact = ContactCreate(
            first_name=first,
            last_name=last,
            title=_optional(row, "role"),
            email=emails[0] if emails else None,
            mobile_phone=mobile,
            office_phone=office,
            is_preferred=True,
        )
    return ParsedCustomer(
        source_id=source_id,
        customer=CustomerCreate(
            customer_type=customer_type,
            display_name=display,
            legal_name=company if customer_type == "commercial" else None,
            marketing_source=_optional(row, "lead_source"),
            notes=_optional(row, "customer_notes"),
            status=CustomerStatus.ACTIVE,
        ),
        contact=contact,
        service_location=_address(row, "service"),
        billing_address=_address(row, "billing"),
    )


class HousecallProCustomerMigration:
    def __init__(self, customer_service: CustomerService | None = None) -> None:
        self.customer_service = customer_service or CustomerService()

    async def _existing_match_count(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        parsed: ParsedCustomer,
    ) -> int:
        contact_signals = []
        if parsed.contact and parsed.contact.email:
            contact_signals.append(
                CustomerContact.normalized_email
                == normalize_email(parsed.contact.email)
            )
        if parsed.contact and parsed.contact.mobile_phone:
            contact_signals.append(
                CustomerContact.normalized_mobile_phone
                == normalize_phone(parsed.contact.mobile_phone)
            )
        location_signal = None
        if parsed.service_location:
            location_signal = (
                ServiceLocation.normalized_address
                == build_normalized_address(
                    parsed.service_location.address,
                    parsed.service_location.address_line_2,
                    parsed.service_location.city,
                    parsed.service_location.state,
                    parsed.service_location.postal_code,
                )
            )
        contact_exists = (
            select(CustomerContact.customer_id).where(or_(*contact_signals))
            if contact_signals
            else None
        )
        filters = [
            Customer.company_id == context.company.id,
            Customer.archived_at.is_(None),
        ]
        identity_filters = [
            Customer.normalized_name
            == normalize_search_text(parsed.customer.display_name)
        ]
        if contact_exists is not None:
            identity_filters.append(Customer.id.in_(contact_exists))
        if location_signal is not None:
            identity_filters.append(
                Customer.id.in_(
                    select(ServiceLocation.customer_id).where(location_signal)
                )
            )
        count = await session.scalar(
            select(func.count())
            .select_from(Customer)
            .where(*filters, or_(*identity_filters))
        )
        return int(count or 0)

    async def run(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        source_path: Path,
        dry_run: bool,
    ) -> MigrationReport:
        if context.active_branch is None:
            raise ValueError("An active Branch is required for migration ownership")
        if not context.can_access_branch(context.active_branch.id):
            raise ValueError("The active Branch is outside the authorized branch scope")
        raw = source_path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            raise ValueError("The source file has no header")
        headers = [normalized_header(value) for value in reader.fieldnames]
        unknown = set(headers) - SUPPORTED_HEADERS
        if unknown:
            raise ValueError(f"Unsupported source columns: {sorted(unknown)}")
        rows = [
            {normalized_header(key): value or "" for key, value in row.items()}
            for row in reader
        ]
        async with factory() as session, session.begin():
            run = CustomerMigrationRun(
                company_id=context.company.id,
                branch_id=context.active_branch.id,
                initiated_by_user_id=context.user.id,
                source_system=SOURCE_SYSTEM,
                source_sha256=digest,
                mode="dry_run" if dry_run else "import",
                status="running",
            )
            session.add(run)
            await session.flush()
            run_id = run.id

        counts = {"accepted": 0, "rejected": 0, "duplicate": 0, "unresolved": 0}
        seen_source_ids: set[str] = set()
        for row_number, row in enumerate(rows, start=2):
            disposition: str | None = None
            reason = ""
            detail = ""
            parsed: ParsedCustomer | None = None
            source_hash: str | None = None
            try:
                parsed = parse_customer(row)
            except UnresolvedRowError as error:
                disposition, reason, detail = (
                    "unresolved",
                    "identity_unresolved",
                    str(error),
                )
            except (ValidationError, ValueError) as error:
                disposition, reason, detail = (
                    "rejected",
                    "validation_failed",
                    str(error),
                )

            if parsed is not None:
                source_hash = hashlib.sha256(parsed.source_id.encode()).hexdigest()
                if parsed.source_id in seen_source_ids:
                    disposition, reason, detail = (
                        "duplicate",
                        "duplicate_source_id_in_file",
                        "The source identifier occurs more than once in this file.",
                    )
                else:
                    seen_source_ids.add(parsed.source_id)
                    async with factory() as session:
                        identity = await session.scalar(
                            select(CustomerSourceIdentity).where(
                                CustomerSourceIdentity.company_id == context.company.id,
                                CustomerSourceIdentity.source_system == SOURCE_SYSTEM,
                                CustomerSourceIdentity.source_customer_id
                                == parsed.source_id,
                            )
                        )
                        match_count = await self._existing_match_count(
                            session, context=context, parsed=parsed
                        )
                    if identity is not None:
                        disposition, reason, detail = (
                            "duplicate",
                            "source_identity_exists",
                            "This source customer was already migrated.",
                        )
                    elif match_count:
                        disposition, reason, detail = (
                            "unresolved",
                            "existing_customer_match",
                            f"{match_count} existing tenant customer(s) match identity signals; no automatic merge performed.",
                        )
                    elif dry_run:
                        counts["accepted"] += 1
                    else:
                        async with factory() as session, session.begin():
                            customer = (
                                await self.customer_service.stage_migrated_customer(
                                    session,
                                    context=context,
                                    customer_data=parsed.customer,
                                    contact_data=parsed.contact,
                                    service_location_data=parsed.service_location,
                                    billing_address_data=parsed.billing_address,
                                )
                            )
                            session.add(
                                CustomerSourceIdentity(
                                    company_id=context.company.id,
                                    branch_id=context.active_branch.id,
                                    customer_id=customer.id,
                                    source_system=SOURCE_SYSTEM,
                                    source_customer_id=parsed.source_id,
                                    first_run_id=run_id,
                                )
                            )
                        counts["accepted"] += 1
            else:
                source_value = _optional(row, "customer_id")
                source_hash = (
                    hashlib.sha256(source_value.encode()).hexdigest()
                    if source_value
                    else None
                )

            if disposition is not None:
                counts[disposition] += 1
                async with factory() as session, session.begin():
                    session.add(
                        CustomerMigrationException(
                            run_id=run_id,
                            row_number=row_number,
                            source_id_sha256=source_hash,
                            disposition=disposition,
                            reason_code=reason,
                            detail=detail,
                        )
                    )

        async with factory() as session, session.begin():
            completed_run = await session.get(
                CustomerMigrationRun, run_id, with_for_update=True
            )
            if completed_run is None:
                raise RuntimeError("Migration run disappeared")
            completed_run.source_count = len(rows)
            completed_run.accepted_count = counts["accepted"]
            completed_run.rejected_count = counts["rejected"]
            completed_run.duplicate_count = counts["duplicate"]
            completed_run.unresolved_count = counts["unresolved"]
            completed_run.status = "completed"
            completed_run.completed_at = utc_now()
        return MigrationReport(
            run_id=str(run_id),
            mode="dry_run" if dry_run else "import",
            source=len(rows),
            **counts,
        )
