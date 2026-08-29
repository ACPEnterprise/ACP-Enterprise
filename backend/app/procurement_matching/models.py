from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProcurementMatch(Base):
    __tablename__ = "procurement_three_way_matches"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "supersedes_match_id"],
            [
                "procurement_three_way_matches.company_id",
                "procurement_three_way_matches.id",
            ],
            name="fk_procurement_match_supersedes",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "purchase_order_id"],
            ["purchasing_purchase_orders.company_id", "purchasing_purchase_orders.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "vendor_bill_id"],
            ["ap_bills.company_id", "ap_bills.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "state IN ('matched','partially_matched','quantity_variance','price_variance','unreceived_billing','unbilled_receipt','overbilled','return_pending_credit','currency_conflict','vendor_conflict','item_conflict','blocked','requires_review')",
            name="ck_procurement_match_state",
        ),
        CheckConstraint(
            "admission_state IN ('eligible','blocked','review_required')",
            name="ck_procurement_match_admission",
        ),
        UniqueConstraint(
            "company_id",
            "vendor_bill_id",
            "evaluation_sequence",
            name="uq_procurement_match_bill_sequence",
        ),
        UniqueConstraint("company_id", "id", name="uq_procurement_match_company_id"),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_procurement_match_idempotency"
        ),
        Index(
            "uq_procurement_match_active_bill",
            "company_id",
            "vendor_bill_id",
            unique=True,
            postgresql_where=text("superseded_at IS NULL"),
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
    vendor_bill_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    operational_vendor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    accounting_vendor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    admission_state: Mapped[str] = mapped_column(String(24), nullable=False)
    policy_reference: Mapped[str | None] = mapped_column(String(160))
    purchase_order_version: Mapped[int] = mapped_column(Integer, nullable=False)
    bill_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_match_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    evaluated_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ProcurementMatchLine(Base):
    __tablename__ = "procurement_three_way_match_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "match_id"],
            [
                "procurement_three_way_matches.company_id",
                "procurement_three_way_matches.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "purchase_order_line_id"],
            [
                "purchasing_purchase_order_lines.company_id",
                "purchasing_purchase_order_lines.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "bill_line_id"],
            ["ap_bill_lines.company_id", "ap_bill_lines.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "receipt_line_id"],
            [
                "purchasing_purchase_order_receipt_lines.company_id",
                "purchasing_purchase_order_receipt_lines.id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "state IN ('matched','partially_matched','quantity_variance','price_variance','unreceived_billing','overbilled','return_pending_credit','item_conflict','blocked','requires_review')",
            name="ck_procurement_match_line_state",
        ),
        UniqueConstraint(
            "company_id",
            "match_id",
            "bill_line_id",
            name="uq_procurement_match_line_bill",
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_procurement_match_line_company_id"
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    match_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    purchase_order_line_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    receipt_line_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    bill_line_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    inventory_item_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    ordered_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    returned_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    net_accepted_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False
    )
    billed_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    po_unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    billed_unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    billed_net_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    billed_tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    quantity_variance: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    price_variance: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)


class ProcurementMatchException(Base):
    __tablename__ = "procurement_match_exceptions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "match_id"],
            [
                "procurement_three_way_matches.company_id",
                "procurement_three_way_matches.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "match_line_id"],
            [
                "procurement_three_way_match_lines.company_id",
                "procurement_three_way_match_lines.id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('open','reviewed','resolved')",
            name="ck_procurement_match_exception_status",
        ),
        CheckConstraint(
            "category IN ('quantity_variance','price_variance','vendor_conflict','item_conflict','currency_conflict','missing_po','missing_receipt','missing_bill','duplicate_bill','duplicate_receipt','overbilled','return_pending_credit','damaged_or_short')",
            name="ck_procurement_match_exception_category",
        ),
        CheckConstraint(
            "resolution IS NULL OR resolution IN ('accept_variance','request_vendor_credit','hold_bill','reject_bill','wait_for_receipt','wait_for_bill','correct_future_po','return_goods','manual_review_required')",
            name="ck_procurement_match_exception_resolution",
        ),
        UniqueConstraint(
            "company_id",
            "match_id",
            "category",
            "match_line_id",
            name="uq_procurement_match_exception_fact",
        ),
        UniqueConstraint(
            "company_id",
            "resolution_idempotency_key",
            name="uq_procurement_match_resolution_idempotency",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    match_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    match_line_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    expected_evidence: Mapped[str] = mapped_column(Text, nullable=False)
    actual_evidence: Mapped[str] = mapped_column(Text, nullable=False)
    resolution: Mapped[str | None] = mapped_column(String(40))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolution_idempotency_key: Mapped[str | None] = mapped_column(String(128))
    resolution_payload_digest: Mapped[str | None] = mapped_column(String(64))
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
