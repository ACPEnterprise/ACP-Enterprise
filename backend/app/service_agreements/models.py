from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
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


class AgreementPlan(Base):
    __tablename__ = "service_agreement_plans"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_agreement_plans_branch_scope",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('draft','active','superseded','inactive')",
            name="ck_agreement_plans_status",
        ),
        CheckConstraint(
            "version >= 1 AND duration_months > 0 AND included_visits >= 0",
            name="ck_agreement_plans_values",
        ),
        CheckConstraint(
            "billing_cadence IN ('unconfigured','monthly','annual','single')",
            name="ck_agreement_plans_cadence",
        ),
        UniqueConstraint(
            "company_id", "code", "version", name="uq_agreement_plans_code_version"
        ),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_agreement_plans_idempotency"
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_agreement_plans_company_id"
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
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    price_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    billing_cadence: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unconfigured"
    )
    duration_months: Mapped[int] = mapped_column(Integer, nullable=False)
    included_visits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    benefits: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    renewal_policy: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    cancellation_policy: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    definition_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ServiceAgreement(Base):
    __tablename__ = "service_agreements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_service_agreements_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "customer_id"],
            ["customers.company_id", "customers.id"],
            name="fk_service_agreements_customer",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "plan_id"],
            ["service_agreement_plans.company_id", "service_agreement_plans.id"],
            name="fk_service_agreements_plan",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "predecessor_agreement_id"],
            ["service_agreements.company_id", "service_agreements.id"],
            name="fk_service_agreements_predecessor",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('draft','pending_activation','active','renewal_pending','renewed','cancelled','expired','suspended')",
            name="ck_service_agreements_status",
        ),
        CheckConstraint(
            "version >= 1 AND end_date >= start_date",
            name="ck_service_agreements_values",
        ),
        UniqueConstraint(
            "company_id", "agreement_number", name="uq_service_agreements_number"
        ),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_service_agreements_idempotency"
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_service_agreements_company_id"
        ),
        UniqueConstraint(
            "company_id",
            "branch_id",
            "id",
            name="uq_service_agreements_company_branch_id",
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
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    plan_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    predecessor_agreement_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    agreement_number: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending_activation"
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    plan_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
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


class AgreementCoverage(Base):
    __tablename__ = "service_agreement_coverage"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "agreement_id"],
            ["service_agreements.company_id", "service_agreements.id"],
            name="fk_agreement_coverage_agreement",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "agreement_id",
            "service_location_id",
            name="uq_agreement_coverage_location",
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
    agreement_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    service_location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("service_locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date] = mapped_column(Date, nullable=False)


class ServiceEntitlement(Base):
    __tablename__ = "service_agreement_entitlements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "agreement_id"],
            [
                "service_agreements.company_id",
                "service_agreements.branch_id",
                "service_agreements.id",
            ],
            name="fk_agreement_entitlements_agreement",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id", "appointment_id"],
            ["appointments.company_id", "appointments.branch_id", "appointments.id"],
            name="fk_agreement_entitlements_appointment",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_agreement_entitlements_job",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('due','scheduled','completed','expired','cancelled','blocked')",
            name="ck_agreement_entitlements_status",
        ),
        UniqueConstraint(
            "company_id",
            "agreement_id",
            "service_location_id",
            "sequence",
            name="uq_agreement_entitlement_sequence",
        ),
        UniqueConstraint(
            "company_id",
            "branch_id",
            "id",
            "agreement_id",
            name="uq_agreement_entitlements_evidence_binding",
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
    agreement_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    service_location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("service_locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    service_category: Mapped[str] = mapped_column(
        String(100), nullable=False, default="configured_service"
    )
    eligible_from: Mapped[date] = mapped_column(Date, nullable=False)
    eligible_to: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="due")
    appointment_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    job_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AgreementLifecycleEvidence(Base):
    __tablename__ = "service_agreement_lifecycle_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "agreement_id"],
            [
                "service_agreements.company_id",
                "service_agreements.branch_id",
                "service_agreements.id",
            ],
            name="fk_agreement_evidence_agreement",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id", "entitlement_id", "agreement_id"],
            [
                "service_agreement_entitlements.company_id",
                "service_agreement_entitlements.branch_id",
                "service_agreement_entitlements.id",
                "service_agreement_entitlements.agreement_id",
            ],
            name="fk_agreement_evidence_entitlement",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "action IN ('activate','renewal_review','renew','cancel','expire','generate_entitlements','schedule_link','job_link','consume','reverse_consumption','billing_ready')",
            name="ck_agreement_evidence_action",
        ),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_agreement_evidence_idempotency"
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
    agreement_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    entitlement_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    prior_status: Mapped[str] = mapped_column(String(24), nullable=False)
    resulting_status: Mapped[str] = mapped_column(String(24), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    payload: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AgreementBillingOccurrence(Base):
    __tablename__ = "service_agreement_billing_occurrences"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "agreement_id"],
            [
                "service_agreements.company_id",
                "service_agreements.branch_id",
                "service_agreements.id",
            ],
            name="fk_agreement_billing_agreement",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "invoice_id"],
            ["invoices.company_id", "invoices.id"],
            name="fk_agreement_billing_invoice",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('unconfigured','ready','invoiced','cancelled','reconciliation_required')",
            name="ck_agreement_billing_status",
        ),
        UniqueConstraint(
            "company_id",
            "agreement_id",
            "period_start",
            name="uq_agreement_billing_period",
        ),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_agreement_billing_idempotency"
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
    agreement_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    invoice_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    payment_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="not_initiated"
    )
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
