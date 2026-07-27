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


STATES = (
    "'requested','reserved','executing','succeeded','failed','reconciliation_required'"
)


class EngineeringRepositoryOperation(Base):
    __tablename__ = "engineering_repository_operations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "authorization_id"],
            [
                "engineering_repository_authorizations.company_id",
                "engineering_repository_authorizations.id",
            ],
            name="fk_repository_operations_authorization",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["requested_by_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_repository_operations_membership",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "operation_type = 'create_commit'",
            name="ck_repository_operations_type",
        ),
        CheckConstraint(
            f"state IN ({STATES})",
            name="ck_repository_operations_state",
        ),
        CheckConstraint(
            "expected_base_commit ~ '^[0-9a-f]{40}$'",
            name="ck_repository_operations_base_commit",
        ),
        CheckConstraint(
            "resulting_commit_sha IS NULL OR resulting_commit_sha ~ '^[0-9a-f]{40}$'",
            name="ck_repository_operations_result_sha",
        ),
        CheckConstraint(
            "length(boundary_digest) = 64",
            name="ck_repository_operations_boundary_digest",
        ),
        CheckConstraint(
            "jsonb_array_length(file_boundary) > 0",
            name="ck_repository_operations_boundary",
        ),
        CheckConstraint(
            "length(btrim(commit_subject)) BETWEEN 1 AND 120 "
            "AND commit_subject !~ '[\\n\\r]'",
            name="ck_repository_operations_subject",
        ),
        CheckConstraint("version >= 1", name="ck_repository_operations_version"),
        CheckConstraint(
            "(state = 'succeeded') = "
            "(succeeded_at IS NOT NULL AND resulting_commit_sha IS NOT NULL)",
            name="ck_repository_operations_succeeded",
        ),
        CheckConstraint(
            "(state = 'failed') = (failed_at IS NOT NULL)",
            name="ck_repository_operations_failed",
        ),
        CheckConstraint(
            "(state = 'reconciliation_required') = "
            "(reconciliation_required_at IS NOT NULL)",
            name="ck_repository_operations_reconciliation",
        ),
        UniqueConstraint(
            "company_id",
            "authorization_id",
            name="uq_repository_operations_authorization",
        ),
        UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_repository_operations_idempotency",
        ),
        UniqueConstraint(
            "company_id",
            "id",
            name="uq_repository_operations_company_id",
        ),
        Index(
            "ix_repository_operations_company_state",
            "company_id",
            "state",
            "updated_at",
            "id",
        ),
        Index(
            "ix_repository_operations_company_command",
            "company_id",
            "command_id",
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
    authorization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    command_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("engineering_commands.id", ondelete="RESTRICT"),
        nullable=False,
    )
    execution_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("engineering_executions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    review_decision_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("engineering_execution_review_decisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    operation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    commit_subject: Mapped[str] = mapped_column(String(120), nullable=False)
    expected_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    expected_base_commit: Mapped[str] = mapped_column(String(40), nullable=False)
    file_boundary: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    boundary_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    resulting_commit_sha: Mapped[str | None] = mapped_column(String(40))
    failure_classification: Mapped[str | None] = mapped_column(String(80))
    failure_detail: Mapped[str | None] = mapped_column(String(240))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    reserved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    succeeded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reconciliation_required_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EngineeringRepositoryOperationEvent(Base):
    __tablename__ = "engineering_repository_operation_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "operation_id"],
            [
                "engineering_repository_operations.company_id",
                "engineering_repository_operations.id",
            ],
            name="fk_repository_operation_events_operation",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["actor_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_repository_operation_events_membership",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "event_type IN "
            "('requested','reserved','started','succeeded','failed',"
            "'reconciliation_required')",
            name="ck_repository_operation_events_type",
        ),
        CheckConstraint(
            f"state IN ({STATES})",
            name="ck_repository_operation_events_state",
        ),
        CheckConstraint(
            "resulting_commit_sha IS NULL OR resulting_commit_sha ~ '^[0-9a-f]{40}$'",
            name="ck_repository_operation_events_result_sha",
        ),
        CheckConstraint(
            "version >= 1",
            name="ck_repository_operation_events_version",
        ),
        UniqueConstraint(
            "company_id",
            "operation_id",
            "version",
            "event_type",
            name="uq_repository_operation_events_version",
        ),
        Index(
            "ix_repository_operation_events_company_created",
            "company_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    resulting_commit_sha: Mapped[str | None] = mapped_column(String(40))
    failure_classification: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
