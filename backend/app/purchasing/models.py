from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OperationalVendor(Base):
    __tablename__ = "purchasing_operational_vendors"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','inactive','archived')",
            name="ck_purchasing_vendors_status",
        ),
        CheckConstraint("version >= 1", name="ck_purchasing_vendors_version"),
        UniqueConstraint("company_id", "code", name="uq_purchasing_vendor_code"),
        UniqueConstraint("company_id", "id", name="uq_purchasing_vendor_company"),
        Index("ix_purchasing_vendor_search", "company_id", "status", "display_name"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(240))
    contact_reference: Mapped[str | None] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    provenance_type: Mapped[str] = mapped_column(
        String(40), nullable=False, default="native"
    )
    provenance_reference: Mapped[str | None] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class PurchaseOrder(Base):
    __tablename__ = "purchasing_purchase_orders"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_purchasing_po_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "vendor_id"],
            [
                "purchasing_operational_vendors.company_id",
                "purchasing_operational_vendors.id",
            ],
            name="fk_purchasing_po_vendor",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('draft','submitted','approved','issued','cancelled','closed')",
            name="ck_purchasing_po_status",
        ),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_purchasing_po_currency"),
        CheckConstraint("version >= 1", name="ck_purchasing_po_version"),
        UniqueConstraint("company_id", "po_number", name="uq_purchasing_po_number"),
        UniqueConstraint("company_id", "id", name="uq_purchasing_po_company"),
        Index(
            "ix_purchasing_po_list", "company_id", "branch_id", "status", "created_at"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    vendor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    po_number: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    expected_date: Mapped[date | None] = mapped_column(Date)
    prepared_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    submitted_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issued_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lifecycle_reason: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class PurchaseOrderLine(Base):
    __tablename__ = "purchasing_purchase_order_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "purchase_order_id"],
            ["purchasing_purchase_orders.company_id", "purchasing_purchase_orders.id"],
            name="fk_purchasing_line_po",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "inventory_item_id"],
            ["inventory_items.company_id", "inventory_items.id"],
            name="fk_purchasing_line_inventory_item",
            ondelete="RESTRICT",
        ),
        CheckConstraint("quantity > 0", name="ck_purchasing_line_quantity"),
        CheckConstraint("unit_cost >= 0", name="ck_purchasing_line_unit_cost"),
        CheckConstraint(
            "extended_cost = quantity * unit_cost", name="ck_purchasing_line_extended"
        ),
        CheckConstraint(
            "inventory_item_id IS NOT NULL OR length(trim(description)) > 0",
            name="ck_purchasing_line_identity",
        ),
        CheckConstraint("version >= 1", name="ck_purchasing_line_version"),
        UniqueConstraint(
            "company_id",
            "purchase_order_id",
            "line_number",
            name="uq_purchasing_line_number",
        ),
        UniqueConstraint("company_id", "id", name="uq_purchasing_line_company"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    purchase_order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    inventory_item_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    extended_cost: Mapped[Decimal] = mapped_column(Numeric(22, 4), nullable=False)
    expected_date: Mapped[date | None] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class PurchaseOrderIssuanceEvidence(Base):
    __tablename__ = "purchasing_po_issuance_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "purchase_order_id"],
            ["purchasing_purchase_orders.company_id", "purchasing_purchase_orders.id"],
            name="fk_purchasing_evidence_po",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id", "purchase_order_id", name="uq_purchasing_evidence_po"
        ),
        UniqueConstraint("company_id", "digest", name="uq_purchasing_evidence_digest"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    purchase_order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    purchase_order_version: Mapped[int] = mapped_column(Integer, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    issued_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PurchasingCommandReceipt(Base):
    __tablename__ = "purchasing_command_receipts"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_purchasing_command_key"
        ),
        CheckConstraint(
            "length(payload_digest) = 64", name="ck_purchasing_command_digest"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    result_type: Mapped[str] = mapped_column(String(40), nullable=False)
    result_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
