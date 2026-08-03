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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EngineeringCommandEcidSequence(Base):
    __tablename__ = "engineering_command_ecid_sequences"
    __table_args__ = (
        CheckConstraint(
            "sequence_year >= 2020",
            name="ck_engineering_command_ecid_sequences_year",
        ),
        CheckConstraint(
            "last_value >= 0",
            name="ck_engineering_command_ecid_sequences_last_value",
        ),
    )

    sequence_year: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=False
    )
    last_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class EngineeringCommand(Base):
    __tablename__ = "engineering_commands"
    __table_args__ = (
        ForeignKeyConstraint(
            ["requested_by_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_engineering_commands_requesting_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["approved_by_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_engineering_commands_approving_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["canceled_by_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_engineering_commands_canceling_membership",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "ecid ~ '^ECID-[0-9]{4}-[0-9]{6,}$'",
            name="ck_engineering_commands_ecid_format",
        ),
        CheckConstraint(
            "length(btrim(command_type)) > 0",
            name="ck_engineering_commands_type_not_blank",
        ),
        CheckConstraint(
            "length(btrim(owner_instruction)) > 0",
            name="ck_engineering_commands_instruction_not_blank",
        ),
        CheckConstraint(
            "length(btrim(instruction_digest)) > 0",
            name="ck_engineering_commands_instruction_digest_not_blank",
        ),
        CheckConstraint(
            "length(btrim(repository_key)) > 0",
            name="ck_engineering_commands_repository_not_blank",
        ),
        CheckConstraint(
            "length(btrim(expected_branch)) > 0",
            name="ck_engineering_commands_branch_not_blank",
        ),
        CheckConstraint(
            "expected_head ~ '^[0-9a-f]{40}$'",
            name="ck_engineering_commands_expected_head",
        ),
        CheckConstraint(
            "length(btrim(idempotency_key)) > 0",
            name="ck_engineering_commands_idempotency_not_blank",
        ),
        CheckConstraint(
            "length(btrim(request_digest)) > 0",
            name="ck_engineering_commands_request_digest_not_blank",
        ),
        CheckConstraint(
            "approval_state IN "
            "('awaiting_approval','approved','rejected','canceled','expired')",
            name="ck_engineering_commands_approval_state",
        ),
        CheckConstraint(
            "execution_state = 'execution_not_connected'",
            name="ck_engineering_commands_execution_state",
        ),
        CheckConstraint("version >= 1", name="ck_engineering_commands_version"),
        CheckConstraint(
            "expires_at > created_at",
            name="ck_engineering_commands_expiration",
        ),
        CheckConstraint(
            "updated_at >= created_at",
            name="ck_engineering_commands_updated_at",
        ),
        CheckConstraint(
            "(approved_at IS NULL) = (approved_by_user_id IS NULL)",
            name="ck_engineering_commands_approval_actor",
        ),
        CheckConstraint(
            "approval_state <> 'approved' OR approved_at IS NOT NULL",
            name="ck_engineering_commands_approved_state",
        ),
        CheckConstraint(
            "(canceled_at IS NULL) = (canceled_by_user_id IS NULL)",
            name="ck_engineering_commands_cancellation_actor",
        ),
        CheckConstraint(
            "approval_state <> 'canceled' OR canceled_at IS NOT NULL",
            name="ck_engineering_commands_canceled_state",
        ),
        CheckConstraint(
            "failure_code IS NULL OR length(btrim(failure_code)) > 0",
            name="ck_engineering_commands_failure_not_blank",
        ),
        CheckConstraint(
            "cancellation_reason_code IS NULL OR "
            "length(btrim(cancellation_reason_code)) > 0",
            name="ck_engineering_commands_cancellation_reason_not_blank",
        ),
        CheckConstraint(
            "result_reference IS NULL OR length(btrim(result_reference)) > 0",
            name="ck_engineering_commands_result_reference_not_blank",
        ),
        UniqueConstraint("ecid", name="uq_engineering_commands_ecid"),
        UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_engineering_commands_company_idempotency",
        ),
        UniqueConstraint(
            "company_id",
            "id",
            name="uq_engineering_commands_company_id_capacity",
        ),
        UniqueConstraint(
            "company_id",
            "id",
            "ecid",
            "instruction_digest",
            name="uq_engineering_commands_company_id_ecid_digest",
        ),
        Index(
            "ix_engineering_commands_company_created",
            "company_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_engineering_commands_company_approval",
            "company_id",
            "approval_state",
            "created_at",
            "id",
        ),
        Index(
            "ix_engineering_commands_company_execution",
            "company_id",
            "execution_state",
            "created_at",
            "id",
        ),
        Index(
            "ix_engineering_commands_company_repository",
            "company_id",
            "repository_key",
            "created_at",
            "id",
        ),
        Index(
            "ix_engineering_commands_approved_queue",
            "company_id",
            "repository_key",
            "approved_at",
            "created_at",
            "id",
            postgresql_where=text(
                "approval_state = 'approved' "
                "AND execution_state = 'execution_not_connected'"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    ecid: Mapped[str] = mapped_column(String(32), nullable=False)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "companies.id",
            name="fk_engineering_commands_company_id_companies",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    command_type: Mapped[str] = mapped_column(String(80), nullable=False)
    owner_instruction: Mapped[str] = mapped_column(Text, nullable=False)
    instruction_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    repository_key: Mapped[str] = mapped_column(String(80), nullable=False)
    expected_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    expected_head: Mapped[str] = mapped_column(String(40), nullable=False)
    requested_code_changes: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    approval_state: Mapped[str] = mapped_column(
        String(24), nullable=False, default="awaiting_approval"
    )
    execution_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="execution_not_connected"
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, default=uuid4
    )
    failure_code: Mapped[str | None] = mapped_column(String(100))
    cancellation_reason_code: Mapped[str | None] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    canceled_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    result_reference: Mapped[str | None] = mapped_column(String(255))


class EngineeringCommandEvent(Base):
    __tablename__ = "engineering_command_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "command_id", "ecid", "instruction_digest"],
            [
                "engineering_commands.company_id",
                "engineering_commands.id",
                "engineering_commands.ecid",
                "engineering_commands.instruction_digest",
            ],
            name="fk_engineering_command_events_command",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["actor_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_engineering_command_events_actor_membership",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "ecid ~ '^ECID-[0-9]{4}-[0-9]{6,}$'",
            name="ck_engineering_command_events_ecid_format",
        ),
        CheckConstraint(
            "length(btrim(instruction_digest)) > 0",
            name="ck_engineering_command_events_instruction_digest_not_blank",
        ),
        CheckConstraint(
            "sequence_number >= 1",
            name="ck_engineering_command_events_sequence",
        ),
        CheckConstraint(
            "length(btrim(event_type)) > 0",
            name="ck_engineering_command_events_type_not_blank",
        ),
        CheckConstraint(
            "prior_approval_state IS NULL OR prior_approval_state IN "
            "('awaiting_approval','approved','rejected','canceled','expired')",
            name="ck_engineering_command_events_prior_approval",
        ),
        CheckConstraint(
            "new_approval_state IS NULL OR new_approval_state IN "
            "('awaiting_approval','approved','rejected','canceled','expired')",
            name="ck_engineering_command_events_new_approval",
        ),
        CheckConstraint(
            "prior_execution_state IS NULL OR "
            "prior_execution_state = 'execution_not_connected'",
            name="ck_engineering_command_events_prior_execution",
        ),
        CheckConstraint(
            "new_execution_state IS NULL OR "
            "new_execution_state = 'execution_not_connected'",
            name="ck_engineering_command_events_new_execution",
        ),
        CheckConstraint(
            "reason_code IS NULL OR length(btrim(reason_code)) > 0",
            name="ck_engineering_command_events_reason_not_blank",
        ),
        CheckConstraint(
            "created_at >= occurred_at",
            name="ck_engineering_command_events_created_at",
        ),
        UniqueConstraint(
            "command_id",
            "sequence_number",
            name="uq_engineering_command_events_command_sequence",
        ),
        Index(
            "ix_engineering_command_events_command_sequence",
            "company_id",
            "command_id",
            "sequence_number",
            "id",
        ),
        Index(
            "ix_engineering_command_events_company_occurred",
            "company_id",
            "occurred_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    command_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    ecid: Mapped[str] = mapped_column(String(32), nullable=False)
    instruction_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    prior_approval_state: Mapped[str | None] = mapped_column(String(24))
    new_approval_state: Mapped[str | None] = mapped_column(String(24))
    prior_execution_state: Mapped[str | None] = mapped_column(String(32))
    new_execution_state: Mapped[str | None] = mapped_column(String(32))
    actor_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reason_code: Mapped[str | None] = mapped_column(String(100))
    event_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    correlation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, default=uuid4
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
