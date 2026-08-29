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
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
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


class PayrollProtectedInputEnvelope(Base):
    """Encrypted sensitive Payroll input; plaintext never enters durable metadata."""

    __tablename__ = "payroll_protected_input_envelopes"
    __table_args__ = (
        UniqueConstraint("company_id", "id", name="uq_payroll_protected_company_id"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    key_id: Mapped[str] = mapped_column(String(80), nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class PayrollInputAuthorityVersion(Base):
    """Company/Employee tax, deduction, or employer-contribution authority."""

    __tablename__ = "payroll_input_authority_versions"
    __table_args__ = (
        CheckConstraint(
            "authority_domain IN ('tax','deduction','employer_contribution')",
            name="ck_payroll_input_domain",
        ),
        CheckConstraint(
            "lifecycle IN ('draft','approved','superseded','retired')",
            name="ck_payroll_input_lifecycle",
        ),
        CheckConstraint(
            "applicability IN ('required','not_applicable')",
            name="ck_payroll_input_applicability",
        ),
        CheckConstraint(
            "effective_end IS NULL OR effective_end > effective_start",
            name="ck_payroll_input_interval",
        ),
        CheckConstraint(
            "(lifecycle = 'draft' AND approved_by_user_id IS NULL "
            "AND approved_at IS NULL) OR (lifecycle <> 'draft' "
            "AND approved_by_user_id IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_payroll_input_approval",
        ),
        ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "protected_envelope_id"],
            [
                "payroll_protected_input_envelopes.company_id",
                "payroll_protected_input_envelopes.id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "employee_id",
            "authority_domain",
            "authority_key",
            "authority_version",
            name="uq_payroll_input_authority_version",
        ),
        UniqueConstraint("company_id", "id", name="uq_payroll_input_company_id"),
        Index(
            "ix_payroll_input_resolution",
            "company_id",
            "employee_id",
            "authority_domain",
            "authority_key",
            "lifecycle",
            "effective_start",
            "effective_end",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    employee_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    authority_domain: Mapped[str] = mapped_column(String(32), nullable=False)
    authority_key: Mapped[str] = mapped_column(String(120), nullable=False)
    authority_version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition_version: Mapped[str] = mapped_column(String(80), nullable=False)
    applicability: Mapped[str] = mapped_column(String(24), nullable=False)
    effective_start: Mapped[date] = mapped_column(Date, nullable=False)
    effective_end: Mapped[date | None] = mapped_column(Date)
    lifecycle: Mapped[str] = mapped_column(String(20), nullable=False)
    jurisdiction_reference: Mapped[str | None] = mapped_column(String(160))
    calculation_basis: Mapped[str | None] = mapped_column(String(80))
    priority: Mapped[int | None] = mapped_column(Integer)
    public_parameters: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    authority_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    protected_envelope_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    supersedes_authority_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("payroll_input_authority_versions.id", ondelete="RESTRICT"),
    )
    drafted_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
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


class PayrollGrossCalculationResultRecord(Base):
    __tablename__ = "payroll_gross_calculation_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "lifecycle IN ('calculated','under_review','approved','superseded','voided')",
            name="ck_payroll_gross_result_lifecycle",
        ),
        CheckConstraint(
            "review_state IN ('not_started','under_review','accepted','rejected')",
            name="ck_payroll_gross_result_review_state",
        ),
        CheckConstraint("gross_pay_total >= 0", name="ck_payroll_gross_total_nonnegative"),
        UniqueConstraint(
            "company_id", "calculation_digest", name="uq_payroll_gross_result_digest"
        ),
        UniqueConstraint("company_id", "id", name="uq_payroll_gross_result_company_id"),
        ForeignKeyConstraint(
            ["company_id", "policy_id"],
            ["payroll_company_policy_versions.company_id", "payroll_company_policy_versions.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "compensation_authority_id"],
            [
                "payroll_compensation_authority_versions.company_id",
                "payroll_compensation_authority_versions.id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id", "result_identity", name="uq_payroll_gross_result_identity"
        ),
        UniqueConstraint(
            "supersedes_result_id", name="uq_payroll_gross_result_single_successor"
        ),
        Index(
            "uq_payroll_gross_result_active_subject_period",
            "company_id",
            "employee_id",
            "pay_period_id",
            unique=True,
            postgresql_where=text(
                "lifecycle IN ('calculated','under_review','approved')"
            ),
        ),
        Index(
            "ix_payroll_gross_result_period",
            "company_id",
            "pay_period_id",
            "lifecycle",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    pay_period_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    result_identity: Mapped[str] = mapped_column(String(96), nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(80), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    policy_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    policy_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    compensation_authority_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    compensation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    time_snapshot_id: Mapped[str | None] = mapped_column(String(96))
    time_snapshot_digest: Mapped[str | None] = mapped_column(String(64))
    admission_id: Mapped[str] = mapped_column(String(96), nullable=False)
    admission_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    earning_components: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False
    )
    gross_pay_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    calculation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    lifecycle: Mapped[str] = mapped_column(String(24), nullable=False)
    review_state: Mapped[str] = mapped_column(String(24), nullable=False)
    supersedes_result_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("payroll_gross_calculation_results.id", ondelete="RESTRICT"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class PayrollGrossCalculationReviewRecord(Base):
    __tablename__ = "payroll_gross_calculation_reviews"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('initiated','accepted','rejected')",
            name="ck_payroll_gross_review_decision",
        ),
        ForeignKeyConstraint(
            ["company_id", "result_id"],
            [
                "payroll_gross_calculation_results.company_id",
                "payroll_gross_calculation_results.id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "result_id", "review_sequence", name="uq_payroll_gross_review_sequence"
        ),
        Index(
            "ix_payroll_gross_review_result",
            "company_id",
            "result_id",
            "review_sequence",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    result_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    review_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    reviewer_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    safe_note: Mapped[str | None] = mapped_column(Text)
    result_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    review_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PayrollTaxDeductionResultRecord(Base):
    __tablename__ = "payroll_tax_deduction_results"
    __table_args__ = (
        CheckConstraint(
            "lifecycle IN ('calculated','under_review','approved','rejected','superseded','voided')",
            name="ck_payroll_tax_result_lifecycle",
        ),
        CheckConstraint(
            "review_state IN ('not_started','under_review','accepted','rejected')",
            name="ck_payroll_tax_result_review_state",
        ),
        ForeignKeyConstraint(
            ["company_id", "gross_result_id"],
            ["payroll_gross_calculation_results.company_id", "payroll_gross_calculation_results.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "id", name="uq_payroll_tax_result_company_id"),
        UniqueConstraint("company_id", "result_identity", name="uq_payroll_tax_result_identity"),
        UniqueConstraint("company_id", "calculation_digest", name="uq_payroll_tax_result_digest"),
        UniqueConstraint("supersedes_result_id", name="uq_payroll_tax_result_successor"),
        Index(
            "uq_payroll_tax_result_active_subject",
            "company_id", "employee_id", "pay_period_id",
            unique=True,
            postgresql_where=text("lifecycle IN ('calculated','under_review','approved')"),
        ),
        Index("ix_payroll_tax_result_period", "company_id", "pay_period_id", "employee_id"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    pay_period_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    gross_result_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    gross_calculation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    result_identity: Mapped[str] = mapped_column(String(96), nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(80), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    admission_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    authority_evidence: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    components: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    gross_pay: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    employee_tax_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    employee_deduction_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    employer_contribution_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    net_pay_candidate: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    money_version: Mapped[str] = mapped_column(String(80), nullable=False)
    calculation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(24), nullable=False)
    review_state: Mapped[str] = mapped_column(String(24), nullable=False)
    supersedes_result_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payroll_tax_deduction_results.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PayrollTaxDeductionReviewRecord(Base):
    __tablename__ = "payroll_tax_deduction_reviews"
    __table_args__ = (
        CheckConstraint("decision IN ('initiated','accepted','rejected')", name="ck_payroll_tax_review_decision"),
        ForeignKeyConstraint(
            ["company_id", "result_id"],
            ["payroll_tax_deduction_results.company_id", "payroll_tax_deduction_results.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("result_id", "review_sequence", name="uq_payroll_tax_review_sequence"),
        UniqueConstraint("review_digest", name="uq_payroll_tax_review_digest"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    result_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    review_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    reviewer_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    safe_note: Mapped[str | None] = mapped_column(Text)
    result_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    review_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
