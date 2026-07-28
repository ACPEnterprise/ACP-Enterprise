from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Estimate(Base):
    __tablename__ = "estimates"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_estimates_job_scope",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('draft', 'presented', 'approved', 'declined', 'expired')",
            name="ck_estimates_status",
        ),
        CheckConstraint(
            "subtotal_amount >= 0 AND tax_amount >= 0 AND total_amount >= 0 "
            "AND total_amount = subtotal_amount + tax_amount",
            name="ck_estimates_amounts",
        ),
        UniqueConstraint(
            "company_id",
            "branch_id",
            "id",
            "customer_id",
            "service_location_id",
            name="uq_estimates_migration_scope",
        ),
        UniqueConstraint("company_id", "id", name="uq_estimates_company_id"),
        UniqueConstraint("company_id", "estimate_number", name="uq_estimate_number"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    service_location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("service_locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    estimate_number: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    presented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_on: Mapped[date | None] = mapped_column(Date)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EstimateLineItem(Base):
    __tablename__ = "estimate_line_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "estimate_id"],
            ["estimates.company_id", "estimates.id"],
            name="fk_estimate_line_items_estimate_scope",
            ondelete="RESTRICT",
        ),
        CheckConstraint("position > 0", name="ck_estimate_line_items_position"),
        CheckConstraint(
            "quantity > 0 AND unit_price >= 0 AND total_amount >= 0",
            name="ck_estimate_line_items_amounts",
        ),
        UniqueConstraint(
            "company_id",
            "estimate_id",
            "position",
            name="uq_estimate_line_items_position",
        ),
        UniqueConstraint(
            "company_id",
            "estimate_id",
            "id",
            name="uq_estimate_line_items_migration_scope",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    estimate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_invoices_job_scope",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('draft', 'issued', 'partially_paid', 'paid', 'void')",
            name="ck_invoices_status",
        ),
        CheckConstraint(
            "subtotal_amount >= 0 AND tax_amount >= 0 AND total_amount >= 0 "
            "AND total_amount = subtotal_amount + tax_amount",
            name="ck_invoices_amounts",
        ),
        UniqueConstraint(
            "company_id",
            "branch_id",
            "id",
            "customer_id",
            "service_location_id",
            name="uq_invoices_migration_scope",
        ),
        UniqueConstraint("company_id", "id", name="uq_invoices_company_id"),
        UniqueConstraint(
            "company_id",
            "branch_id",
            "id",
            "customer_id",
            name="uq_invoices_payment_scope",
        ),
        UniqueConstraint("company_id", "invoice_number", name="uq_invoice_number"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    service_location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("service_locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    invoice_number: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_on: Mapped[date | None] = mapped_column(Date)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "invoice_id"],
            ["invoices.company_id", "invoices.id"],
            name="fk_invoice_line_items_invoice_scope",
            ondelete="RESTRICT",
        ),
        CheckConstraint("position > 0", name="ck_invoice_line_items_position"),
        CheckConstraint(
            "quantity > 0 AND unit_price >= 0 AND total_amount >= 0",
            name="ck_invoice_line_items_amounts",
        ),
        UniqueConstraint(
            "company_id",
            "invoice_id",
            "position",
            name="uq_invoice_line_items_position",
        ),
        UniqueConstraint(
            "company_id",
            "invoice_id",
            "id",
            name="uq_invoice_line_items_migration_scope",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    invoice_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "invoice_id", "customer_id"],
            [
                "invoices.company_id",
                "invoices.branch_id",
                "invoices.id",
                "invoices.customer_id",
            ],
            name="fk_payments_invoice_scope",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed', 'refunded')",
            name="ck_payments_status",
        ),
        CheckConstraint("amount > 0", name="ck_payments_amount"),
        UniqueConstraint(
            "company_id",
            "branch_id",
            "id",
            "invoice_id",
            "customer_id",
            name="uq_payments_migration_scope",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    invoice_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    method: Mapped[str | None] = mapped_column(String(40))
    reference: Mapped[str | None] = mapped_column(String(191))
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
