"""Durable Company Payroll policy and Employee compensation authority."""

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
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
        UniqueConstraint(
            "company_id",
            "employee_id",
            "pay_period_id",
            "id",
            name="uq_payroll_gross_result_statement_scope",
        ),
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
        ForeignKeyConstraint(
            ["company_id", "employee_id", "pay_period_id", "supersedes_result_id"],
            ["payroll_gross_calculation_results.company_id", "payroll_gross_calculation_results.employee_id", "payroll_gross_calculation_results.pay_period_id", "payroll_gross_calculation_results.id"],
            name="fk_payroll_gross_result_predecessor_scope",
            ondelete="RESTRICT",
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
    supersedes_result_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
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
            ["company_id", "employee_id", "pay_period_id", "gross_result_id"],
            [
                "payroll_gross_calculation_results.company_id",
                "payroll_gross_calculation_results.employee_id",
                "payroll_gross_calculation_results.pay_period_id",
                "payroll_gross_calculation_results.id",
            ],
            name="fk_payroll_tax_result_gross_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "id", name="uq_payroll_tax_result_company_id"),
        UniqueConstraint(
            "company_id",
            "employee_id",
            "id",
            name="uq_payroll_tax_result_instruction_scope",
        ),
        UniqueConstraint(
            "company_id",
            "employee_id",
            "pay_period_id",
            "id",
            name="uq_payroll_tax_result_statement_scope",
        ),
        UniqueConstraint("company_id", "result_identity", name="uq_payroll_tax_result_identity"),
        UniqueConstraint("company_id", "calculation_digest", name="uq_payroll_tax_result_digest"),
        UniqueConstraint("supersedes_result_id", name="uq_payroll_tax_result_successor"),
        ForeignKeyConstraint(
            ["company_id", "employee_id", "pay_period_id", "supersedes_result_id"],
            ["payroll_tax_deduction_results.company_id", "payroll_tax_deduction_results.employee_id", "payroll_tax_deduction_results.pay_period_id", "payroll_tax_deduction_results.id"],
            name="fk_payroll_tax_result_predecessor_scope",
            ondelete="RESTRICT",
        ),
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
    supersedes_result_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
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


class PayrollRunRecord(Base):
    __tablename__ = "payroll_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "pay_period_id"],
            ["timekeeping_pay_periods.company_id", "timekeeping_pay_periods.id"],
            name="fk_payroll_runs_pay_period_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "supersedes_run_id"],
            ["payroll_runs.company_id", "payroll_runs.id"],
            name="fk_payroll_runs_predecessor_scope",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "lifecycle IN ('assembled','under_review','reviewed','approved','rejected','superseded','voided')",
            name="ck_payroll_run_lifecycle",
        ),
        CheckConstraint(
            "review_state IN ('not_started','under_review','accepted','rejected')",
            name="ck_payroll_run_review_state",
        ),
        UniqueConstraint("company_id", "id", name="uq_payroll_run_company_id"),
        UniqueConstraint(
            "company_id",
            "pay_period_id",
            "id",
            name="uq_payroll_run_statement_scope",
        ),
        UniqueConstraint("company_id", "run_identity", name="uq_payroll_run_identity"),
        UniqueConstraint("company_id", "run_digest", name="uq_payroll_run_digest"),
        UniqueConstraint("supersedes_run_id", name="uq_payroll_run_successor"),
        Index(
            "uq_payroll_run_active_period",
            "company_id",
            "pay_period_id",
            unique=True,
            postgresql_where=text(
                "lifecycle IN ('assembled','under_review','reviewed','approved')"
            ),
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    pay_period_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    schedule_definition_id: Mapped[str] = mapped_column(String(120), nullable=False)
    schedule_version: Mapped[str] = mapped_column(String(80), nullable=False)
    assembly_version: Mapped[str] = mapped_column(String(80), nullable=False)
    population_identity: Mapped[str] = mapped_column(String(120), nullable=False)
    population_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    run_identity: Mapped[str] = mapped_column(String(96), nullable=False)
    run_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_gross: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    aggregate_employee_taxes: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    aggregate_employee_deductions: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    aggregate_net_pay: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    aggregate_employer_contributions: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    assembled_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    assembled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(24), nullable=False)
    review_state: Mapped[str] = mapped_column(String(24), nullable=False)
    supersedes_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    consumed_by_payment_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class PayrollRunMemberRecord(Base):
    __tablename__ = "payroll_run_members"
    __table_args__ = (
        CheckConstraint(
            "disposition IN ('ready','blocked','excluded','not_applicable')",
            name="ck_payroll_run_member_disposition",
        ),
        ForeignKeyConstraint(
            ["company_id", "run_id"],
            ["payroll_runs.company_id", "payroll_runs.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "gross_result_id"],
            ["payroll_gross_calculation_results.company_id", "payroll_gross_calculation_results.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "tax_result_id"],
            ["payroll_tax_deduction_results.company_id", "payroll_tax_deduction_results.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("run_id", "employee_id", name="uq_payroll_run_member_employee"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    disposition: Mapped[str] = mapped_column(String(24), nullable=False)
    gross_result_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    gross_result_digest: Mapped[str | None] = mapped_column(String(64))
    tax_result_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    tax_result_digest: Mapped[str | None] = mapped_column(String(64))
    blocker_evidence_digest: Mapped[str | None] = mapped_column(String(64))
    disposition_authority_digest: Mapped[str | None] = mapped_column(String(64))
    membership_digest: Mapped[str] = mapped_column(String(64), nullable=False)


class PayrollRunReviewRecord(Base):
    __tablename__ = "payroll_run_reviews"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('initiated','accepted','rejected','approved')",
            name="ck_payroll_run_review_decision",
        ),
        ForeignKeyConstraint(
            ["company_id", "run_id"],
            ["payroll_runs.company_id", "payroll_runs.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("run_id", "review_sequence", name="uq_payroll_run_review_sequence"),
        UniqueConstraint("review_digest", name="uq_payroll_run_review_digest"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    review_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    safe_note: Mapped[str | None] = mapped_column(Text)
    run_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    review_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PayrollPaymentDestinationVersion(Base):
    __tablename__ = "payroll_payment_destination_versions"
    __table_args__ = (
        CheckConstraint(
            "method_type IN ('direct_deposit','paper_check','other')",
            name="ck_payroll_payment_destination_method",
        ),
        CheckConstraint(
            "lifecycle IN ('draft','approved','superseded','revoked','expired')",
            name="ck_payroll_payment_destination_lifecycle",
        ),
        CheckConstraint(
            "effective_end IS NULL OR effective_end > effective_start",
            name="ck_payroll_payment_destination_interval",
        ),
        ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "protected_envelope_id"],
            ["payroll_protected_input_envelopes.company_id", "payroll_protected_input_envelopes.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "id", name="uq_payroll_payment_destination_company_id"),
        UniqueConstraint(
            "company_id",
            "employee_id",
            "id",
            name="uq_payroll_payment_destination_instruction_scope",
        ),
        ForeignKeyConstraint(
            ["company_id", "employee_id", "supersedes_destination_id"],
            ["payroll_payment_destination_versions.company_id", "payroll_payment_destination_versions.employee_id", "payroll_payment_destination_versions.id"],
            name="fk_payroll_payment_destination_predecessor_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "employee_id", "destination_version", name="uq_payroll_payment_destination_version"),
        Index("ix_payroll_payment_destination_resolution", "company_id", "employee_id", "lifecycle", "effective_start", "effective_end"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    destination_version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition_version: Mapped[str] = mapped_column(String(80), nullable=False)
    method_type: Mapped[str] = mapped_column(String(32), nullable=False)
    destination_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    protected_envelope_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    masked_display: Mapped[str] = mapped_column(String(80), nullable=False)
    verification_evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_start: Mapped[date] = mapped_column(Date, nullable=False)
    effective_end: Mapped[date | None] = mapped_column(Date)
    lifecycle: Mapped[str] = mapped_column(String(20), nullable=False)
    authority_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    supersedes_destination_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    audit_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PayrollPaymentReleaseRecord(Base):
    __tablename__ = "payroll_payment_releases"
    __table_args__ = (
        CheckConstraint("lifecycle IN ('draft','under_review','approved_for_release','rejected','superseded','voided')", name="ck_payroll_payment_release_lifecycle"),
        CheckConstraint("review_state IN ('not_started','under_review','accepted','rejected')", name="ck_payroll_payment_release_review_state"),
        ForeignKeyConstraint(
            ["company_id", "pay_period_id", "payroll_run_id"],
            ["payroll_runs.company_id", "payroll_runs.pay_period_id", "payroll_runs.id"],
            name="fk_payroll_payment_release_run_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "payroll_run_id", "supersedes_release_id"],
            ["payroll_payment_releases.company_id", "payroll_payment_releases.payroll_run_id", "payroll_payment_releases.id"],
            name="fk_payroll_payment_release_predecessor_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "id", name="uq_payroll_payment_release_company_id"),
        UniqueConstraint(
            "company_id",
            "payroll_run_id",
            "id",
            name="uq_payroll_payment_release_execution_scope",
        ),
        UniqueConstraint("company_id", "package_identity", name="uq_payroll_payment_release_identity"),
        UniqueConstraint("company_id", "package_digest", name="uq_payroll_payment_release_digest"),
        UniqueConstraint("supersedes_release_id", name="uq_payroll_payment_release_successor"),
        Index("uq_payroll_payment_release_active_run", "company_id", "payroll_run_id", unique=True, postgresql_where=text("lifecycle IN ('draft','under_review','approved_for_release')")),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    payroll_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    payroll_run_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    pay_period_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    definition_version: Mapped[str] = mapped_column(String(80), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    package_identity: Mapped[str] = mapped_column(String(96), nullable=False)
    package_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_release_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    assembled_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    assembled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(28), nullable=False)
    review_state: Mapped[str] = mapped_column(String(24), nullable=False)
    supersedes_release_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    execution_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PayrollPaymentInstructionRecord(Base):
    __tablename__ = "payroll_payment_instructions"
    __table_args__ = (
        CheckConstraint("disposition IN ('ready','blocked','excluded','not_applicable')", name="ck_payroll_payment_instruction_disposition"),
        ForeignKeyConstraint(["company_id", "release_id"], ["payroll_payment_releases.company_id", "payroll_payment_releases.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["company_id", "employee_id"], ["employees.company_id", "employees.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["company_id", "employee_id", "tax_result_id"],
            ["payroll_tax_deduction_results.company_id", "payroll_tax_deduction_results.employee_id", "payroll_tax_deduction_results.id"],
            name="fk_payroll_payment_instruction_tax_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "employee_id", "destination_id"],
            ["payroll_payment_destination_versions.company_id", "payroll_payment_destination_versions.employee_id", "payroll_payment_destination_versions.id"],
            name="fk_payroll_payment_instruction_destination_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("release_id", "employee_id", name="uq_payroll_payment_instruction_employee"),
        UniqueConstraint("company_id", "instruction_identity", name="uq_payroll_payment_instruction_identity"),
        UniqueConstraint("company_id", "id", name="uq_payroll_payment_instruction_company_id"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    release_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    disposition: Mapped[str] = mapped_column(String(24), nullable=False)
    run_member_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    tax_result_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    tax_result_digest: Mapped[str | None] = mapped_column(String(64))
    destination_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    destination_digest: Mapped[str | None] = mapped_column(String(64))
    method_type: Mapped[str | None] = mapped_column(String(32))
    protected_destination_reference: Mapped[str | None] = mapped_column(String(120))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    blocker_evidence_digest: Mapped[str | None] = mapped_column(String(64))
    instruction_identity: Mapped[str] = mapped_column(String(96), nullable=False)
    instruction_digest: Mapped[str] = mapped_column(String(64), nullable=False)


class PayrollPaymentReleaseReviewRecord(Base):
    __tablename__ = "payroll_payment_release_reviews"
    __table_args__ = (
        CheckConstraint("decision IN ('initiated','accepted','rejected','approved')", name="ck_payroll_payment_release_review_decision"),
        ForeignKeyConstraint(["company_id", "release_id"], ["payroll_payment_releases.company_id", "payroll_payment_releases.id"], ondelete="RESTRICT"),
        UniqueConstraint("release_id", "review_sequence", name="uq_payroll_payment_release_review_sequence"),
        UniqueConstraint("review_digest", name="uq_payroll_payment_release_review_digest"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    release_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    review_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    safe_note: Mapped[str | None] = mapped_column(Text)
    package_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    review_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PayrollPaymentExecutionRecord(Base):
    __tablename__ = "payroll_payment_executions"
    __table_args__ = (
        CheckConstraint("lifecycle IN ('authorized','submission_pending','submitted','provider_acknowledged','settlement_pending','partially_settled','settled','rejected','failed','canceled','uncertain')", name="ck_payroll_payment_execution_lifecycle"),
        ForeignKeyConstraint(
            ["company_id", "payroll_run_id", "release_id"],
            ["payroll_payment_releases.company_id", "payroll_payment_releases.payroll_run_id", "payroll_payment_releases.id"],
            name="fk_payroll_payment_execution_release_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "id", name="uq_payroll_payment_execution_company_id"),
        UniqueConstraint("company_id", "execution_identity", name="uq_payroll_payment_execution_identity"),
        UniqueConstraint("company_id", "execution_digest", name="uq_payroll_payment_execution_digest"),
        Index("uq_payroll_payment_execution_active_release", "company_id", "release_id", unique=True, postgresql_where=text("lifecycle IN ('authorized','submission_pending','submitted','provider_acknowledged','settlement_pending','partially_settled','uncertain')")),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    release_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    payroll_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    package_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    definition_version: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_identity: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_version: Mapped[str] = mapped_column(String(40), nullable=False)
    execution_idempotency_key: Mapped[str] = mapped_column(String(96), nullable=False)
    execution_identity: Mapped[str] = mapped_column(String(96), nullable=False)
    execution_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    authorized_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(32), nullable=False)
    authorized_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    authorized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(120))
    request_digest: Mapped[str | None] = mapped_column(String(64))
    response_digest: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PayrollPaymentExecutionItemRecord(Base):
    __tablename__ = "payroll_payment_execution_items"
    __table_args__ = (
        CheckConstraint("lifecycle IN ('authorized','submitted','acknowledged','settlement_pending','settled','rejected','failed','unresolved')", name="ck_payroll_payment_execution_item_lifecycle"),
        ForeignKeyConstraint(["company_id", "execution_id"], ["payroll_payment_executions.company_id", "payroll_payment_executions.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["company_id", "instruction_id"],
            ["payroll_payment_instructions.company_id", "payroll_payment_instructions.id"],
            name="fk_payroll_payment_execution_item_instruction_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("execution_id", "instruction_id", name="uq_payroll_payment_execution_item_instruction"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    execution_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    instruction_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    instruction_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(24), nullable=False)
    provider_safe_reference: Mapped[str | None] = mapped_column(String(120))
    evidence_digest: Mapped[str | None] = mapped_column(String(64))


class PayrollPaymentExecutionEvidenceRecord(Base):
    __tablename__ = "payroll_payment_execution_evidence"
    __table_args__ = (
        CheckConstraint("evidence_type IN ('submission','acknowledgement','settlement','failure','uncertain')", name="ck_payroll_payment_execution_evidence_type"),
        ForeignKeyConstraint(["company_id", "execution_id"], ["payroll_payment_executions.company_id", "payroll_payment_executions.id"], ondelete="RESTRICT"),
        UniqueConstraint("execution_id", "evidence_digest", name="uq_payroll_payment_execution_evidence_digest"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    execution_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(24), nullable=False)
    provider_identity: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_version: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_safe_reference: Mapped[str | None] = mapped_column(String(120))
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    response_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PayrollAccountingPolicyVersion(Base):
    __tablename__ = "payroll_accounting_policy_versions"
    __table_args__ = (
        CheckConstraint("recognition_event IN ('payroll_accrual','payment_release','wage_settlement','tax_remittance','deduction_remittance','return_adjustment','adjustment_applied')", name="ck_payroll_accounting_policy_event"),
        CheckConstraint("lifecycle IN ('draft','approved','superseded','retired')", name="ck_payroll_accounting_policy_lifecycle"),
        CheckConstraint("effective_end IS NULL OR effective_end > effective_start", name="ck_payroll_accounting_policy_interval"),
        UniqueConstraint("company_id", "recognition_event", "policy_version", name="uq_payroll_accounting_policy_version"),
        Index("ix_payroll_accounting_policy_resolution", "company_id", "recognition_event", "lifecycle", "effective_start", "effective_end"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition_version: Mapped[str] = mapped_column(String(80), nullable=False)
    recognition_event: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    effective_start: Mapped[date] = mapped_column(Date, nullable=False)
    effective_end: Mapped[date | None] = mapped_column(Date)
    lifecycle: Mapped[str] = mapped_column(String(16), nullable=False)
    decision_evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supersedes_policy_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("payroll_accounting_policy_versions.id", ondelete="RESTRICT"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PayrollAccountingMappingVersion(Base):
    __tablename__ = "payroll_accounting_mapping_versions"
    __table_args__ = (
        CheckConstraint("recognition_event IN ('payroll_accrual','payment_release','wage_settlement','tax_remittance','deduction_remittance','return_adjustment','adjustment_applied')", name="ck_payroll_accounting_mapping_event"),
        CheckConstraint("posting_side IN ('debit','credit')", name="ck_payroll_accounting_mapping_side"),
        CheckConstraint("lifecycle IN ('draft','approved','superseded','retired')", name="ck_payroll_accounting_mapping_lifecycle"),
        CheckConstraint("effective_end IS NULL OR effective_end > effective_start", name="ck_payroll_accounting_mapping_interval"),
        ForeignKeyConstraint(["company_id", "account_id"], ["accounting_accounts.company_id", "accounting_accounts.id"], ondelete="RESTRICT"),
        UniqueConstraint("company_id", "recognition_event", "component", "mapping_version", name="uq_payroll_accounting_mapping_version"),
        Index("ix_payroll_accounting_mapping_resolution", "company_id", "recognition_event", "component", "lifecycle", "effective_start", "effective_end"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    mapping_version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition_version: Mapped[str] = mapped_column(String(80), nullable=False)
    recognition_event: Mapped[str] = mapped_column(String(32), nullable=False)
    component: Mapped[str] = mapped_column(String(48), nullable=False)
    posting_side: Mapped[str] = mapped_column(String(8), nullable=False)
    account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    effective_start: Mapped[date] = mapped_column(Date, nullable=False)
    effective_end: Mapped[date | None] = mapped_column(Date)
    lifecycle: Mapped[str] = mapped_column(String(16), nullable=False)
    approval_evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    mapping_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supersedes_mapping_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("payroll_accounting_mapping_versions.id", ondelete="RESTRICT"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PayrollAccountingConsumptionRecord(Base):
    """Append-only bridge from a Payroll economic event to native Accounting."""

    __tablename__ = "payroll_accounting_consumptions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "journal_id"],
            ["accounting_journals.company_id", "accounting_journals.id"],
            name="fk_payroll_accounting_consumption_journal_scope",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "lifecycle IN ('prepared','posted','reconciliation_required','superseded','reversed')",
            name="ck_payroll_accounting_consumption_lifecycle",
        ),
        UniqueConstraint("company_id", "candidate_identity", name="uq_payroll_accounting_consumption_identity"),
        UniqueConstraint("company_id", "recognition_event", "source_event_id", name="uq_payroll_accounting_source_consumption"),
        UniqueConstraint("company_id", "journal_id", name="uq_payroll_accounting_consumption_journal"),
        Index("ix_payroll_accounting_consumption_source", "company_id", "source_type", "source_id"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    recognition_event: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    fact_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(32), nullable=False)
    journal_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    journal_version: Mapped[int | None] = mapped_column(Integer)
    prepared_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PayrollPayStatementRecord(Base):
    """Immutable employee-facing projection of approved Payroll evidence."""

    __tablename__ = "payroll_pay_statements"
    __table_args__ = (
        CheckConstraint("lifecycle IN ('created','issued','superseded','voided')", name="ck_payroll_pay_statement_lifecycle"),
        CheckConstraint("payment_status IN ('not_available','pending','acknowledged','partially_settled','settled','failed','unresolved')", name="ck_payroll_pay_statement_payment_status"),
        ForeignKeyConstraint(
            ["company_id", "pay_period_id", "run_id"],
            ["payroll_runs.company_id", "payroll_runs.pay_period_id", "payroll_runs.id"],
            name="fk_payroll_pay_statement_run_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(["company_id", "employee_id"], ["employees.company_id", "employees.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["company_id", "employee_id", "pay_period_id", "gross_result_id"],
            ["payroll_gross_calculation_results.company_id", "payroll_gross_calculation_results.employee_id", "payroll_gross_calculation_results.pay_period_id", "payroll_gross_calculation_results.id"],
            name="fk_payroll_pay_statement_gross_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "employee_id", "pay_period_id", "tax_result_id"],
            ["payroll_tax_deduction_results.company_id", "payroll_tax_deduction_results.employee_id", "payroll_tax_deduction_results.pay_period_id", "payroll_tax_deduction_results.id"],
            name="fk_payroll_pay_statement_tax_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "employee_id", "adjustment_result_id"],
            ["payroll_adjustment_results.company_id", "payroll_adjustment_results.employee_id", "payroll_adjustment_results.id"],
            name="fk_payroll_pay_statement_adjustment_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "employee_id", "reporting_snapshot_id"],
            ["payroll_reporting_snapshots.company_id", "payroll_reporting_snapshots.employee_id", "payroll_reporting_snapshots.id"],
            name="fk_payroll_pay_statement_reporting_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "employee_id", "pay_period_id", "supersedes_statement_id"],
            ["payroll_pay_statements.company_id", "payroll_pay_statements.employee_id", "payroll_pay_statements.pay_period_id", "payroll_pay_statements.id"],
            name="fk_payroll_pay_statement_predecessor_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "statement_identity", name="uq_payroll_pay_statement_identity"),
        UniqueConstraint("company_id", "id", name="uq_payroll_pay_statement_company_id"),
        UniqueConstraint(
            "company_id",
            "employee_id",
            "pay_period_id",
            "id",
            name="uq_payroll_pay_statement_predecessor_scope",
        ),
        UniqueConstraint("company_id", "statement_digest", name="uq_payroll_pay_statement_digest"),
        UniqueConstraint("supersedes_statement_id", name="uq_payroll_pay_statement_successor"),
        Index("ix_payroll_pay_statement_employee_period", "company_id", "employee_id", "pay_period_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    pay_period_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    run_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    gross_result_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    gross_result_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    tax_result_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    tax_result_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    adjustment_result_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    adjustment_digest: Mapped[str | None] = mapped_column(String(64))
    reporting_snapshot_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reporting_digest: Mapped[str | None] = mapped_column(String(64))
    statement_version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition_version: Mapped[str] = mapped_column(String(80), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    payment_status: Mapped[str] = mapped_column(String(24), nullable=False)
    payment_evidence_digest: Mapped[str | None] = mapped_column(String(64))
    content: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    ytd_status: Mapped[str] = mapped_column(String(24), nullable=False)
    statement_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    statement_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(16), nullable=False)
    supersedes_statement_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    issued_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PayrollPayStatementArtifactRecord(Base):
    """Protected render evidence subordinate to an issued pay statement."""
    __tablename__ = "payroll_pay_statement_artifacts"
    __table_args__ = (
        CheckConstraint("lifecycle IN ('generated','retained','superseded','voided')", name="ck_payroll_pay_statement_artifact_lifecycle"),
        ForeignKeyConstraint(["company_id", "statement_id"], ["payroll_pay_statements.company_id", "payroll_pay_statements.id"], ondelete="RESTRICT"),
        UniqueConstraint("company_id", "artifact_identity", name="uq_payroll_pay_statement_artifact_identity"),
        UniqueConstraint("company_id", "storage_reference", name="uq_payroll_pay_statement_artifact_storage"),
        Index("ix_payroll_pay_statement_artifact_statement", "company_id", "statement_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    statement_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    statement_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    render_contract_version: Mapped[str] = mapped_column(String(80), nullable=False)
    template_version: Mapped[str] = mapped_column(String(80), nullable=False)
    renderer_version: Mapped[str] = mapped_column(String(80), nullable=False)
    media_type: Mapped[str] = mapped_column(String(80), nullable=False)
    artifact_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(16), nullable=False)
    retention_state: Mapped[str] = mapped_column(String(24), nullable=False, default="preserve")
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PayrollPayStatementDeliveryRecord(Base):
    """Safe link-only delivery intent; never contains statement contents."""
    __tablename__ = "payroll_pay_statement_deliveries"
    __table_args__ = (
        CheckConstraint("channel IN ('authenticated_web','authenticated_app','email_link','push_link')", name="ck_payroll_pay_statement_delivery_channel"),
        CheckConstraint("lifecycle IN ('prepared','acknowledged','failed','revoked')", name="ck_payroll_pay_statement_delivery_lifecycle"),
        ForeignKeyConstraint(["company_id", "statement_id"], ["payroll_pay_statements.company_id", "payroll_pay_statements.id"], ondelete="RESTRICT"),
        UniqueConstraint("company_id", "delivery_identity", name="uq_payroll_pay_statement_delivery_identity"),
        Index("ix_payroll_pay_statement_delivery_statement", "company_id", "statement_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    statement_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    statement_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    link_target: Mapped[str] = mapped_column(String(256), nullable=False)
    provider_identity: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_version: Mapped[str] = mapped_column(String(40), nullable=False)
    delivery_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    delivery_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(16), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PayrollHistoryCoverageRecord(Base):
    """Approved declaration of complete native or admitted historical coverage."""
    __tablename__ = "payroll_history_coverage"
    __table_args__ = (
        CheckConstraint("lifecycle IN ('draft','approved','superseded','retired')", name="ck_payroll_history_coverage_lifecycle"),
        CheckConstraint("coverage_end >= coverage_start", name="ck_payroll_history_coverage_interval"),
        UniqueConstraint("company_id", "coverage_identity", name="uq_payroll_history_coverage_identity"),
        Index("ix_payroll_history_coverage_resolution", "company_id", "lifecycle", "coverage_start", "coverage_end"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    coverage_start: Mapped[date] = mapped_column(Date, nullable=False)
    coverage_end: Mapped[date] = mapped_column(Date, nullable=False)
    source_authority: Mapped[str] = mapped_column(String(80), nullable=False)
    source_evidence: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    coverage_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PayrollReportingSnapshotRecord(Base):
    """Immutable pay-period, quarter, or year reporting composition."""
    __tablename__ = "payroll_reporting_snapshots"
    __table_args__ = (
        CheckConstraint("period_kind IN ('pay_period','quarter','year')", name="ck_payroll_reporting_period_kind"),
        CheckConstraint("state IN ('authoritative','partial','unavailable','conflicting')", name="ck_payroll_reporting_state"),
        UniqueConstraint("company_id", "report_identity", name="uq_payroll_reporting_identity"),
        UniqueConstraint(
            "company_id",
            "employee_id",
            "id",
            name="uq_payroll_reporting_statement_scope",
        ),
        Index("ix_payroll_reporting_period", "company_id", "period_start", "period_end", "employee_id"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    employee_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    period_identity: Mapped[str] = mapped_column(String(120), nullable=False)
    period_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3))
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    totals: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    source_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    source_digests: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    coverage_evidence_id: Mapped[str | None] = mapped_column(String(128))
    blockers: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    reconciliation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    report_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    report_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    definition_version: Mapped[str] = mapped_column(String(80), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PayrollFilingPackageRecord(Base):
    """Provider-neutral filing evidence; never represents submission."""
    __tablename__ = "payroll_filing_packages"
    __table_args__ = (
        CheckConstraint("state IN ('prepared_not_submitted','superseded','voided')", name="ck_payroll_filing_package_state"),
        UniqueConstraint("company_id", "package_identity", name="uq_payroll_filing_package_identity"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    reporting_snapshot_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("payroll_reporting_snapshots.id", ondelete="RESTRICT"), nullable=False)
    compliance_schema_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("payroll_compliance_schemas.id", ondelete="RESTRICT"))
    reporting_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_id: Mapped[str] = mapped_column(String(128), nullable=False)
    configuration_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    jurisdiction_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    package_type: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    package_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    package_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    supersedes_package_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("payroll_filing_packages.id", ondelete="RESTRICT"))
    amendment_evidence_digest: Mapped[str | None] = mapped_column(String(64))
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PayrollComplianceSchemaRecord(Base):
    """Approved provider-neutral compliance schema/rule authority."""
    __tablename__ = "payroll_compliance_schemas"
    __table_args__ = (
        CheckConstraint("lifecycle IN ('draft','approved','superseded','retired')", name="ck_payroll_compliance_schema_lifecycle"),
        CheckConstraint("quarter IS NULL OR quarter BETWEEN 1 AND 4", name="ck_payroll_compliance_schema_quarter"),
        CheckConstraint("effective_end IS NULL OR effective_end >= effective_start", name="ck_payroll_compliance_schema_interval"),
        UniqueConstraint("company_id", "schema_identity", name="uq_payroll_compliance_schema_identity"),
        Index("ix_payroll_compliance_schema_resolution", "company_id", "jurisdiction_reference", "package_family", "tax_year", "quarter", "lifecycle"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    jurisdiction_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    package_family: Mapped[str] = mapped_column(String(80), nullable=False)
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[int | None] = mapped_column(Integer)
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False)
    required_evidence: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    legal_content_slots: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    effective_start: Mapped[date] = mapped_column(Date, nullable=False)
    effective_end: Mapped[date | None] = mapped_column(Date)
    schema_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PayrollReportingArtifactRecord(Base):
    """Protected render evidence subordinate to reporting/package authority."""
    __tablename__ = "payroll_reporting_artifacts"
    __table_args__ = (
        CheckConstraint("source_type IN ('report','filing_package')", name="ck_payroll_reporting_artifact_source"),
        CheckConstraint("lifecycle IN ('generated','retained','superseded','voided')", name="ck_payroll_reporting_artifact_lifecycle"),
        UniqueConstraint("company_id", "artifact_identity", name="uq_payroll_reporting_artifact_identity"),
        UniqueConstraint("company_id", "storage_reference", name="uq_payroll_reporting_artifact_storage"),
        Index("ix_payroll_reporting_artifact_source", "company_id", "source_type", "source_id"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(24), nullable=False)
    source_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    render_version: Mapped[str] = mapped_column(String(80), nullable=False)
    media_type: Mapped[str] = mapped_column(String(80), nullable=False)
    artifact_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PayrollAdjustmentAuthorityRecord(Base):
    __tablename__ = "payroll_adjustment_authorities"
    __table_args__ = (
        CheckConstraint("classification IN ('pre_payment_payroll_correction','retroactive_earnings','off_cycle_payroll','tax_correction','deduction_correction','payment_return','payment_rejection','payment_reversal','settlement_correction','accounting_adjustment_required')", name="ck_payroll_adjustment_classification"),
        CheckConstraint("lifecycle IN ('draft','under_review','approved','applied_to_successor_authority','rejected','superseded','voided')", name="ck_payroll_adjustment_lifecycle"),
        UniqueConstraint("company_id", "id", name="uq_payroll_adjustment_company_id"),
        UniqueConstraint("company_id", "adjustment_identity", name="uq_payroll_adjustment_identity"),
        UniqueConstraint("company_id", "adjustment_digest", name="uq_payroll_adjustment_digest"),
        UniqueConstraint("supersedes_adjustment_id", name="uq_payroll_adjustment_successor"),
        ForeignKeyConstraint(
            ["company_id", "supersedes_adjustment_id"],
            ["payroll_adjustment_authorities.company_id", "payroll_adjustment_authorities.id"],
            name="fk_payroll_adjustment_predecessor_scope",
            ondelete="RESTRICT",
        ),
        Index("uq_payroll_adjustment_active_subject", "company_id", "source_type", "source_id", "classification", unique=True, postgresql_where=text("lifecycle IN ('draft','under_review','approved')")),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    employee_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    original_pay_period_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    off_cycle_pay_period_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    classification: Mapped[str] = mapped_column(String(48), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    source_type: Mapped[str] = mapped_column(String(48), nullable=False)
    source_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    source_evidence: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    delta_components: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    definition_version: Mapped[str] = mapped_column(String(80), nullable=False)
    adjustment_identity: Mapped[str] = mapped_column(String(96), nullable=False)
    adjustment_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(36), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supersedes_adjustment_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PayrollAdjustmentReviewRecord(Base):
    __tablename__ = "payroll_adjustment_reviews"
    __table_args__ = (
        CheckConstraint("decision IN ('initiated','accepted','rejected','approved')", name="ck_payroll_adjustment_review_decision"),
        ForeignKeyConstraint(["company_id", "adjustment_id"], ["payroll_adjustment_authorities.company_id", "payroll_adjustment_authorities.id"], ondelete="RESTRICT"),
        UniqueConstraint("adjustment_id", "sequence", name="uq_payroll_adjustment_review_sequence"),
        UniqueConstraint("review_digest", name="uq_payroll_adjustment_review_digest"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    adjustment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    safe_note: Mapped[str | None] = mapped_column(Text)
    adjustment_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    review_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PayrollAdjustmentResultRecord(Base):
    __tablename__ = "payroll_adjustment_results"
    __table_args__ = (
        CheckConstraint("lifecycle IN ('calculated','under_review','approved','applied_to_successor_authority','rejected','superseded','voided')", name="ck_payroll_adjustment_result_lifecycle"),
        ForeignKeyConstraint(["company_id", "adjustment_id"], ["payroll_adjustment_authorities.company_id", "payroll_adjustment_authorities.id"], ondelete="RESTRICT"),
        UniqueConstraint("company_id", "id", name="uq_payroll_adjustment_result_company_id"),
        UniqueConstraint(
            "company_id",
            "employee_id",
            "id",
            name="uq_payroll_adjustment_result_statement_scope",
        ),
        UniqueConstraint("company_id", "result_identity", name="uq_payroll_adjustment_result_identity"),
        UniqueConstraint("company_id", "calculation_digest", name="uq_payroll_adjustment_result_digest"),
        UniqueConstraint("supersedes_result_id", name="uq_payroll_adjustment_result_successor"),
        ForeignKeyConstraint(
            ["company_id", "supersedes_result_id"],
            ["payroll_adjustment_results.company_id", "payroll_adjustment_results.id"],
            name="fk_payroll_adjustment_result_predecessor_scope",
            ondelete="RESTRICT",
        ),
        Index("uq_payroll_adjustment_result_active", "company_id", "adjustment_id", unique=True, postgresql_where=text("lifecycle IN ('calculated','under_review','approved')")),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    employee_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    original_pay_period_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    correction_pay_period_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    adjustment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    adjustment_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(48), nullable=False)
    source_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    classification: Mapped[str] = mapped_column(String(48), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    components: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    consequences: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    result_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(80), nullable=False)
    calculation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(40), nullable=False)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supersedes_result_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PayrollAdjustmentResultReviewRecord(Base):
    __tablename__ = "payroll_adjustment_result_reviews"
    __table_args__ = (
        CheckConstraint("decision IN ('initiated','accepted','rejected','approved')", name="ck_payroll_adjustment_result_review_decision"),
        ForeignKeyConstraint(["company_id", "result_id"], ["payroll_adjustment_results.company_id", "payroll_adjustment_results.id"], ondelete="RESTRICT"),
        UniqueConstraint("result_id", "sequence", name="uq_payroll_adjustment_result_review_sequence"),
        UniqueConstraint("review_digest", name="uq_payroll_adjustment_result_review_digest"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    result_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    reviewer_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    safe_note: Mapped[str | None] = mapped_column(Text)
    result_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    review_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PayrollAdjustmentApplicationRecord(Base):
    __tablename__ = "payroll_adjustment_applications"
    __table_args__ = (
        ForeignKeyConstraint(["company_id", "result_id"], ["payroll_adjustment_results.company_id", "payroll_adjustment_results.id"], ondelete="RESTRICT"),
        UniqueConstraint("result_id", "purpose", name="uq_payroll_adjustment_application_purpose"),
        UniqueConstraint("application_digest", name="uq_payroll_adjustment_application_digest"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    result_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    successor_authority_type: Mapped[str] = mapped_column(String(80), nullable=False)
    result_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    authorized_components: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    application_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    applied_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PayrollRemittancePolicyRecord(Base):
    __tablename__ = "payroll_remittance_policies"
    __table_args__ = (
        CheckConstraint("lifecycle IN ('draft','approved','superseded','retired')", name="ck_payroll_remittance_policy_lifecycle"),
        UniqueConstraint("company_id", "classification", "version", name="uq_payroll_remittance_policy_version"),
        UniqueConstraint("company_id", "policy_digest", name="uq_payroll_remittance_policy_digest"),
        UniqueConstraint("company_id", "id", name="uq_payroll_remittance_policy_company_id"),
        Index("ix_payroll_remittance_policy_resolve", "company_id", "classification", "lifecycle", "effective_start", "effective_end"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    classification: Mapped[str] = mapped_column(String(48), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    aggregation_permitted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    due_days_after_period: Mapped[int | None] = mapped_column(Integer)
    destination_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    accounting_consequence: Mapped[str] = mapped_column(String(48), nullable=False)
    effective_start: Mapped[date] = mapped_column(Date, nullable=False)
    effective_end: Mapped[date | None] = mapped_column(Date)
    lifecycle: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PayrollRemittanceDestinationRecord(Base):
    __tablename__ = "payroll_remittance_destinations"
    __table_args__ = (
        CheckConstraint("lifecycle IN ('draft','approved','superseded','revoked','expired')", name="ck_payroll_remittance_destination_lifecycle"),
        UniqueConstraint("company_id", "destination_identity", name="uq_payroll_remittance_destination_identity"),
        UniqueConstraint("company_id", "id", name="uq_payroll_remittance_destination_company_id"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    destination_type: Mapped[str] = mapped_column(String(48), nullable=False)
    jurisdiction_reference: Mapped[str | None] = mapped_column(String(120))
    protected_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    masked_display: Mapped[str] = mapped_column(String(80), nullable=False)
    effective_start: Mapped[date] = mapped_column(Date, nullable=False)
    effective_end: Mapped[date | None] = mapped_column(Date)
    lifecycle: Mapped[str] = mapped_column(String(16), nullable=False)
    destination_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    destination_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PayrollRemittanceObligationRecord(Base):
    __tablename__ = "payroll_remittance_obligations"
    __table_args__ = (
        CheckConstraint("lifecycle IN ('identified','ready_for_review','under_review','approved_for_remittance','instruction_prepared','submission_pending','submitted','provider_acknowledged','settlement_pending','partially_settled','settled','blocked','rejected','failed','uncertain','superseded','voided','returned','reversed')", name="ck_payroll_remittance_obligation_lifecycle"),
        ForeignKeyConstraint(
            ["company_id", "pay_period_id", "payroll_run_id"],
            ["payroll_runs.company_id", "payroll_runs.pay_period_id", "payroll_runs.id"],
            name="fk_payroll_remittance_obligation_run_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "policy_id"],
            ["payroll_remittance_policies.company_id", "payroll_remittance_policies.id"],
            name="fk_payroll_remittance_obligation_policy_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "destination_id"],
            ["payroll_remittance_destinations.company_id", "payroll_remittance_destinations.id"],
            name="fk_payroll_remittance_obligation_destination_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "payroll_run_id", "classification", "supersedes_obligation_id"],
            ["payroll_remittance_obligations.company_id", "payroll_remittance_obligations.payroll_run_id", "payroll_remittance_obligations.classification", "payroll_remittance_obligations.id"],
            name="fk_payroll_remittance_obligation_predecessor_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "id", name="uq_payroll_remittance_obligation_company_id"),
        UniqueConstraint(
            "company_id",
            "payroll_run_id",
            "classification",
            "id",
            name="uq_payroll_remittance_obligation_predecessor_scope",
        ),
        UniqueConstraint("company_id", "obligation_identity", name="uq_payroll_remittance_obligation_identity"),
        UniqueConstraint("company_id", "obligation_digest", name="uq_payroll_remittance_obligation_digest"),
        UniqueConstraint("supersedes_obligation_id", name="uq_payroll_remittance_obligation_successor"),
        Index("uq_payroll_remittance_active_source", "company_id", "payroll_run_id", "classification", unique=True, postgresql_where=text("lifecycle NOT IN ('superseded','voided','returned','reversed')")),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    payroll_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    pay_period_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    classification: Mapped[str] = mapped_column(String(48), nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    contribution_evidence: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    policy_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    policy_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    destination_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    destination_digest: Mapped[str | None] = mapped_column(String(64))
    obligation_start: Mapped[date] = mapped_column(Date, nullable=False)
    obligation_end: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    settled_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal(0))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(32), nullable=False)
    obligation_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    obligation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    supersedes_obligation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PayrollRemittanceReviewRecord(Base):
    __tablename__ = "payroll_remittance_reviews"
    __table_args__ = (ForeignKeyConstraint(["company_id", "obligation_id"], ["payroll_remittance_obligations.company_id", "payroll_remittance_obligations.id"], ondelete="RESTRICT"), UniqueConstraint("obligation_id", "sequence", name="uq_payroll_remittance_review_sequence"), UniqueConstraint("review_digest", name="uq_payroll_remittance_review_digest"))
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    obligation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    safe_note: Mapped[str | None] = mapped_column(Text)
    obligation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    review_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PayrollRemittanceInstructionRecord(Base):
    __tablename__ = "payroll_remittance_instructions"
    __table_args__ = (
        ForeignKeyConstraint(["company_id", "obligation_id"], ["payroll_remittance_obligations.company_id", "payroll_remittance_obligations.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["company_id", "destination_id"],
            ["payroll_remittance_destinations.company_id", "payroll_remittance_destinations.id"],
            name="fk_payroll_remittance_instruction_destination_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "id", name="uq_payroll_remittance_instruction_company_id"),
        UniqueConstraint("obligation_id", name="uq_payroll_remittance_instruction_obligation"),
        UniqueConstraint("instruction_digest", name="uq_payroll_remittance_instruction_digest"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    obligation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    destination_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    provider_identity: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_version: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    instruction_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    instruction_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(32), nullable=False)
    request_digest: Mapped[str | None] = mapped_column(String(64))
    response_digest: Mapped[str | None] = mapped_column(String(64))
    provider_reference: Mapped[str | None] = mapped_column(String(160))
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PayrollRemittanceEvidenceRecord(Base):
    __tablename__ = "payroll_remittance_evidence"
    __table_args__ = (ForeignKeyConstraint(["company_id", "instruction_id"], ["payroll_remittance_instructions.company_id", "payroll_remittance_instructions.id"], ondelete="RESTRICT"), UniqueConstraint("instruction_id", "evidence_digest", name="uq_payroll_remittance_evidence_digest"))
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    instruction_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(24), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    provider_safe_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
