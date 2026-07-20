from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.platform.company.models import Company


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CustomerNumberSequence(Base):
    __tablename__ = "customer_number_sequences"
    __table_args__ = (
        CheckConstraint(
            "last_value >= 0", name="ck_customer_number_sequences_last_value"
        ),
    )

    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "companies.id",
            name="fk_customer_number_sequences_company_id_companies",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    )
    last_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint(
            "customer_type IN ('residential', 'commercial', 'municipal', 'hoa', "
            "'property_management')",
            name="ck_customers_customer_type",
        ),
        CheckConstraint(
            "status IN ('prospect', 'active', 'inactive')",
            name="ck_customers_status",
        ),
        CheckConstraint(
            "preferred_contact_method IN ('phone', 'sms', 'email')",
            name="ck_customers_preferred_contact_method",
        ),
        CheckConstraint(
            "customer_number ~ '^CUS-[0-9]{6,}$'",
            name="ck_customers_customer_number_format",
        ),
        CheckConstraint(
            "length(btrim(display_name)) > 0",
            name="ck_customers_display_name_not_blank",
        ),
        UniqueConstraint(
            "company_id",
            "customer_number",
            name="uq_customers_company_id_customer_number",
        ),
        Index("ix_customers_company_id_status", "company_id", "status"),
        Index("ix_customers_company_id_display_name", "company_id", "display_name"),
        Index(
            "ix_customers_customer_number_trgm",
            "customer_number",
            postgresql_using="gin",
            postgresql_ops={"customer_number": "gin_trgm_ops"},
        ),
        Index(
            "ix_customers_display_name_trgm",
            "display_name",
            postgresql_using="gin",
            postgresql_ops={"display_name": "gin_trgm_ops"},
        ),
        Index(
            "ix_customers_legal_name_trgm",
            "legal_name",
            postgresql_using="gin",
            postgresql_ops={"legal_name": "gin_trgm_ops"},
        ),
        Index(
            "ix_customers_active_updated",
            "company_id",
            "updated_at",
            "id",
            postgresql_where=text("archived_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "companies.id",
            name="fk_customers_company_id_companies",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    customer_number: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="prospect")
    customer_type: Mapped[str] = mapped_column(String(30), nullable=False)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(300))
    primary_contact_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "customer_contacts.id",
            name="fk_customers_primary_contact_id_customer_contacts",
            ondelete="RESTRICT",
            use_alter=True,
        ),
    )
    preferred_contact_method: Mapped[str] = mapped_column(
        String(20), nullable=False, default="phone"
    )
    marketing_source: Mapped[str | None] = mapped_column("source", String(100))
    tax_exempt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column("internal_notes", Text)

    # Forward-compatible legacy identity/search fields retained for migrated data.
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    business_name: Mapped[str | None] = mapped_column(String(200))
    normalized_name: Mapped[str] = mapped_column(String(300), nullable=False)
    primary_phone: Mapped[str | None] = mapped_column(String(30))
    normalized_primary_phone: Mapped[str | None] = mapped_column(String(20))
    secondary_phone: Mapped[str | None] = mapped_column(String(30))
    normalized_secondary_phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(320))
    normalized_email: Mapped[str | None] = mapped_column(String(320))
    is_vip: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    company: Mapped["Company"] = relationship(foreign_keys=[company_id])
    contacts: Mapped[list["CustomerContact"]] = relationship(
        back_populates="customer",
        foreign_keys="CustomerContact.customer_id",
        passive_deletes=True,
    )
    primary_contact: Mapped["CustomerContact | None"] = relationship(
        foreign_keys=[primary_contact_id],
        post_update=True,
    )
    locations: Mapped[list["ServiceLocation"]] = relationship(
        back_populates="customer", passive_deletes=True
    )
    notes_history: Mapped[list["CustomerNote"]] = relationship(
        back_populates="customer", passive_deletes=True
    )


class CustomerContact(Base):
    __tablename__ = "customer_contacts"
    __table_args__ = (
        UniqueConstraint(
            "id", "customer_id", name="uq_customer_contacts_id_customer_id"
        ),
        Index("ix_customer_contacts_customer_id_active", "customer_id", "active"),
        Index("ix_customer_contacts_normalized_email", "normalized_email"),
        Index("ix_customer_contacts_normalized_mobile_phone", "normalized_phone"),
        Index(
            "ix_customer_contacts_normalized_office_phone", "normalized_office_phone"
        ),
        Index(
            "ix_customer_contacts_first_name_trgm",
            "first_name",
            postgresql_using="gin",
            postgresql_ops={"first_name": "gin_trgm_ops"},
        ),
        Index(
            "ix_customer_contacts_last_name_trgm",
            "last_name",
            postgresql_using="gin",
            postgresql_ops={"last_name": "gin_trgm_ops"},
        ),
        Index(
            "ix_customer_contacts_normalized_email_trgm",
            "normalized_email",
            postgresql_using="gin",
            postgresql_ops={"normalized_email": "gin_trgm_ops"},
        ),
        Index(
            "ix_customer_contacts_normalized_phone_trgm",
            "normalized_phone",
            postgresql_using="gin",
            postgresql_ops={"normalized_phone": "gin_trgm_ops"},
        ),
        Index(
            "ix_customer_contacts_normalized_office_phone_trgm",
            "normalized_office_phone",
            postgresql_using="gin",
            postgresql_ops={"normalized_office_phone": "gin_trgm_ops"},
        ),
        Index(
            "uq_customer_contacts_active_preferred",
            "customer_id",
            unique=True,
            postgresql_where=text("is_preferred AND active AND archived_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "customers.id",
            name="fk_customer_contacts_customer_id_customers",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str | None] = mapped_column(String(150))
    email: Mapped[str | None] = mapped_column(String(320))
    normalized_email: Mapped[str | None] = mapped_column(String(320))
    mobile_phone: Mapped[str | None] = mapped_column("phone", String(30))
    normalized_mobile_phone: Mapped[str | None] = mapped_column(
        "normalized_phone", String(20)
    )
    office_phone: Mapped[str | None] = mapped_column(String(30))
    normalized_office_phone: Mapped[str | None] = mapped_column(String(20))
    is_preferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text)

    # Existing authorization/business metadata retained for forward compatibility.
    relationship_or_role: Mapped[str | None] = mapped_column(String(100))
    can_approve_work: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    customer: Mapped[Customer] = relationship(
        back_populates="contacts", foreign_keys=[customer_id]
    )


class ServiceLocation(Base):
    __tablename__ = "service_locations"
    __table_args__ = (
        CheckConstraint(
            "country = upper(country)", name="ck_service_locations_country_upper"
        ),
        CheckConstraint(
            "gps_latitude IS NULL OR gps_latitude BETWEEN -90 AND 90",
            name="ck_service_locations_latitude",
        ),
        CheckConstraint(
            "gps_longitude IS NULL OR gps_longitude BETWEEN -180 AND 180",
            name="ck_service_locations_longitude",
        ),
        Index("ix_service_locations_customer_id_active", "customer_id", "active"),
        Index("ix_service_locations_normalized_address", "normalized_address"),
        Index(
            "ix_service_locations_address_line_1_trgm",
            "address_line_1",
            postgresql_using="gin",
            postgresql_ops={"address_line_1": "gin_trgm_ops"},
        ),
        Index(
            "ix_service_locations_city_trgm",
            "city",
            postgresql_using="gin",
            postgresql_ops={"city": "gin_trgm_ops"},
        ),
        Index(
            "ix_service_locations_postal_code_trgm",
            "postal_code",
            postgresql_using="gin",
            postgresql_ops={"postal_code": "gin_trgm_ops"},
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "customers.id",
            name="fk_service_locations_customer_id_customers",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    nickname: Mapped[str | None] = mapped_column(String(150))
    address: Mapped[str] = mapped_column("address_line_1", String(200), nullable=False)
    address_line_2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="US")
    gps_latitude: Mapped[float | None] = mapped_column(Numeric(9, 6))
    gps_longitude: Mapped[float | None] = mapped_column(Numeric(10, 6))
    billing_address_override: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    gate_code: Mapped[str | None] = mapped_column(String(200))
    property_notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    normalized_address: Mapped[str] = mapped_column(String(500), nullable=False)

    # Existing plumbing/property metadata retained for later operational modules.
    property_type: Mapped[str | None] = mapped_column(String(30))
    gate_access_instructions: Mapped[str | None] = mapped_column(Text)
    water_shutoff_location: Mapped[str | None] = mapped_column(Text)
    sewer_septic: Mapped[str | None] = mapped_column(String(20))
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    customer: Mapped[Customer] = relationship(back_populates="locations")


class CustomerNote(Base):
    __tablename__ = "customer_notes"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    author_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )

    customer: Mapped[Customer] = relationship(back_populates="notes_history")
