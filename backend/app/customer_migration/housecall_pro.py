from dataclasses import dataclass

from app.customers.schemas import (
    ContactCreate,
    CustomerCreate,
    CustomerStatus,
    CustomerType,
    ServiceLocationCreate,
)

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


class LegacyCustomerImportRetiredError(RuntimeError):
    pass


class HousecallProCustomerMigration:
    """Retired legacy orchestrator; reviewed imports use CustomerImportFacade."""

    async def run(self, *args: object, **kwargs: object) -> MigrationReport:
        raise LegacyCustomerImportRetiredError(
            "legacy Customer orchestration is retired; use customer_import_facade"
        )
