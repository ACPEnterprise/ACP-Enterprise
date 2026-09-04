from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
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


class EngineeringExecution(Base):
    __tablename__ = "engineering_executions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "command_id", "ecid", "instruction_digest"],
            [
                "engineering_commands.company_id",
                "engineering_commands.id",
                "engineering_commands.ecid",
                "engineering_commands.instruction_digest",
            ],
            name="fk_engineering_executions_command",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["requested_by_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_engineering_executions_requesting_membership",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "length(btrim(provider_identifier)) > 0",
            name="ck_engineering_executions_provider_not_blank",
        ),
        CheckConstraint(
            "state IN ('execution_not_connected','queued','starting','running',"
            "'completed','failed','cancelled')",
            name="ck_engineering_executions_state",
        ),
        CheckConstraint(
            "status IN ('disconnected','queued','starting','running','succeeded',"
            "'failed','cancelled')",
            name="ck_engineering_executions_status",
        ),
        CheckConstraint("version >= 1", name="ck_engineering_executions_version"),
        CheckConstraint(
            "updated_at >= created_at",
            name="ck_engineering_executions_updated_at",
        ),
        CheckConstraint(
            "(started_at IS NULL AND "
            "(finished_at IS NULL OR "
            "(state IN ('failed','cancelled') AND finished_at >= requested_at))) "
            "OR (started_at IS NOT NULL AND started_at >= requested_at AND "
            "(finished_at IS NULL OR finished_at >= started_at))",
            name="ck_engineering_executions_timestamps",
        ),
        CheckConstraint(
            "failure_classification IS NULL OR "
            "length(btrim(failure_classification)) > 0",
            name="ck_engineering_executions_failure_not_blank",
        ),
        UniqueConstraint(
            "company_id", "command_id", name="uq_engineering_executions_company_command"
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_engineering_executions_company_id"
        ),
        Index(
            "ix_engineering_executions_company_created",
            "company_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_engineering_executions_company_state",
            "company_id",
            "state",
            "created_at",
            "id",
        ),
        Index(
            "ix_engineering_executions_command",
            "company_id",
            "command_id",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    scheduler_delegation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("engineering_scheduler_delegations.id", ondelete="RESTRICT"),
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "companies.id",
            name="fk_engineering_executions_company_id_companies",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    command_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    ecid: Mapped[str] = mapped_column(String(32), nullable=False)
    instruction_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    provider_identifier: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    evidence_summary: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    validation_summary: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    output_references: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    failure_classification: Mapped[str | None] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
