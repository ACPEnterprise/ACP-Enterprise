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
    effective_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
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
    is_cancelled: Mapped[bool] = mapped_column(nullable=False, default=False)
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


class PurchaseOrderReceipt(Base):
    __tablename__ = "purchasing_purchase_order_receipts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "purchase_order_id"],
            ["purchasing_purchase_orders.company_id", "purchasing_purchase_orders.id"],
            name="fk_purchasing_receipt_po",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id", "receiving_location_id"],
            [
                "inventory_stock_locations.company_id",
                "inventory_stock_locations.branch_id",
                "inventory_stock_locations.id",
            ],
            name="fk_purchasing_receipt_inventory_location",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id", "receiving_event_identity", name="uq_purchasing_receipt_event"
        ),
        CheckConstraint(
            "inventory_application_state IN ('pending','applied','not_applicable')",
            name="ck_purchasing_receipt_inventory_application_state",
        ),
        UniqueConstraint("company_id", "id", name="uq_purchasing_receipt_company"),
        CheckConstraint(
            "status IN ('recorded','discrepancy_outstanding')",
            name="ck_purchasing_receipt_status",
        ),
        Index(
            "ix_purchasing_receipt_po",
            "company_id",
            "purchase_order_id",
            "received_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    purchase_order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    vendor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    receiving_location_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    inventory_application_state: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending"
    )
    receiving_event_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    receiver_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(240))
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class PurchaseOrderReceiptLine(Base):
    __tablename__ = "purchasing_purchase_order_receipt_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "receipt_id"],
            [
                "purchasing_purchase_order_receipts.company_id",
                "purchasing_purchase_order_receipts.id",
            ],
            name="fk_purchasing_receipt_line_receipt",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "inventory_movement_id"],
            ["inventory_stock_movements.company_id", "inventory_stock_movements.id"],
            name="fk_purchasing_receipt_line_inventory_movement",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "purchase_order_line_id"],
            [
                "purchasing_purchase_order_lines.company_id",
                "purchasing_purchase_order_lines.id",
            ],
            name="fk_purchasing_receipt_line_po_line",
            ondelete="RESTRICT",
        ),
        CheckConstraint("accepted_quantity >= 0", name="ck_receipt_line_accepted"),
        CheckConstraint("rejected_quantity >= 0", name="ck_receipt_line_rejected"),
        CheckConstraint(
            "accepted_quantity + rejected_quantity > 0 OR discrepancy_category IS NOT NULL",
            name="ck_receipt_line_outcome",
        ),
        UniqueConstraint(
            "company_id",
            "receipt_id",
            "purchase_order_line_id",
            name="uq_purchasing_receipt_po_line",
        ),
        UniqueConstraint("company_id", "id", name="uq_purchasing_receipt_line_company"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    receipt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    purchase_order_line_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    ordered_quantity_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False
    )
    accepted_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    rejected_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    cumulative_accepted_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False
    )
    outstanding_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False
    )
    unit_snapshot: Mapped[str] = mapped_column(String(40), nullable=False)
    discrepancy_category: Mapped[str | None] = mapped_column(String(40))
    observed_condition: Mapped[str | None] = mapped_column(Text)
    inventory_movement_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    unit_cost_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    currency_snapshot: Mapped[str | None] = mapped_column(String(3))


class PurchaseOrderDiscrepancy(Base):
    __tablename__ = "purchasing_purchase_order_discrepancies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "receipt_id"],
            [
                "purchasing_purchase_order_receipts.company_id",
                "purchasing_purchase_order_receipts.id",
            ],
            name="fk_purchasing_discrepancy_receipt",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "receipt_line_id"],
            [
                "purchasing_purchase_order_receipt_lines.company_id",
                "purchasing_purchase_order_receipt_lines.id",
            ],
            name="fk_purchasing_discrepancy_receipt_line",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "category IN ('quantity_short','quantity_over','wrong_item','damaged_item','rejected_item','missing_line')",
            name="ck_purchasing_discrepancy_category",
        ),
        CheckConstraint(
            "status IN ('open','resolved_accepted','resolved_rejected')",
            name="ck_purchasing_discrepancy_status",
        ),
        CheckConstraint("version >= 1", name="ck_purchasing_discrepancy_version"),
        UniqueConstraint(
            "company_id", "receipt_line_id", name="uq_purchasing_discrepancy_line"
        ),
        UniqueConstraint("company_id", "id", name="uq_purchasing_discrepancy_company"),
        Index(
            "ix_purchasing_discrepancy_open",
            "company_id",
            "purchase_order_id",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    purchase_order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    purchase_order_line_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    receipt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    receipt_line_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    expected_fact: Mapped[str] = mapped_column(Text, nullable=False)
    actual_fact: Mapped[str] = mapped_column(Text, nullable=False)
    observed_condition: Mapped[str] = mapped_column(Text, nullable=False)
    opened_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class PurchaseReturn(Base):
    __tablename__ = "purchasing_purchase_returns"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "receipt_id"],
            [
                "purchasing_purchase_order_receipts.company_id",
                "purchasing_purchase_order_receipts.id",
            ],
            name="fk_purchase_return_receipt",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "inventory_movement_id"],
            ["inventory_stock_movements.company_id", "inventory_stock_movements.id"],
            name="fk_purchase_return_inventory_movement",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "receipt_line_id"],
            [
                "purchasing_purchase_order_receipt_lines.company_id",
                "purchasing_purchase_order_receipt_lines.id",
            ],
            name="fk_purchase_return_receipt_line",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "purchase_order_id"],
            ["purchasing_purchase_orders.company_id", "purchasing_purchase_orders.id"],
            name="fk_purchase_return_po",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "purchase_order_line_id"],
            [
                "purchasing_purchase_order_lines.company_id",
                "purchasing_purchase_order_lines.id",
            ],
            name="fk_purchase_return_po_line",
            ondelete="RESTRICT",
        ),
        CheckConstraint("quantity > 0", name="ck_purchase_return_quantity"),
        CheckConstraint(
            "reason IN ('damaged_after_receipt','defective','wrong_item','excess_not_needed','vendor_requested','other')",
            name="ck_purchase_return_reason",
        ),
        CheckConstraint(
            "status IN ('requested','authorized','denied','return_ready','returned','received_by_vendor','closed','canceled')",
            name="ck_purchase_return_status",
        ),
        CheckConstraint(
            "authorization_status IN ('not_requested','requested','received','denied','not_required')",
            name="ck_purchase_return_authorization",
        ),
        CheckConstraint("version >= 1", name="ck_purchase_return_version"),
        UniqueConstraint(
            "company_id", "return_identity", name="uq_purchase_return_identity"
        ),
        UniqueConstraint("company_id", "id", name="uq_purchase_return_company"),
        Index("ix_purchase_return_po", "company_id", "purchase_order_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    purchase_order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    vendor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    receipt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    receipt_line_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    purchase_order_line_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    return_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    item_identity_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    accepted_quantity_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    reason_note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="requested")
    authorization_status: Mapped[str] = mapped_column(String(32), nullable=False)
    vendor_authorization_reference: Mapped[str | None] = mapped_column(String(200))
    vendor_instructions: Mapped[str | None] = mapped_column(Text)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    updated_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    authorization_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    vendor_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_reference: Mapped[str | None] = mapped_column(String(240))
    inventory_movement_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class PurchaseOrderChangeOrder(Base):
    __tablename__ = "purchasing_po_change_orders"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "purchase_order_id"],
            ["purchasing_purchase_orders.company_id", "purchasing_purchase_orders.id"],
            name="fk_purchasing_change_po",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('requested','approved','rejected')",
            name="ck_purchasing_change_status",
        ),
        UniqueConstraint(
            "company_id", "change_identity", name="uq_purchasing_change_identity"
        ),
        UniqueConstraint("company_id", "id", name="uq_purchasing_change_company"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    purchase_order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    change_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    base_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    proposed_changes: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="requested")
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    decided_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_revision: Mapped[int | None] = mapped_column(Integer)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    downstream_reconciliation_required: Mapped[bool] = mapped_column(
        nullable=False, default=False
    )


class PurchaseOrderRevision(Base):
    __tablename__ = "purchasing_po_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "purchase_order_id"],
            ["purchasing_purchase_orders.company_id", "purchasing_purchase_orders.id"],
            name="fk_purchasing_revision_po",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "purchase_order_id",
            "revision_number",
            name="uq_purchasing_revision_number",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    purchase_order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    predecessor_revision: Mapped[int | None] = mapped_column(Integer)
    change_order_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("purchasing_po_change_orders.id", ondelete="RESTRICT"),
    )
    effective_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class PurchaseOrderDispositionEvidence(Base):
    __tablename__ = "purchasing_po_disposition_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "purchase_order_id"],
            ["purchasing_purchase_orders.company_id", "purchasing_purchase_orders.id"],
            name="fk_purchasing_disposition_po",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "disposition IN ('fully_satisfied','canceled_before_receipt','remainder_canceled')",
            name="ck_purchasing_disposition_kind",
        ),
        UniqueConstraint(
            "company_id", "purchase_order_id", name="uq_purchasing_disposition_po"
        ),
        UniqueConstraint("company_id", "id", name="uq_purchasing_disposition_company"),
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
    effective_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    prior_status: Mapped[str] = mapped_column(String(20), nullable=False)
    disposition: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    quantity_evidence: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False
    )
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ReplenishmentDecisionEvidence(Base):
    __tablename__ = "purchasing_replenishment_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_purchasing_replenishment_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "vendor_id"],
            [
                "purchasing_operational_vendors.company_id",
                "purchasing_operational_vendors.id",
            ],
            name="fk_purchasing_replenishment_vendor",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "inventory_item_id"],
            ["inventory_items.company_id", "inventory_items.id"],
            name="fk_purchasing_replenishment_item",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "purchase_order_id"],
            ["purchasing_purchase_orders.company_id", "purchasing_purchase_orders.id"],
            name="fk_purchasing_replenishment_po",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "decision IN ('approved','rejected')",
            name="ck_purchasing_replenishment_decision",
        ),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_purchasing_replenishment_key"
        ),
        UniqueConstraint(
            "company_id",
            "recommendation_digest",
            name="uq_purchasing_replenishment_recommendation",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    inventory_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    recommendation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    recommendation_snapshot: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False
    )
    approval_evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    approved_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    vendor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    purchase_order_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class BranchPurchasingPolicy(Base):
    """Current branch/item replenishment target with immutable revision evidence."""

    __tablename__ = "purchasing_branch_policies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_purchasing_branch_policy_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "inventory_item_id"],
            ["inventory_items.company_id", "inventory_items.id"],
            name="fk_purchasing_branch_policy_item",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "target_available_quantity >= 0",
            name="ck_purchasing_branch_policy_target",
        ),
        CheckConstraint(
            "status IN ('active','inactive')",
            name="ck_purchasing_branch_policy_status",
        ),
        CheckConstraint("version >= 1", name="ck_purchasing_branch_policy_version"),
        UniqueConstraint(
            "company_id",
            "branch_id",
            "inventory_item_id",
            name="uq_purchasing_branch_policy_item",
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_purchasing_branch_policy_company"
        ),
        Index(
            "ix_purchasing_branch_policy_scope",
            "company_id",
            "branch_id",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    inventory_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    target_available_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    provenance_reference: Mapped[str] = mapped_column(String(240), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    updated_by_user_id: Mapped[UUID] = mapped_column(
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


class BranchPurchasingPolicyRevision(Base):
    __tablename__ = "purchasing_branch_policy_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "policy_id"],
            ["purchasing_branch_policies.company_id", "purchasing_branch_policies.id"],
            name="fk_purchasing_branch_policy_revision_policy",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "target_available_quantity >= 0",
            name="ck_purchasing_branch_policy_revision_target",
        ),
        CheckConstraint(
            "status IN ('active','inactive')",
            name="ck_purchasing_branch_policy_revision_status",
        ),
        CheckConstraint(
            "length(evidence_digest) = 64 AND length(payload_digest) = 64",
            name="ck_purchasing_branch_policy_revision_digests",
        ),
        UniqueConstraint(
            "company_id",
            "policy_id",
            "version",
            name="uq_purchasing_branch_policy_revision_version",
        ),
        UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_purchasing_branch_policy_revision_key",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    policy_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    target_available_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    provenance_reference: Mapped[str] = mapped_column(String(240), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class PurchaseRequisition(Base):
    """Governed procurement demand; approval is distinct from PO authority."""

    __tablename__ = "purchasing_requisitions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_purchasing_requisition_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "inventory_item_id"],
            ["inventory_items.company_id", "inventory_items.id"],
            name="fk_purchasing_requisition_item",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "suggested_vendor_id"],
            [
                "purchasing_operational_vendors.company_id",
                "purchasing_operational_vendors.id",
            ],
            name="fk_purchasing_requisition_vendor",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "purchase_order_id"],
            ["purchasing_purchase_orders.company_id", "purchasing_purchase_orders.id"],
            name="fk_purchasing_requisition_po",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_purchasing_requisition_job",
            ondelete="RESTRICT",
        ),
        CheckConstraint("quantity > 0", name="ck_purchasing_requisition_quantity"),
        CheckConstraint(
            "status IN ('draft','submitted','approved','rejected','cancelled','converted')",
            name="ck_purchasing_requisition_status",
        ),
        CheckConstraint(
            "source_type IN ('manual','replenishment','job_material','stock_location','emergency_exception')",
            name="ck_purchasing_requisition_source",
        ),
        CheckConstraint("version >= 1", name="ck_purchasing_requisition_version"),
        UniqueConstraint(
            "company_id", "request_number", name="uq_purchasing_requisition_number"
        ),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_purchasing_requisition_key"
        ),
        UniqueConstraint("company_id", "id", name="uq_purchasing_requisition_company"),
        Index(
            "ix_purchasing_requisition_queue",
            "company_id",
            "branch_id",
            "status",
            "need_by",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    request_number: Mapped[str] = mapped_column(String(80), nullable=False)
    inventory_item_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    need_by: Mapped[date | None] = mapped_column(Date)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(240), nullable=False)
    job_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    suggested_vendor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requester_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    decided_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    purchase_order_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class SupplyChainPolicy(Base):
    """Versioned configuration readiness without selecting Company policy."""

    __tablename__ = "supply_chain_policies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_supply_chain_policy_branch",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "policy_type IN ('matching_tolerance','receiving','reorder','valuation','receipt_accrual','approval')",
            name="ck_supply_chain_policy_type",
        ),
        CheckConstraint(
            "status IN ('unconfigured','draft','active','inactive')",
            name="ck_supply_chain_policy_status",
        ),
        CheckConstraint("version >= 1", name="ck_supply_chain_policy_version"),
        UniqueConstraint(
            "company_id",
            "branch_id",
            "policy_type",
            name="uq_supply_chain_policy_scope",
        ),
        UniqueConstraint("company_id", "id", name="uq_supply_chain_policy_company"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    policy_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unconfigured"
    )
    configuration: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    readiness_reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by_user_id: Mapped[UUID] = mapped_column(
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


class PurchasingDocumentEvidence(Base):
    """Append-only provider-neutral document custody metadata."""

    __tablename__ = "purchasing_document_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_purchasing_document_branch",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "entity_type IN ('purchase_order','requisition','receipt','discrepancy','purchase_return')",
            name="ck_purchasing_document_entity_type",
        ),
        CheckConstraint(
            "length(content_digest) = 64", name="ck_purchasing_document_digest"
        ),
        CheckConstraint(
            "status IN ('active','superseded')", name="ck_purchasing_document_status"
        ),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_purchasing_document_key"
        ),
        UniqueConstraint(
            "company_id",
            "entity_type",
            "entity_id",
            "content_digest",
            name="uq_purchasing_document_content",
        ),
        UniqueConstraint("company_id", "id", name="uq_purchasing_document_company"),
        Index(
            "ix_purchasing_document_entity",
            "company_id",
            "entity_type",
            "entity_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    document_type: Mapped[str] = mapped_column(String(80), nullable=False)
    filename: Mapped[str] = mapped_column(String(240), nullable=False)
    media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
