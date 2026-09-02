"""Immutable persistence for policy-neutral operational measurement packets."""

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
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


class OperationalMeasurementSnapshot(Base):
    __tablename__ = "economics_operational_measurement_snapshots"
    __table_args__ = (
        CheckConstraint("period_end >= period_start", name="ck_eco_measurement_period"),
        CheckConstraint(
            "(predecessor_snapshot_id IS NULL AND correction_reason IS NULL) OR "
            "(predecessor_snapshot_id IS NOT NULL AND length(btrim(correction_reason)) > 0)",
            name="ck_eco_measurement_correction",
        ),
        UniqueConstraint(
            "company_id", "snapshot_digest", name="uq_eco_measurement_snapshot_digest"
        ),
        UniqueConstraint("company_id", "id", name="uq_eco_measurement_company_id"),
        UniqueConstraint(
            "predecessor_snapshot_id", name="uq_eco_measurement_successor"
        ),
        ForeignKeyConstraint(
            ("company_id", "predecessor_snapshot_id"),
            (
                "economics_operational_measurement_snapshots.company_id",
                "economics_operational_measurement_snapshots.id",
            ),
            ondelete="RESTRICT",
        ),
        Index(
            "ix_eco_measurement_period",
            "company_id",
            "branch_id",
            "period_start",
            "period_end",
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
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    contract_version: Mapped[str] = mapped_column(String(80), nullable=False)
    facts: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    attribution: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    source_matrix: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False
    )
    completeness: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    snapshot_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    predecessor_snapshot_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
    )
    correction_reason: Mapped[str | None] = mapped_column(Text)
    source_version_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
