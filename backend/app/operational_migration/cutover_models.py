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
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


PARENT_TYPES = (
    "('customer','service_location','job','appointment','estimate','invoice')"
)


class MigrationHistoryEntry(Base):
    __tablename__ = "operational_migration_history_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_migration_history_branch_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["first_run_id", "company_id", "branch_id"],
            [
                "operational_migration_runs.id",
                "operational_migration_runs.company_id",
                "operational_migration_runs.branch_id",
            ],
            name="fk_migration_history_first_run_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            name="fk_migration_history_employee_scope",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "entry_type IN ('note','activity')",
            name="ck_migration_history_entry_type",
        ),
        CheckConstraint(
            f"parent_type IN {PARENT_TYPES}",
            name="ck_migration_history_parent_type",
        ),
        CheckConstraint(
            "attribution_status IN ('resolved','unresolved','not_provided')",
            name="ck_migration_history_attribution",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "source_id_sha256",
            name="uq_migration_history_source_identity",
        ),
        Index(
            "ix_migration_history_parent",
            "company_id",
            "parent_type",
            "parent_id",
            "occurred_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_system: Mapped[str] = mapped_column(String(80), nullable=False)
    source_id_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_type: Mapped[str] = mapped_column(String(30), nullable=False)
    parent_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    employee_source_ref_sha256: Mapped[str | None] = mapped_column(String(64))
    employee_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    attribution_status: Mapped[str] = mapped_column(String(20), nullable=False)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    activity_category: Mapped[str] = mapped_column(String(64), nullable=False)
    supported_tags: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    normalized_attributes: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    unsupported_attribute_keys: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    external_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    first_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class MigrationArtifact(Base):
    __tablename__ = "operational_migration_artifacts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_migration_artifacts_branch_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["first_run_id", "company_id", "branch_id"],
            [
                "operational_migration_runs.id",
                "operational_migration_runs.company_id",
                "operational_migration_runs.branch_id",
            ],
            name="fk_migration_artifact_first_run_scope",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"parent_type IN {PARENT_TYPES}",
            name="ck_migration_artifacts_parent_type",
        ),
        CheckConstraint(
            "artifact_category IN ('attachment','document','photo','other')",
            name="ck_migration_artifacts_category",
        ),
        CheckConstraint(
            "retrieval_state IN ('pending','available','unavailable')",
            name="ck_migration_artifacts_retrieval",
        ),
        CheckConstraint(
            "transfer_state IN ('pending','transferred','failed','not_required')",
            name="ck_migration_artifacts_transfer",
        ),
        CheckConstraint(
            "validation_state IN ('pending','valid','invalid','not_validated')",
            name="ck_migration_artifacts_validation",
        ),
        CheckConstraint(
            "byte_size IS NULL OR byte_size >= 0",
            name="ck_migration_artifacts_size",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_migration_artifacts_attempts",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "source_id_sha256",
            name="uq_migration_artifacts_source_identity",
        ),
        Index(
            "ix_migration_artifacts_parent",
            "company_id",
            "parent_type",
            "parent_id",
        ),
        Index(
            "ix_migration_artifacts_readiness",
            "company_id",
            "branch_id",
            "required_for_cutover",
            "transfer_state",
            "validation_state",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_system: Mapped[str] = mapped_column(String(80), nullable=False)
    source_id_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_type: Mapped[str] = mapped_column(String(30), nullable=False)
    parent_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    artifact_category: Mapped[str] = mapped_column(String(20), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    media_type: Mapped[str | None] = mapped_column(String(127))
    byte_size: Mapped[int | None] = mapped_column(Integer)
    source_checksum: Mapped[str | None] = mapped_column(String(128))
    acp_checksum: Mapped[str | None] = mapped_column(String(128))
    retrieval_state: Mapped[str] = mapped_column(String(20), nullable=False)
    transfer_state: Mapped[str] = mapped_column(String(20), nullable=False)
    validation_state: Mapped[str] = mapped_column(String(20), nullable=False)
    failure_classification: Mapped[str | None] = mapped_column(String(80))
    retry_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    required_for_cutover: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    first_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class MigrationArtifactAttempt(Base):
    __tablename__ = "operational_migration_artifact_attempts"
    __table_args__ = (
        UniqueConstraint(
            "artifact_id",
            "attempt_number",
            name="uq_migration_artifact_attempt_number",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    artifact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operational_migration_artifacts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operational_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    failure_classification: Mapped[str | None] = mapped_column(String(80))
    retry_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class MigrationRecordOutcome(Base):
    __tablename__ = "operational_migration_record_outcomes"
    __table_args__ = (
        CheckConstraint(
            "disposition IN ('accepted','rejected','duplicate','unresolved','skipped')",
            name="ck_migration_record_outcomes_disposition",
        ),
        UniqueConstraint(
            "run_id",
            "entity_type",
            "source_id_sha256",
            name="uq_migration_record_outcomes_identity",
        ),
        Index(
            "ix_migration_record_outcomes_run_disposition",
            "run_id",
            "disposition",
            "entity_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operational_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    disposition: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(80))
    retry_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parent_linked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class MigrationPhaseCompletion(Base):
    __tablename__ = "operational_migration_phase_completions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_migration_phase_completion_branch_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["supporting_run_id", "company_id", "branch_id"],
            [
                "operational_migration_runs.id",
                "operational_migration_runs.company_id",
                "operational_migration_runs.branch_id",
            ],
            name="fk_migration_phase_supporting_run_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "branch_id",
            "phase_code",
            name="uq_migration_phase_completion",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    phase_code: Mapped[str] = mapped_column(String(40), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    dry_run_completed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    import_completed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    idempotent_rerun_validated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    supporting_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class MigrationCutoverAssessment(Base):
    __tablename__ = "operational_migration_cutover_assessments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_migration_cutover_assessment_branch_scope",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "projected_status IN ('ready_for_owner_review','not_ready')",
            name="ck_migration_cutover_assessment_status",
        ),
        Index(
            "ix_migration_cutover_assessment_latest",
            "company_id",
            "branch_id",
            "evaluated_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    evaluated_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    projected_status: Mapped[str] = mapped_column(String(40), nullable=False)
    ready: Mapped[bool] = mapped_column(Boolean, nullable=False)
    blocker_codes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    facts: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class MigrationAuditSummary(Base):
    __tablename__ = "operational_migration_audit_summaries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_migration_audit_summary_branch_scope",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "completion_status IN ('completed','completed_with_exceptions','incomplete')",
            name="ck_migration_audit_summary_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    assessment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operational_migration_cutover_assessments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_descriptor_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    completion_status: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_counts: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    artifact_outcomes: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    reconciliation_differences: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    unresolved_categories: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    run_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    period_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
