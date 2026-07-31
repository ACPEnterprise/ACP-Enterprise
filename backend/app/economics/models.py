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
    source_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    allocated_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    residual_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence_status: Mapped[str] = mapped_column(String(12), nullable=False)
    confidence_percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
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
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    measured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
