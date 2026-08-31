from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ControlledExecutionOfferModel(Base):
    __tablename__ = "engineering_controlled_execution_offers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "command_id"],
            ["engineering_commands.company_id", "engineering_commands.id"],
            name="fk_controlled_offers_command",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "execution_id"],
            ["engineering_executions.company_id", "engineering_executions.id"],
            name="fk_controlled_offers_execution",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "lease_id"],
            ["engineering_worker_leases.company_id", "engineering_worker_leases.id"],
            name="fk_controlled_offers_lease",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            name="fk_controlled_offers_worker",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "session_id"],
            [
                "engineering_worker_transport_sessions.company_id",
                "engineering_worker_transport_sessions.id",
            ],
            name="fk_controlled_offers_session",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "command_type IN ('inspect_workspace','execute_code')",
            name="ck_controlled_offers_command_type",
        ),
        CheckConstraint(
            "capability_required = 'engineering.execute'",
            name="ck_controlled_offers_capability",
        ),
        CheckConstraint(
            "state IN ('available','acquired','completed','failed','cancelled','expired')",
            name="ck_controlled_offers_state",
        ),
        CheckConstraint(
            "lease_seconds BETWEEN 30 AND 900", name="ck_controlled_offers_lease"
        ),
        CheckConstraint("version >= 1", name="ck_controlled_offers_version"),
        CheckConstraint(
            "expires_at > created_at", name="ck_controlled_offers_expiration"
        ),
        CheckConstraint(
            "(state = 'available' AND lease_id IS NULL AND worker_id IS NULL "
            "AND session_id IS NULL AND acquired_at IS NULL) OR "
            "(state IN ('acquired','completed','failed') AND lease_id IS NOT NULL "
            "AND worker_id IS NOT NULL AND session_id IS NOT NULL "
            "AND acquired_at IS NOT NULL) OR state IN ('cancelled','expired')",
            name="ck_controlled_offers_acquisition_binding",
        ),
        UniqueConstraint(
            "company_id", "execution_id", name="uq_controlled_offers_execution"
        ),
        UniqueConstraint("company_id", "id", name="uq_controlled_offers_company_id"),
        UniqueConstraint(
            "company_id",
            "id",
            "command_id",
            "execution_id",
            "lease_id",
            "worker_id",
            "session_id",
            name="uq_controlled_offers_result_binding",
        ),
        UniqueConstraint(
            "company_id",
            "id",
            "command_id",
            "execution_id",
            "lease_id",
            "worker_id",
            name="uq_controlled_offers_recovery_binding",
        ),
        Index(
            "ix_controlled_offers_company_state_expiry",
            "company_id",
            "state",
            "expires_at",
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
    command_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    execution_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(100), nullable=False)
    command_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    capability_required: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    lease_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    worker_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    session_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    acquired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ControlledExecutionResultModel(Base):
    __tablename__ = "engineering_controlled_execution_results"
    __table_args__ = (
        ForeignKeyConstraint(
            [
                "company_id",
                "offer_id",
                "command_id",
                "execution_id",
                "lease_id",
                "worker_id",
                "session_id",
            ],
            [
                "engineering_controlled_execution_offers.company_id",
                "engineering_controlled_execution_offers.id",
                "engineering_controlled_execution_offers.command_id",
                "engineering_controlled_execution_offers.execution_id",
                "engineering_controlled_execution_offers.lease_id",
                "engineering_controlled_execution_offers.worker_id",
                "engineering_controlled_execution_offers.session_id",
            ],
            name="fk_controlled_results_offer",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "outcome IN ('succeeded','failed','timed_out','cancelled')",
            name="ck_controlled_results_outcome",
        ),
        CheckConstraint(
            "repository_mutated IN (true,false)",
            name="ck_controlled_results_repository_mutation_boolean",
        ),
        CheckConstraint(
            "completed_at >= started_at", name="ck_controlled_results_timestamps"
        ),
        UniqueConstraint("company_id", "offer_id", name="uq_controlled_results_offer"),
        UniqueConstraint("company_id", "id", name="uq_controlled_results_company_id"),
        Index(
            "ix_controlled_results_company_execution",
            "company_id",
            "execution_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    offer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    command_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    execution_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    lease_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    worker_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    session_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    output: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    error_classification: Mapped[str | None] = mapped_column(String(100))
    repository_mutated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    correlation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
