from datetime import datetime
from enum import StrEnum
from math import ceil
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.customers.normalization import normalize_email, normalize_phone, optional_text


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CustomerStatus(StrEnum):
    PROSPECT = "prospect"
    ACTIVE = "active"
    INACTIVE = "inactive"


class CustomerType(StrEnum):
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    MUNICIPAL = "municipal"
    HOA = "hoa"
    PROPERTY_MANAGEMENT = "property_management"


class PreferredContactMethod(StrEnum):
    PHONE = "phone"
    SMS = "sms"
    EMAIL = "email"


class CustomerCreate(StrictSchema):
    customer_type: CustomerType
    display_name: str = Field(min_length=1, max_length=300)
    legal_name: str | None = Field(default=None, max_length=300)
    preferred_contact_method: PreferredContactMethod = PreferredContactMethod.PHONE
    marketing_source: str | None = Field(default=None, max_length=100)
    tax_exempt: bool = False
    notes: str | None = Field(default=None, max_length=10000)
    status: CustomerStatus = CustomerStatus.PROSPECT

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Display name is required.")
        return cleaned

    @field_validator("legal_name", "marketing_source", "notes", mode="before")
    @classmethod
    def clean_optional(cls, value: Any) -> Any:
        return (
            optional_text(value) if isinstance(value, str) or value is None else value
        )


class CustomerUpdate(StrictSchema):
    customer_type: CustomerType | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=300)
    legal_name: str | None = Field(default=None, max_length=300)
    preferred_contact_method: PreferredContactMethod | None = None
    marketing_source: str | None = Field(default=None, max_length=100)
    tax_exempt: bool | None = None
    notes: str | None = Field(default=None, max_length=10000)

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Display name is required.")
        return cleaned

    @field_validator("legal_name", "marketing_source", "notes", mode="before")
    @classmethod
    def clean_optional(cls, value: Any) -> Any:
        return (
            optional_text(value) if isinstance(value, str) or value is None else value
        )


class CustomerUpdateRequest(StrictSchema):
    display_name: str | None = Field(default=None, min_length=1, max_length=300)
    legal_name: str | None = Field(default=None, max_length=300)
    status: CustomerStatus | None = None
    customer_type: CustomerType | None = None
    preferred_contact_method: PreferredContactMethod | None = None
    marketing_source: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=10000)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    business_name: str | None = Field(default=None, max_length=200)
    primary_phone: str | None = Field(default=None, max_length=30)
    secondary_phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=320)
    is_vip: bool | None = None

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Display name is required.")
        return cleaned

    @field_validator(
        "legal_name",
        "marketing_source",
        "notes",
        "first_name",
        "last_name",
        "business_name",
        "primary_phone",
        "secondary_phone",
        "email",
        mode="before",
    )
    @classmethod
    def clean_legal_name(cls, value: Any) -> Any:
        return (
            optional_text(value) if isinstance(value, str) or value is None else value
        )

    @field_validator("email")
    @classmethod
    def validate_update_email(cls, value: str | None) -> str | None:
        return normalize_email(value) if value else None

    @field_validator("primary_phone", "secondary_phone")
    @classmethod
    def validate_update_phone(cls, value: str | None) -> str | None:
        if value:
            normalize_phone(value)
        return value


class CustomerStatusUpdate(StrictSchema):
    status: CustomerStatus


class ContactCreate(StrictSchema):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    title: str | None = Field(default=None, max_length=150)
    email: str | None = Field(default=None, max_length=320)
    mobile_phone: str | None = Field(default=None, max_length=30)
    office_phone: str | None = Field(default=None, max_length=30)
    is_preferred: bool = False
    active: bool = True
    notes: str | None = Field(default=None, max_length=4000)
    relationship_or_role: str | None = Field(default=None, max_length=100)
    can_approve_work: bool = False

    @field_validator("first_name", "last_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Contact names are required.")
        return cleaned

    @field_validator(
        "title",
        "email",
        "mobile_phone",
        "office_phone",
        "notes",
        "relationship_or_role",
        mode="before",
    )
    @classmethod
    def clean_optional(cls, value: Any) -> Any:
        return (
            optional_text(value) if isinstance(value, str) or value is None else value
        )

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        return normalize_email(value) if value else None

    @field_validator("mobile_phone", "office_phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value:
            normalize_phone(value)
        return value

    @model_validator(mode="after")
    def preferred_contact_must_be_active(self) -> "ContactCreate":
        if self.is_preferred and not self.active:
            raise ValueError("A preferred Contact must be active.")
        return self


class ContactUpdate(StrictSchema):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    title: str | None = Field(default=None, max_length=150)
    email: str | None = Field(default=None, max_length=320)
    mobile_phone: str | None = Field(default=None, max_length=30)
    office_phone: str | None = Field(default=None, max_length=30)
    is_preferred: bool | None = None
    active: bool | None = None
    notes: str | None = Field(default=None, max_length=4000)
    relationship_or_role: str | None = Field(default=None, max_length=100)
    can_approve_work: bool | None = None

    @field_validator("first_name", "last_name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Contact names are required.")
        return cleaned

    @field_validator(
        "title",
        "email",
        "mobile_phone",
        "office_phone",
        "notes",
        "relationship_or_role",
        mode="before",
    )
    @classmethod
    def clean_optional(cls, value: Any) -> Any:
        return (
            optional_text(value) if isinstance(value, str) or value is None else value
        )

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        return normalize_email(value) if value else None

    @field_validator("mobile_phone", "office_phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value:
            normalize_phone(value)
        return value

    @model_validator(mode="after")
    def preferred_contact_must_be_active(self) -> "ContactUpdate":
        if self.is_preferred is True and self.active is False:
            raise ValueError("A preferred Contact must be active.")
        return self


class ServiceLocationCreate(StrictSchema):
    nickname: str | None = Field(default=None, max_length=150)
    address: str = Field(min_length=1, max_length=200)
    address_line_2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    postal_code: str = Field(min_length=1, max_length=20)
    country: str = Field(default="US", min_length=2, max_length=2)
    gps_latitude: float | None = Field(default=None, ge=-90, le=90)
    gps_longitude: float | None = Field(default=None, ge=-180, le=180)
    billing_address_override: bool = False
    gate_code: str | None = Field(default=None, max_length=200)
    property_notes: str | None = Field(default=None, max_length=4000)
    active: bool = True
    property_type: str | None = Field(default=None, max_length=30)
    gate_access_instructions: str | None = Field(default=None, max_length=4000)
    water_shutoff_location: str | None = Field(default=None, max_length=4000)
    sewer_septic: str | None = Field(default=None, pattern="^(sewer|septic|unknown)$")
    is_primary: bool = False

    @field_validator("address", "city", "state", "postal_code")
    @classmethod
    def clean_required(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field is required.")
        return cleaned

    @field_validator("country")
    @classmethod
    def normalize_country(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if len(cleaned) != 2 or not cleaned.isalpha():
            raise ValueError("Country must be an ISO two-letter code.")
        return cleaned

    @field_validator(
        "nickname",
        "address_line_2",
        "gate_code",
        "property_notes",
        "property_type",
        "gate_access_instructions",
        "water_shutoff_location",
        "sewer_septic",
        mode="before",
    )
    @classmethod
    def clean_optional(cls, value: Any) -> Any:
        return (
            optional_text(value) if isinstance(value, str) or value is None else value
        )


class ServiceLocationUpdate(StrictSchema):
    nickname: str | None = Field(default=None, max_length=150)
    address: str | None = Field(default=None, min_length=1, max_length=200)
    address_line_2: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    state: str | None = Field(default=None, min_length=1, max_length=100)
    postal_code: str | None = Field(default=None, min_length=1, max_length=20)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    gps_latitude: float | None = Field(default=None, ge=-90, le=90)
    gps_longitude: float | None = Field(default=None, ge=-180, le=180)
    billing_address_override: bool | None = None
    gate_code: str | None = Field(default=None, max_length=200)
    property_notes: str | None = Field(default=None, max_length=4000)
    active: bool | None = None
    property_type: str | None = Field(default=None, max_length=30)
    gate_access_instructions: str | None = Field(default=None, max_length=4000)
    water_shutoff_location: str | None = Field(default=None, max_length=4000)
    sewer_septic: str | None = Field(default=None, pattern="^(sewer|septic|unknown)$")
    is_primary: bool | None = None

    @field_validator("country")
    @classmethod
    def normalize_country(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().upper()
        if len(cleaned) != 2 or not cleaned.isalpha():
            raise ValueError("Country must be an ISO two-letter code.")
        return cleaned


class ContactResponse(ContactCreate):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: UUID
    customer_id: UUID
    created_at: datetime
    updated_at: datetime


class ServiceLocationResponse(ServiceLocationCreate):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: UUID
    customer_id: UUID
    created_at: datetime
    updated_at: datetime


class CustomerResponse(CustomerCreate):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: UUID
    customer_number: str
    company_id: UUID
    primary_contact_id: UUID | None
    created_at: datetime
    updated_at: datetime


class CustomerDetail(CustomerResponse):
    contacts: list[ContactResponse]
    locations: list[ServiceLocationResponse]


class CustomerDetailMetadata(StrictSchema):
    company_id: UUID
    customer_number: str
    status: CustomerStatus
    customer_type: CustomerType
    preferred_contact_method: PreferredContactMethod
    created_at: datetime
    updated_at: datetime


class CustomerDetailResponse(CustomerResponse):
    preferred_contact: ContactResponse | None
    contacts: list[ContactResponse]
    locations: list[ServiceLocationResponse]
    active_service_locations: list[ServiceLocationResponse]
    inactive_service_locations: list[ServiceLocationResponse]
    note_history: list["CustomerNoteResponse"] = Field(default_factory=list)
    metadata: CustomerDetailMetadata


class CustomerLifecycleResponse(StrictSchema):
    customer_id: UUID
    company_id: UUID
    archived: bool
    archived_at: datetime | None
    updated_at: datetime


class CustomerListResponse(StrictSchema):
    items: list[CustomerResponse]
    total: int
    limit: int
    offset: int


class CustomerSortField(StrEnum):
    CUSTOMER_NUMBER = "customer_number"
    DISPLAY_NAME = "display_name"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    STATUS = "status"


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


class CustomerSearchQuery(StrictSchema):
    query: str | None = Field(default=None, min_length=1, max_length=300)
    status: CustomerStatus | None = None
    customer_type: CustomerType | None = None
    has_preferred_contact: bool | None = None
    has_active_service_locations: bool | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    updated_from: datetime | None = None
    updated_to: datetime | None = None
    sort_by: CustomerSortField = CustomerSortField.DISPLAY_NAME
    sort_direction: SortDirection = SortDirection.ASC
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=200)

    @model_validator(mode="after")
    def validate_date_ranges(self) -> "CustomerSearchQuery":
        if (
            self.created_from
            and self.created_to
            and self.created_from > self.created_to
        ):
            raise ValueError("created_from must not be after created_to")
        if (
            self.updated_from
            and self.updated_to
            and self.updated_from > self.updated_to
        ):
            raise ValueError("updated_from must not be after updated_to")
        return self


class CustomerSearchResponse(StrictSchema):
    items: list[CustomerResponse]
    page: int
    page_size: int
    total_count: int
    total_pages: int

    @classmethod
    def build(
        cls,
        *,
        items: list[CustomerResponse],
        page: int,
        page_size: int,
        total_count: int,
    ) -> "CustomerSearchResponse":
        return cls(
            items=items,
            page=page,
            page_size=page_size,
            total_count=total_count,
            total_pages=ceil(total_count / page_size) if total_count else 0,
        )


class TimelineActor(StrictSchema):
    id: UUID
    display_name: str


class TimelineEntity(StrictSchema):
    type: str
    id: UUID | None


class CustomerTimelineEntry(StrictSchema):
    id: UUID
    timestamp: datetime
    event_type: str
    actor: TimelineActor | None
    entity: TimelineEntity
    summary: str
    metadata: dict[str, object]
    branch_id: UUID | None
    company_id: UUID
    customer_id: UUID
    correlation_id: UUID


class CustomerTimelineResponse(StrictSchema):
    items: list[CustomerTimelineEntry]
    page: int
    page_size: int
    total_count: int
    total_pages: int

    @classmethod
    def build(
        cls,
        *,
        items: list[CustomerTimelineEntry],
        page: int,
        page_size: int,
        total_count: int,
    ) -> "CustomerTimelineResponse":
        return cls(
            items=items,
            page=page,
            page_size=page_size,
            total_count=total_count,
            total_pages=ceil(total_count / page_size) if total_count else 0,
        )


class CustomerIntakeCreate(StrictSchema):
    """Launch intake contract translated into the authoritative aggregate."""

    customer_type: str
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    business_name: str | None = Field(default=None, max_length=200)
    primary_phone: str = Field(min_length=1, max_length=30)
    secondary_phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=320)
    preferred_contact_method: PreferredContactMethod = PreferredContactMethod.PHONE
    status: CustomerStatus = CustomerStatus.ACTIVE
    source: str = Field(default="unknown", max_length=100)
    is_vip: bool = False
    internal_notes: str | None = Field(default=None, max_length=10000)

    @field_validator("customer_type")
    @classmethod
    def validate_intake_customer_type(cls, value: str) -> str:
        if value not in {
            "individual",
            "business",
            "residential",
            "commercial",
            "municipal",
            "hoa",
            "property_management",
        }:
            raise ValueError("Unsupported customer type.")
        return value

    @field_validator(
        "first_name",
        "last_name",
        "business_name",
        "secondary_phone",
        "email",
        "internal_notes",
        mode="before",
    )
    @classmethod
    def clean_intake_optional(cls, value: Any) -> Any:
        return (
            optional_text(value) if isinstance(value, str) or value is None else value
        )

    @field_validator("primary_phone")
    @classmethod
    def validate_primary_phone(cls, value: str) -> str:
        cleaned = value.strip()
        normalize_phone(cleaned)
        return cleaned

    @field_validator("email")
    @classmethod
    def normalize_intake_email(cls, value: str | None) -> str | None:
        return normalize_email(value) if value else None

    @model_validator(mode="after")
    def validate_identity(self) -> "CustomerIntakeCreate":
        if self.customer_type in {"individual", "residential"}:
            if not self.first_name or not self.last_name:
                raise ValueError("Individual customers require first and last name.")
        elif not self.business_name:
            raise ValueError("Business customers require a business name.")
        if (
            self.preferred_contact_method is PreferredContactMethod.EMAIL
            and not self.email
        ):
            raise ValueError("Email is required when email is preferred.")
        return self


class DuplicateCheckRequest(StrictSchema):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    business_name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=320)
    address_line_1: str | None = Field(default=None, max_length=200)
    address_line_2: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)


class DuplicateMatchResponse(CustomerResponse):
    reasons: list[str]


class DuplicateCheckResponse(StrictSchema):
    matches: list[DuplicateMatchResponse]


class CustomerIntakeResponse(StrictSchema):
    customer: CustomerDetailResponse
    duplicate_warnings: list[DuplicateMatchResponse]


class CustomerNoteCreate(StrictSchema):
    body: str = Field(min_length=1, max_length=4000)

    @field_validator("body")
    @classmethod
    def clean_body(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Note body is required.")
        return cleaned


class CustomerNoteResponse(StrictSchema):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: UUID
    customer_id: UUID
    author_user_id: UUID | None
    body: str
    created_at: datetime


class ConsentChannel(StrEnum):
    SMS = "sms"
    EMAIL = "email"


class ConsentDecision(StrEnum):
    GRANTED = "granted"
    WITHDRAWN = "withdrawn"


class CustomerConsentCreate(StrictSchema):
    channel: ConsentChannel
    decision: ConsentDecision
    source: str = Field(min_length=1, max_length=100)
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("source", "reason", mode="before")
    @classmethod
    def clean_consent_text(cls, value: Any) -> Any:
        return (
            optional_text(value) if isinstance(value, str) or value is None else value
        )


class CustomerConsentResponse(StrictSchema):
    id: UUID
    customer_id: UUID
    channel: ConsentChannel
    decision: ConsentDecision
    source: str
    reason: str | None
    recorded_at: datetime
    recorded_by_user_id: UUID | None
    branch_id: UUID | None
