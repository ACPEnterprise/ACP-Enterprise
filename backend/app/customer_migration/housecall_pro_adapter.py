import csv
import hashlib
import io
import json
import re
from dataclasses import asdict, dataclass
from typing import Literal

from pydantic import ValidationError

from app.customers.schemas import (
    ContactCreate,
    CustomerCreate,
    CustomerStatus,
    CustomerType,
    ServiceLocationCreate,
)

ADDRESS_HEADER = re.compile(
    r"^Address_(?P<group>[1-9]\d*) (?P<field>"
    r"Street Line 1|Street Line 2|City|State|Postal Code|Billing\?|Notes)$"
)
ADDRESS_FIELDS = frozenset(
    {
        "Street Line 1",
        "Street Line 2",
        "City",
        "State",
        "Postal Code",
        "Billing?",
        "Notes",
    }
)
REQUIRED_ADDRESS_FIELDS = frozenset({"Street Line 1", "City", "State", "Postal Code"})

LEGACY_SCALAR_HEADERS = frozenset(
    {
        "First Name",
        "Last Name",
        "Display Name",
        "Mobile Number",
        "Home Number",
        "Email",
        "Additional Emails",
        "Company",
        "Job Title",
        "Work Number",
        "Tags",
        "Notes",
        "ID",
        "Customer Type",
        "Customer notifications enabled",
        "Customer is Contractor",
        "Lead Source",
    }
)
EXTENDED_SCALAR_HEADERS = frozenset(
    {
        "First Name",
        "Last Name",
        "Display Name",
        "Mobile Number",
        "Home Number",
        "Email",
        "Additional Emails",
        "Company",
        "Role",
        "Work Number",
        "Bills to",
        "Accepts bills from",
        "Tags",
        "Notes",
        "ID",
        "Customer Type",
        "Customer notifications enabled",
        "Customer is Contractor",
        "Lead Source",
        "Customer created at",
        "Email marketing consent",
        "SMS marketing consent",
        "Last service date",
        "Lifetime value",
    }
)
PHONE_2B_SCALAR_HEADERS = EXTENDED_SCALAR_HEADERS - {
    "Email marketing consent",
    "SMS marketing consent",
} | {"Do Not Service"}
MAPPED_SCALAR_HEADERS = frozenset(
    {
        "First Name",
        "Last Name",
        "Display Name",
        "Mobile Number",
        "Home Number",
        "Email",
        "Company",
        "Job Title",
        "Role",
        "Work Number",
        "Notes",
        "ID",
        "Customer Type",
        "Lead Source",
    }
)

Disposition = Literal["rejected", "duplicate"]


@dataclass(frozen=True)
class CustomerExportSchemaContract:
    version: str
    scalar_headers: frozenset[str]
    address_group_count: int
    order_independent_header_sha256: str

    @property
    def headers(self) -> frozenset[str]:
        repeated = {
            f"Address_{group} {field}"
            for group in range(1, self.address_group_count + 1)
            for field in ADDRESS_FIELDS
        }
        return self.scalar_headers | repeated


HOUSECALL_PRO_CUSTOMER_EXPORT_CONTRACTS = (
    CustomerExportSchemaContract(
        version="housecall_pro_customer_444_v1",
        scalar_headers=LEGACY_SCALAR_HEADERS,
        address_group_count=61,
        order_independent_header_sha256=(
            "cb594618aff13df48c8e8307d432c73feda66dd1d080b75a2e09fb3143917665"
        ),
    ),
    CustomerExportSchemaContract(
        version="housecall_pro_customer_451_v1",
        scalar_headers=EXTENDED_SCALAR_HEADERS,
        address_group_count=61,
        order_independent_header_sha256=(
            "4ee5c82b18e7673392ae612ce2f380af6ee24e3e1b384093355659e77e82c9f5"
        ),
    ),
    CustomerExportSchemaContract(
        version="housecall_pro_customer_450_v1",
        scalar_headers=PHONE_2B_SCALAR_HEADERS,
        address_group_count=61,
        order_independent_header_sha256=(
            "27ae0928bb107dc030455ed4da841ab0104047e9cc2f47c4742d88af027d919d"
        ),
    ),
)


@dataclass(frozen=True)
class IncompleteAddressGroupEvidence:
    address_group_number: int
    source_group_sha256: str
    source_fields: dict[str, str]


@dataclass(frozen=True)
class CustomerChildTransformationException:
    source_id_sha256: str
    contract_version: str
    address_group_number: int
    missing_fields: tuple[str, ...]
    reason_code: str
    evidence_sha256: str


@dataclass(frozen=True)
class AdaptedCustomerRecord:
    row_number: int
    source_id: str
    schema_version: str
    customer: CustomerCreate
    contact: ContactCreate | None
    service_locations: tuple[ServiceLocationCreate, ...]
    billing_address: ServiceLocationCreate | None
    unmapped_fields: dict[str, str]
    incomplete_address_groups: tuple[IncompleteAddressGroupEvidence, ...]
    source_row_sha256: str


@dataclass(frozen=True)
class CustomerTransformationRejection:
    row_number: int | None
    disposition: Disposition
    code: str
    fields: tuple[str, ...] = ()
    source_id_sha256: str | None = None
    source_row_sha256: str | None = None


@dataclass(frozen=True)
class CustomerTransformationReport:
    schema_version: str | None
    source_sha256: str
    transformation_sha256: str
    source: int
    accepted: int
    rejected: int
    duplicate: int
    records: tuple[AdaptedCustomerRecord, ...]
    rejections: tuple[CustomerTransformationRejection, ...]
    child_exceptions: tuple[CustomerChildTransformationException, ...]


class CustomerAdapterValidationError(ValueError):
    def __init__(self, code: str, *, fields: tuple[str, ...] = ()) -> None:
        super().__init__(code)
        self.code = code
        self.fields = tuple(sorted(set(fields)))


def _header_sha256(headers: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(headers)).encode()).hexdigest()


def _address_groups(headers: list[str]) -> dict[int, frozenset[str]]:
    groups: dict[int, set[str]] = {}
    for header in headers:
        match = ADDRESS_HEADER.fullmatch(header)
        if match is None:
            continue
        groups.setdefault(int(match.group("group")), set()).add(match.group("field"))
    return {group: frozenset(fields) for group, fields in groups.items()}


def detect_customer_export_contract(
    headers: list[str],
) -> CustomerExportSchemaContract | None:
    if len(headers) != len(set(headers)):
        return None
    groups = _address_groups(headers)
    if not groups or any(fields != ADDRESS_FIELDS for fields in groups.values()):
        return None
    if set(groups) != set(range(1, max(groups) + 1)):
        return None
    scalar_headers = frozenset(
        header for header in headers if ADDRESS_HEADER.fullmatch(header) is None
    )
    signature = _header_sha256(headers)
    for contract in HOUSECALL_PRO_CUSTOMER_EXPORT_CONTRACTS:
        if (
            contract.scalar_headers == scalar_headers
            and contract.address_group_count == len(groups)
            and contract.order_independent_header_sha256 == signature
        ):
            return contract
    return None


def _optional(row: dict[str, str], field: str) -> str | None:
    value = row.get(field, "").strip()
    return value or None


def _required(row: dict[str, str], field: str) -> str:
    value = _optional(row, field)
    if value is None:
        raise CustomerAdapterValidationError("missing_required_field", fields=(field,))
    return value


def _customer_type(value: str) -> CustomerType:
    normalized = value.strip().lower()
    if normalized == "homeowner":
        return CustomerType.RESIDENTIAL
    if normalized == "business":
        return CustomerType.COMMERCIAL
    raise CustomerAdapterValidationError(
        "unsupported_customer_type", fields=("Customer Type",)
    )


def _billing_flag(value: str | None, field: str) -> bool:
    normalized = (value or "").strip().lower()
    if normalized in {"", "false"}:
        return False
    if normalized == "true":
        return True
    raise CustomerAdapterValidationError("unsupported_billing_flag", fields=(field,))


class HousecallProCustomerExportAdapter:
    """Transform known Customer exports without depending on column positions."""

    def __init__(self) -> None:
        self.default_country = "US"
        self.default_status = CustomerStatus.ACTIVE

    def _address_records(
        self,
        row: dict[str, str],
        contract: CustomerExportSchemaContract,
        *,
        source_id_sha256: str,
    ) -> tuple[
        tuple[ServiceLocationCreate, ...],
        ServiceLocationCreate | None,
        tuple[IncompleteAddressGroupEvidence, ...],
        tuple[CustomerChildTransformationException, ...],
    ]:
        services: list[ServiceLocationCreate] = []
        billing: ServiceLocationCreate | None = None
        evidence: list[IncompleteAddressGroupEvidence] = []
        child_exceptions: list[CustomerChildTransformationException] = []
        for group in range(1, contract.address_group_count + 1):
            prefix = f"Address_{group}"
            values = {
                field: _optional(row, f"{prefix} {field}") for field in ADDRESS_FIELDS
            }
            if not any(values.values()):
                continue
            missing = tuple(
                sorted(
                    f"{prefix} {field}"
                    for field in REQUIRED_ADDRESS_FIELDS
                    if values[field] is None
                )
            )
            if missing:
                source_fields = {
                    f"{prefix} {field}": value
                    for field, value in sorted(values.items())
                    if value is not None
                }
                evidence_sha256 = hashlib.sha256(
                    json.dumps(source_fields, sort_keys=True).encode()
                ).hexdigest()
                evidence.append(
                    IncompleteAddressGroupEvidence(
                        address_group_number=group,
                        source_group_sha256=evidence_sha256,
                        source_fields=source_fields,
                    )
                )
                child_exceptions.append(
                    CustomerChildTransformationException(
                        source_id_sha256=source_id_sha256,
                        contract_version=contract.version,
                        address_group_number=group,
                        missing_fields=missing,
                        reason_code="incomplete_address_group",
                        evidence_sha256=evidence_sha256,
                    )
                )
                continue
            address = ServiceLocationCreate(
                address=values["Street Line 1"] or "",
                address_line_2=values["Street Line 2"],
                city=values["City"] or "",
                state=values["State"] or "",
                postal_code=values["Postal Code"] or "",
                country=self.default_country,
                property_notes=values["Notes"],
            )
            if _billing_flag(values["Billing?"], f"{prefix} Billing?"):
                if billing is not None:
                    raise CustomerAdapterValidationError(
                        "multiple_billing_addresses",
                        fields=(f"{prefix} Billing?",),
                    )
                billing = address
            else:
                services.append(address)
        return (
            tuple(services),
            billing,
            tuple(evidence),
            tuple(child_exceptions),
        )

    @staticmethod
    def _contact(
        row: dict[str, str], title_field: str
    ) -> tuple[ContactCreate | None, tuple[str, ...]]:
        first = _optional(row, "First Name")
        last = _optional(row, "Last Name")
        mobile = _optional(row, "Mobile Number") or _optional(row, "Home Number")
        values = (
            first,
            last,
            _optional(row, "Email"),
            mobile,
            _optional(row, "Work Number"),
            _optional(row, title_field),
        )
        if not any(values):
            return None, ()
        if first is None or last is None:
            return None, tuple(
                field
                for field, value in (("First Name", first), ("Last Name", last))
                if value is None
            )
        return (
            ContactCreate(
                first_name=first,
                last_name=last,
                title=_optional(row, title_field),
                email=_optional(row, "Email"),
                mobile_phone=mobile,
                office_phone=_optional(row, "Work Number"),
                is_preferred=True,
            ),
            (),
        )

    def _adapt(
        self,
        row: dict[str, str],
        contract: CustomerExportSchemaContract,
        *,
        row_number: int,
    ) -> tuple[AdaptedCustomerRecord, tuple[CustomerChildTransformationException, ...]]:
        source_id = _required(row, "ID")
        source_id_sha256 = hashlib.sha256(source_id.encode()).hexdigest()
        customer_type = _customer_type(_required(row, "Customer Type"))
        first = _optional(row, "First Name")
        last = _optional(row, "Last Name")
        company = _optional(row, "Company")
        display: str | None = _optional(row, "Display Name") or " ".join(
            value for value in (first, last) if value
        )
        display = display or company
        if display is None:
            raise CustomerAdapterValidationError(
                "customer_name_unresolved",
                fields=("Display Name", "First Name", "Last Name", "Company"),
            )
        title_field = "Role" if "Role" in contract.scalar_headers else "Job Title"
        services, billing, incomplete_groups, child_exceptions = self._address_records(
            row,
            contract,
            source_id_sha256=source_id_sha256,
        )
        used_headers = MAPPED_SCALAR_HEADERS & contract.scalar_headers
        unmapped = {
            header: row[header]
            for header in sorted(contract.scalar_headers - used_headers)
            if row.get(header, "").strip()
        }
        home = _optional(row, "Home Number")
        mobile = _optional(row, "Mobile Number")
        if home and mobile:
            unmapped["Home Number"] = row["Home Number"]
        customer = CustomerCreate(
            customer_type=customer_type,
            display_name=display,
            legal_name=company if customer_type == CustomerType.COMMERCIAL else None,
            marketing_source=_optional(row, "Lead Source"),
            notes=_optional(row, "Notes"),
            status=self.default_status,
        )
        contact, missing_contact_fields = self._contact(row, title_field)
        if missing_contact_fields:
            evidence_payload = {
                "source_id_sha256": source_id_sha256,
                "child_entity_type": "contact",
                "missing_fields": missing_contact_fields,
            }
            child_exceptions = (
                *child_exceptions,
                CustomerChildTransformationException(
                    source_id_sha256=source_id_sha256,
                    contract_version=contract.version,
                    address_group_number=0,
                    missing_fields=missing_contact_fields,
                    reason_code="contact_name_unresolved",
                    evidence_sha256=hashlib.sha256(
                        json.dumps(evidence_payload, sort_keys=True).encode()
                    ).hexdigest(),
                ),
            )
        row_payload = json.dumps(row, sort_keys=True).encode()
        return AdaptedCustomerRecord(
            row_number=row_number,
            source_id=source_id,
            schema_version=contract.version,
            customer=customer,
            contact=contact,
            service_locations=services,
            billing_address=billing,
            unmapped_fields=unmapped,
            incomplete_address_groups=incomplete_groups,
            source_row_sha256=hashlib.sha256(row_payload).hexdigest(),
        ), child_exceptions

    @staticmethod
    def _report(
        *,
        schema_version: str | None,
        source_sha256: str,
        source: int,
        records: list[AdaptedCustomerRecord],
        rejections: list[CustomerTransformationRejection],
        child_exceptions: list[CustomerChildTransformationException] | None = None,
    ) -> CustomerTransformationReport:
        child_exception_items = child_exceptions or []
        payload = {
            "schema_version": schema_version,
            "source_sha256": source_sha256,
            "records": [asdict(record) for record in records],
            "rejections": [asdict(rejection) for rejection in rejections],
            "child_exceptions": [
                asdict(exception) for exception in child_exception_items
            ],
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()
        return CustomerTransformationReport(
            schema_version=schema_version,
            source_sha256=source_sha256,
            transformation_sha256=digest,
            source=source,
            accepted=len(records),
            rejected=sum(item.disposition == "rejected" for item in rejections),
            duplicate=sum(item.disposition == "duplicate" for item in rejections),
            records=tuple(records),
            rejections=tuple(rejections),
            child_exceptions=tuple(child_exception_items),
        )

    def transform(
        self,
        source_bytes: bytes,
        *,
        expected_source_sha256: str,
    ) -> CustomerTransformationReport:
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        if source_sha256 != expected_source_sha256:
            return self._report(
                schema_version=None,
                source_sha256=source_sha256,
                source=0,
                records=[],
                rejections=[
                    CustomerTransformationRejection(
                        row_number=None,
                        disposition="rejected",
                        code="source_checksum_mismatch",
                    )
                ],
            )
        try:
            text = source_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            return self._report(
                schema_version=None,
                source_sha256=source_sha256,
                source=0,
                records=[],
                rejections=[
                    CustomerTransformationRejection(
                        row_number=None,
                        disposition="rejected",
                        code="unsupported_encoding",
                    )
                ],
            )
        reader = csv.DictReader(io.StringIO(text))
        headers = list(reader.fieldnames or [])
        contract = detect_customer_export_contract(headers)
        if contract is None:
            return self._report(
                schema_version=None,
                source_sha256=source_sha256,
                source=0,
                records=[],
                rejections=[
                    CustomerTransformationRejection(
                        row_number=None,
                        disposition="rejected",
                        code="unsupported_customer_export_schema",
                    )
                ],
            )
        rows = [{key: value or "" for key, value in row.items()} for row in reader]
        records: list[AdaptedCustomerRecord] = []
        rejections: list[CustomerTransformationRejection] = []
        child_exceptions: list[CustomerChildTransformationException] = []
        seen: set[str] = set()
        for row_number, row in enumerate(rows, start=2):
            source_row_sha256 = hashlib.sha256(
                json.dumps(row, sort_keys=True).encode()
            ).hexdigest()
            source_id = _optional(row, "ID")
            source_hash = (
                hashlib.sha256(source_id.encode()).hexdigest()
                if source_id is not None
                else None
            )
            try:
                record, record_child_exceptions = self._adapt(
                    row, contract, row_number=row_number
                )
            except CustomerAdapterValidationError as error:
                rejections.append(
                    CustomerTransformationRejection(
                        row_number=row_number,
                        disposition="rejected",
                        code=error.code,
                        fields=error.fields,
                        source_id_sha256=source_hash,
                        source_row_sha256=source_row_sha256,
                    )
                )
                continue
            except (ValidationError, ValueError):
                rejections.append(
                    CustomerTransformationRejection(
                        row_number=row_number,
                        disposition="rejected",
                        code="domain_validation_failed",
                        source_id_sha256=source_hash,
                        source_row_sha256=source_row_sha256,
                    )
                )
                continue
            if record.source_id in seen:
                rejections.append(
                    CustomerTransformationRejection(
                        row_number=row_number,
                        disposition="duplicate",
                        code="duplicate_source_identity",
                        source_id_sha256=source_hash,
                        source_row_sha256=source_row_sha256,
                    )
                )
                continue
            seen.add(record.source_id)
            records.append(record)
            child_exceptions.extend(record_child_exceptions)
        return self._report(
            schema_version=contract.version,
            source_sha256=source_sha256,
            source=len(rows),
            records=records,
            rejections=rejections,
            child_exceptions=child_exceptions,
        )
