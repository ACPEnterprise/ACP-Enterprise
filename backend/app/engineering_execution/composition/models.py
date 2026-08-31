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


class ExecutionComposition(Base):
    __tablename__ = "engineering_execution_compositions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "execution_id", "command_id"],
            [
                "engineering_executions.company_id",
                "engineering_executions.id",
                "engineering_executions.command_id",
            ],
            name="fk_execution_compositions_execution_command",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            name="fk_execution_compositions_worker",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "lease_id"],
            ["engineering_worker_leases.company_id", "engineering_worker_leases.id"],
            name="fk_execution_compositions_lease",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "state IN ('created','expired','revoked')",
            name="ck_execution_compositions_state",
        ),
        CheckConstraint("version >= 1", name="ck_execution_compositions_version"),
        CheckConstraint(
            "length(btrim(provider_identifier)) > 0",
            name="ck_execution_compositions_provider",
        ),
        CheckConstraint(
            "length(composition_digest) = 64",
            name="ck_execution_compositions_digest",
        ),
        CheckConstraint(
            "expected_head ~ '^[0-9a-f]{40}$'",
            name="ck_execution_compositions_expected_head",
        ),
        CheckConstraint(
            "expires_at > created_at",
            name="ck_execution_compositions_expiration",
        ),
        UniqueConstraint(
            "company_id",
            "execution_id",
            "lease_id",
            name="uq_execution_compositions_execution_lease",
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_execution_compositions_company_id"
        ),
        Index(
            "ix_execution_compositions_company_state",
            "company_id",
            "state",
            "created_at",
            "id",
        ),
        Index(
            "ix_execution_compositions_company_execution",
            "company_id",
            "execution_id",
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
    command_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    execution_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    worker_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    lease_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    provider_identifier: Mapped[str] = mapped_column(String(100), nullable=False)
    required_capabilities: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    effective_capabilities: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    approved_code_changes: Mapped[bool] = mapped_column(Boolean, nullable=False)
    repository_key: Mapped[str] = mapped_column(String(100), nullable=False)
    expected_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    expected_head: Mapped[str] = mapped_column(String(40), nullable=False)
    instruction_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    composition_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CompositionReceipt(Base):
    __tablename__ = "engineering_composition_receipts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "composition_id"],
            [
                "engineering_execution_compositions.company_id",
                "engineering_execution_compositions.id",
            ],
            name="fk_composition_receipts_composition",
            ondelete="RESTRICT",
        ),
        CheckConstraint("status = 'accepted'", name="ck_composition_receipts_status"),
        CheckConstraint("version = 1", name="ck_composition_receipts_version"),
        CheckConstraint(
            "expires_at > created_at", name="ck_composition_receipts_expiration"
        ),
        CheckConstraint(
            "length(btrim(integrity_method)) > 0",
            name="ck_composition_receipts_integrity_method",
        ),
        UniqueConstraint(
            "company_id",
            "composition_id",
            name="uq_composition_receipts_composition",
        ),
        Index(
            "ix_composition_receipts_company_execution",
            "company_id",
            "execution_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    composition_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    execution_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    worker_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    lease_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    provider_identifier: Mapped[str] = mapped_column(String(100), nullable=False)
    instruction_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    composition_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    integrity_method: Mapped[str] = mapped_column(String(50), nullable=False)
    integrity_key_reference: Mapped[str | None] = mapped_column(String(200))
    integrity_proof: Mapped[str | None] = mapped_column(String(4096))


class ProviderExecutionAttempt(Base):
    __tablename__ = "engineering_provider_execution_attempts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "composition_id"],
            [
                "engineering_execution_compositions.company_id",
                "engineering_execution_compositions.id",
            ],
            name="fk_provider_attempts_composition",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "state IN ('prepared','starting','running','completed','failed',"
            "'cancelled','timed_out','quarantined')",
            name="ck_provider_attempts_state",
        ),
        CheckConstraint("attempt_ordinal >= 1", name="ck_provider_attempts_ordinal"),
        CheckConstraint("version >= 1", name="ck_provider_attempts_version"),
        UniqueConstraint(
            "company_id",
            "composition_id",
            "attempt_ordinal",
            name="uq_provider_attempts_composition_ordinal",
        ),
        UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_provider_attempts_idempotency",
        ),
        UniqueConstraint("company_id", "id", name="uq_provider_attempts_company_id"),
        Index(
            "ix_provider_attempts_company_state",
            "company_id",
            "state",
            "prepared_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    composition_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    worker_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    lease_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    provider_identifier: Mapped[str] = mapped_column(String(100), nullable=False)
    attempt_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    prepared_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_classification: Mapped[str | None] = mapped_column(String(100))
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    cancellation_acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ProviderProgressEvent(Base):
    __tablename__ = "engineering_provider_progress_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "attempt_id"],
            [
                "engineering_provider_execution_attempts.company_id",
                "engineering_provider_execution_attempts.id",
            ],
            name="fk_provider_progress_attempt",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "phase IN ('preparing','starting','executing','validating','finalizing')",
            name="ck_provider_progress_phase",
        ),
        CheckConstraint("sequence_number >= 1", name="ck_provider_progress_sequence"),
        CheckConstraint(
            "percentage IS NULL OR percentage BETWEEN 0 AND 100",
            name="ck_provider_progress_percentage",
        ),
        CheckConstraint(
            "length(btrim(message_code)) BETWEEN 1 AND 100",
            name="ck_provider_progress_message_code",
        ),
        CheckConstraint(
            "summary IS NULL OR length(summary) <= 500",
            name="ck_provider_progress_summary",
        ),
        UniqueConstraint(
            "company_id",
            "attempt_id",
            "sequence_number",
            name="uq_provider_progress_attempt_sequence",
        ),
        Index(
            "ix_provider_progress_company_attempt",
            "company_id",
            "attempt_id",
            "sequence_number",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    attempt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    phase: Mapped[str] = mapped_column(String(30), nullable=False)
    message_code: Mapped[str] = mapped_column(String(100), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(500))
    percentage: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class NormalizedProviderResult(Base):
    __tablename__ = "engineering_normalized_provider_results"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "id", name="uq_normalized_results_company_id"
        ),
        ForeignKeyConstraint(
            ["company_id", "attempt_id"],
            [
                "engineering_provider_execution_attempts.company_id",
                "engineering_provider_execution_attempts.id",
            ],
            name="fk_normalized_results_attempt",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "composition_id"],
            [
                "engineering_execution_compositions.company_id",
                "engineering_execution_compositions.id",
            ],
            name="fk_normalized_results_composition",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('succeeded','failed','cancelled')",
            name="ck_normalized_results_status",
        ),
        CheckConstraint(
            "disposition IN ('accepted','rejected','quarantined')",
            name="ck_normalized_results_disposition",
        ),
        CheckConstraint(
            "repository_mutated = false",
            name="ck_normalized_results_repository_not_mutated",
        ),
        CheckConstraint(
            "disposition = 'accepted' OR length(btrim(disposition_reason)) > 0",
            name="ck_normalized_results_reason",
        ),
        UniqueConstraint(
            "company_id", "attempt_id", name="uq_normalized_results_attempt"
        ),
        Index(
            "ix_normalized_results_company_disposition",
            "company_id",
            "disposition",
            "received_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    attempt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    composition_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence_summary: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    validation_summary: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    output_references: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    failure_classification: Mapped[str | None] = mapped_column(String(100))
    repository_mutated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    disposition: Mapped[str] = mapped_column(String(20), nullable=False)
    disposition_reason: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
