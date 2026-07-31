from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
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
    amount_minor: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    confidence_status: Mapped[str] = mapped_column(String(12), nullable=False)
    confidence_percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    recorded_at: Mapped[datetime] = mapped_column(
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
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    numerator: Mapped[int] = mapped_column(Integer, nullable=False)
    denominator: Mapped[int] = mapped_column(Integer, nullable=False)
    allocated_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    evidence: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
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
    evidence: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    measured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
