"""Durable Company Payroll policy and Employee compensation authority."""

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


class CompanyPayrollPolicyVersion(Base):
    __tablename__ = "payroll_company_policy_versions"
    __table_args__ = (
        CheckConstraint("policy_version >= 1", name="ck_payroll_policy_version"),
        CheckConstraint(
            "lifecycle IN ('draft','approved','superseded','retired')",
            name="ck_payroll_policy_lifecycle",
        ),
        CheckConstraint(
            "effective_end IS NULL OR effective_end > effective_start",
            name="ck_payroll_policy_interval",
        ),
        CheckConstraint(
            "(lifecycle = 'draft' AND approved_by_user_id IS NULL "
            "AND approved_at IS NULL) OR (lifecycle <> 'draft' "
            "AND approved_by_user_id IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_payroll_policy_approval",
        ),
        UniqueConstraint(
            "company_id", "policy_version", name="uq_payroll_policy_version"
        ),
        UniqueConstraint("company_id", "id", name="uq_payroll_policy_company_id"),
        Index(
            "ix_payroll_policy_resolution",
            "company_id",
            "lifecycle",
            "effective_start",
            "effective_end",
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
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_start: Mapped[date] = mapped_column(Date, nullable=False)
    effective_end: Mapped[date | None] = mapped_column(Date)
    lifecycle: Mapped[str] = mapped_column(String(20), nullable=False)
    definition_version: Mapped[str] = mapped_column(String(80), nullable=False)
    definition: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    decision_evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    authority_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    supersedes_policy_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("payroll_company_policy_versions.id", ondelete="RESTRICT"),
    )
    drafted_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    audit_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EmployeeCompensationAuthorityVersion(Base):
    __tablename__ = "payroll_compensation_authority_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("authority_version >= 1", name="ck_payroll_comp_version"),
        CheckConstraint(
            "lifecycle IN ('draft','approved','superseded','retired')",
            name="ck_payroll_comp_lifecycle",
        ),
        CheckConstraint(
            "compensation_type IN ('hourly','salaried')",
            name="ck_payroll_comp_type",
        ),
        CheckConstraint(
            "effective_end IS NULL OR effective_end > effective_start",
            name="ck_payroll_comp_interval",
        ),
        CheckConstraint(
            "(compensation_type = 'hourly' AND hourly_rate > 0 "
            "AND salary_amount IS NULL AND salary_frequency IS NULL) OR "
            "(compensation_type = 'salaried' AND salary_amount > 0 "
            "AND salary_frequency IS NOT NULL AND hourly_rate IS NULL)",
            name="ck_payroll_comp_shape",
        ),
        CheckConstraint(
            "(lifecycle = 'draft' AND approved_by_user_id IS NULL "
            "AND approved_at IS NULL) OR (lifecycle <> 'draft' "
            "AND approved_by_user_id IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_payroll_comp_approval",
        ),
        UniqueConstraint(
            "company_id",
            "employee_id",
            "authority_version",
            name="uq_payroll_comp_version",
        ),
        UniqueConstraint("company_id", "id", name="uq_payroll_comp_company_id"),
        Index(
            "ix_payroll_comp_resolution",
            "company_id",
            "employee_id",
            "lifecycle",
            "effective_start",
            "effective_end",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    authority_version: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_start: Mapped[date] = mapped_column(Date, nullable=False)
    effective_end: Mapped[date | None] = mapped_column(Date)
    lifecycle: Mapped[str] = mapped_column(String(20), nullable=False)
    definition_version: Mapped[str] = mapped_column(String(80), nullable=False)
    compensation_type: Mapped[str] = mapped_column(String(20), nullable=False)
    hourly_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    salary_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    salary_frequency: Mapped[str | None] = mapped_column(String(40))
    worker_class_reference: Mapped[str | None] = mapped_column(String(160))
    additional_earning_types: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    recurring_components: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    decision_evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    authority_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    supersedes_authority_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("payroll_compensation_authority_versions.id", ondelete="RESTRICT"),
    )
    drafted_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    audit_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
