from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
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


class BusinessFactRecord(Base):
    __tablename__ = "business_economics_facts"
    __table_args__ = (
        CheckConstraint(
            "category IN ('revenue', 'labor', 'materials', 'equipment', 'truck', 'overhead')",
            name="ck_business_economics_facts_category",
        ),
        CheckConstraint(
            "confidence_status IN ('measured', 'estimated', 'unknown')",
            name="ck_business_economics_facts_confidence_status",
        ),
        CheckConstraint(
            "confidence_percentage BETWEEN 0 AND 100",
            name="ck_business_economics_facts_confidence_percentage",
        ),
        CheckConstraint(
            "(amount_minor IS NULL) = (confidence_status = 'unknown')",
            name="ck_business_economics_facts_known_amount",
        ),
        CheckConstraint("version >= 1", name="ck_business_economics_facts_version"),
        CheckConstraint(
            "period_end >= period_start",
            name="ck_business_economics_facts_period",
        ),
        CheckConstraint(
            "accounting_basis IN ('accrual', 'cash', 'operational')",
            name="ck_business_economics_facts_accounting_basis",
        ),
        CheckConstraint(
            "correction_kind IN ('original', 'reversal', 'supersession', 'effective_date')",
            name="ck_business_economics_facts_correction_kind",
        ),
        CheckConstraint(
            "(correction_kind = 'original' AND corrects_fact_id IS NULL) OR "
            "(correction_kind <> 'original' AND corrects_fact_id IS NOT NULL)",
            name="ck_business_economics_facts_correction_reference",
        ),
        UniqueConstraint(
            "company_id",
            "input_digest",
            name="uq_business_economics_facts_input_digest",
        ),
        UniqueConstraint(
            "company_id",
            "subject_type",
            "subject_id",
            "fact_key",
            "period_start",
            "period_end",
            "version",
            name="uq_business_economics_facts_version",
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_business_economics_facts_company_id"
        ),
        Index(
            "ix_business_economics_facts_subject",
            "company_id",
            "subject_type",
            "subject_id",
            "occurred_at",
            "id",
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
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    fact_key: Mapped[str] = mapped_column(String(80), nullable=False)
    amount_minor: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    confidence_status: Mapped[str] = mapped_column(String(12), nullable=False)
    confidence_percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_snapshot: Mapped[list[dict[str, object]]] = mapped_column(
        "evidence", JSONB, nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    measurement_method: Mapped[str] = mapped_column(String(80), nullable=False)
    accounting_basis: Mapped[str] = mapped_column(String(16), nullable=False)
    correction_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    corrects_fact_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_economics_facts.id", ondelete="RESTRICT"),
    )
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EvidenceReferenceRecord(Base):
    __tablename__ = "business_economics_evidence_references"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('business_event', 'source_record', 'allocation', 'reasoning')",
            name="ck_business_economics_evidence_kind",
        ),
        CheckConstraint(
            "length(content_digest) = 64",
            name="ck_business_economics_evidence_digest",
        ),
        UniqueConstraint(
            "company_id",
            "kind",
            "source_system",
            "source_record_type",
            "reference_id",
            "source_version",
            name="uq_business_economics_evidence_source_version",
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_business_economics_evidence_company_id"
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
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    source_system: Mapped[str] = mapped_column(String(80), nullable=False)
    source_record_type: Mapped[str] = mapped_column(String(80), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(160), nullable=False)
    source_version: Mapped[str] = mapped_column(String(80), nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    business_event_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_events.id", ondelete="RESTRICT"),
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class FactEvidenceRecord(Base):
    __tablename__ = "business_economics_fact_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "fact_id"],
            ["business_economics_facts.company_id", "business_economics_facts.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "evidence_id"],
            [
                "business_economics_evidence_references.company_id",
                "business_economics_evidence_references.id",
            ],
            ondelete="RESTRICT",
        ),
    )

    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    fact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    evidence_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)


class AllocationPolicyRecord(Base):
    __tablename__ = "business_economics_allocation_policies"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_business_economics_policies_version"),
        UniqueConstraint(
            "company_id",
            "policy_key",
            "version",
            name="uq_business_economics_policies_version",
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_business_economics_policies_company_id"
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
    policy_key: Mapped[str] = mapped_column(String(80), nullable=False)
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    driver_fact_key: Mapped[str] = mapped_column(String(80), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AllocationRunRecord(Base):
    __tablename__ = "business_economics_allocation_runs"
    __table_args__ = (
        CheckConstraint(
            "source_amount_minor = allocated_amount_minor + residual_amount_minor",
            name="ck_business_economics_allocation_runs_reconcile",
        ),
        CheckConstraint(
            "confidence_status IN ('measured', 'estimated', 'unknown')",
            name="ck_business_economics_allocation_runs_confidence_status",
        ),
        CheckConstraint(
            "confidence_percentage BETWEEN 0 AND 100",
            name="ck_business_economics_allocation_runs_confidence_percentage",
        ),
        UniqueConstraint(
            "company_id",
            "input_digest",
            name="uq_business_economics_allocation_runs_input",
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_business_economics_allocation_runs_company_id"
        ),
        UniqueConstraint(
            "company_id",
            "policy_id",
            "version",
            name="uq_business_economics_allocation_runs_version",
        ),
        ForeignKeyConstraint(
            ["company_id", "policy_id"],
            [
                "business_economics_allocation_policies.company_id",
                "business_economics_allocation_policies.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "source_fact_id"],
            ["business_economics_facts.company_id", "business_economics_facts.id"],
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    policy_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_fact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    period_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_economics_accounting_periods.id", ondelete="RESTRICT"),
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    allocated_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    residual_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence_status: Mapped[str] = mapped_column(String(12), nullable=False)
    confidence_percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    execution_duration_ms: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AllocationRecord(Base):
    __tablename__ = "business_economics_allocations"
    __table_args__ = (
        CheckConstraint(
            "numerator >= 0", name="ck_business_economics_allocations_numerator"
        ),
        CheckConstraint(
            "denominator > 0", name="ck_business_economics_allocations_denominator"
        ),
        CheckConstraint(
            "numerator <= denominator", name="ck_business_economics_allocations_ratio"
        ),
        Index(
            "ix_business_economics_allocations_subject",
            "company_id",
            "subject_type",
            "subject_id",
            "created_at",
            "id",
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
    source_fact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_economics_facts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_economics_allocation_runs.id", ondelete="RESTRICT"),
    )
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    numerator: Mapped[int] = mapped_column(Integer, nullable=False)
    denominator: Mapped[int] = mapped_column(Integer, nullable=False)
    allocated_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    evidence_snapshot: Mapped[list[dict[str, object]]] = mapped_column(
        "evidence", JSONB, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ProfitMeasurementRecord(Base):
    __tablename__ = "business_economics_profit_measurements"
    __table_args__ = (
        CheckConstraint(
            "confidence_status IN ('measured', 'estimated', 'unknown')",
            name="ck_business_economics_profit_measurements_confidence_status",
        ),
        CheckConstraint(
            "confidence_percentage BETWEEN 0 AND 100",
            name="ck_business_economics_profit_measurements_confidence_percentage",
        ),
        CheckConstraint(
            "version >= 1", name="ck_business_economics_profit_measurements_version"
        ),
        CheckConstraint(
            "period_end >= period_start",
            name="ck_business_economics_profit_measurements_period",
        ),
        UniqueConstraint(
            "company_id",
            "subject_type",
            "subject_id",
            "period_start",
            "period_end",
            "version",
            name="uq_business_economics_profit_measurements_version",
        ),
        UniqueConstraint(
            "company_id",
            "input_digest",
            name="uq_business_economics_profit_measurements_input_digest",
        ),
        Index(
            "ix_business_economics_profit_measurements_latest",
            "company_id",
            "subject_type",
            "subject_id",
            "measured_at",
            "id",
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
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    revenue_minor: Mapped[int | None] = mapped_column(BigInteger)
    labor_minor: Mapped[int | None] = mapped_column(BigInteger)
    materials_minor: Mapped[int | None] = mapped_column(BigInteger)
    equipment_minor: Mapped[int | None] = mapped_column(BigInteger)
    truck_minor: Mapped[int | None] = mapped_column(BigInteger)
    overhead_minor: Mapped[int | None] = mapped_column(BigInteger)
    gross_profit_minor: Mapped[int | None] = mapped_column(BigInteger)
    net_profit_minor: Mapped[int | None] = mapped_column(BigInteger)
    confidence_status: Mapped[str] = mapped_column(String(12), nullable=False)
    confidence_percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_snapshot: Mapped[list[dict[str, object]]] = mapped_column(
        "evidence", JSONB, nullable=False
    )
    input_fact_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    input_allocation_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    measured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class RecalculationScopeRecord(Base):
    __tablename__ = "business_economics_recalculation_scopes"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('job', 'branch', 'company')",
            name="ck_business_economics_recalculation_scope_type",
        ),
        Index(
            "ix_business_economics_recalculation_pending",
            "company_id",
            "processed_at",
            "requested_at",
            "id",
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
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    reason_fact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_economics_facts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccountingPeriodRecord(Base):
    __tablename__ = "business_economics_accounting_periods"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'closing', 'closed', 'reopened')",
            name="ck_business_economics_periods_status",
        ),
        CheckConstraint(
            "period_end >= period_start", name="ck_business_economics_periods_range"
        ),
        CheckConstraint("version >= 1", name="ck_business_economics_periods_version"),
        UniqueConstraint(
            "company_id",
            "period_start",
            "period_end",
            name="uq_business_economics_periods_range",
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
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    responsible_owner_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AccountingPeriodHistoryRecord(Base):
    __tablename__ = "business_economics_accounting_period_history"
    __table_args__ = (
        CheckConstraint(
            "to_status IN ('open', 'closing', 'closed', 'reopened')",
            name="ck_business_economics_period_history_status",
        ),
        UniqueConstraint(
            "period_id", "version", name="uq_business_economics_period_history_version"
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
    period_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_economics_accounting_periods.id", ondelete="RESTRICT"),
        nullable=False,
    )
    from_status: Mapped[str | None] = mapped_column(String(12))
    to_status: Mapped[str] = mapped_column(String(12), nullable=False)
    responsible_owner_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AllocationEvidenceRecord(Base):
    __tablename__ = "business_economics_allocation_evidence"

    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_economics_allocation_runs.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    evidence_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_economics_evidence_references.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)


class ReconciliationResultRecord(Base):
    __tablename__ = "business_economics_reconciliation_results"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('source', 'ledger', 'allocation', 'measurement', 'evidence')",
            name="ck_business_economics_reconciliation_kind",
        ),
        CheckConstraint(
            "status IN ('passed', 'failed')",
            name="ck_business_economics_reconciliation_status",
        ),
        UniqueConstraint(
            "company_id",
            "input_digest",
            name="uq_business_economics_reconciliation_input",
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
    period_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_economics_accounting_periods.id", ondelete="RESTRICT"),
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False)
    expected_count: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_count: Mapped[int] = mapped_column(Integer, nullable=False)
    variance_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    details: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    reconciled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ProfitabilityProjectionRecord(Base):
    __tablename__ = "business_economics_profitability_projections"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('job', 'branch', 'company')",
            name="ck_business_economics_projections_scope",
        ),
        UniqueConstraint(
            "company_id",
            "scope_type",
            "scope_id",
            "period_start",
            "period_end",
            "version",
            name="uq_business_economics_projections_version",
        ),
        UniqueConstraint(
            "company_id", "input_digest", name="uq_business_economics_projections_input"
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
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3))
    measurement_count: Mapped[int] = mapped_column(Integer, nullable=False)
    values: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    confidence_status: Mapped[str] = mapped_column(String(12), nullable=False)
    confidence_percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    input_measurement_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class OperationalMetricRecord(Base):
    __tablename__ = "business_economics_operational_metrics"
    __table_args__ = (
        CheckConstraint(
            "name IN ('pending_recalculations', 'allocation_execution_ms', 'materialization_duration_ms', 'reconciliation_failures', 'stale_measurements', 'incomplete_periods')",
            name="ck_business_economics_metrics_name",
        ),
        Index(
            "ix_business_economics_metrics_company_observed",
            "company_id",
            "observed_at",
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
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    labels: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
