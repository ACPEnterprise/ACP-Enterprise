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


class EngineeringRepositoryAuthorization(Base):
    __tablename__ = "engineering_repository_authorizations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "review_id"],
            [
                "engineering_execution_reviews.company_id",
                "engineering_execution_reviews.id",
            ],
            name="fk_repository_authorizations_review",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["authorized_by_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_repository_authorizations_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "command_id"],
            ["engineering_commands.company_id", "engineering_commands.id"],
            name="fk_repository_authorizations_command_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "execution_id"],
            ["engineering_executions.company_id", "engineering_executions.id"],
            name="fk_repository_authorizations_execution_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "result_id"],
            [
                "engineering_normalized_provider_results.company_id",
                "engineering_normalized_provider_results.id",
            ],
            name="fk_repository_authorizations_result_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "review_decision_id"],
            [
                "engineering_execution_review_decisions.company_id",
                "engineering_execution_review_decisions.id",
            ],
            name="fk_repository_authorizations_decision_company",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "operation_type IN ('create_commit')",
            name="ck_repository_authorizations_operation",
        ),
        CheckConstraint(
            "state IN ('authorized','expired','revoked','consumed')",
            name="ck_repository_authorizations_state",
        ),
        CheckConstraint(
            "expected_base_commit ~ '^[0-9a-f]{40}$'",
            name="ck_repository_authorizations_base_commit",
        ),
        CheckConstraint(
            "length(btrim(expected_branch)) > 0",
            name="ck_repository_authorizations_branch",
        ),
        CheckConstraint(
            "jsonb_array_length(file_boundary) > 0",
            name="ck_repository_authorizations_file_boundary",
        ),
        CheckConstraint(
            "length(authorization_digest) = 64",
            name="ck_repository_authorizations_digest",
        ),
        CheckConstraint(
            "expires_at > authorized_at",
            name="ck_repository_authorizations_expiration",
        ),
        CheckConstraint(
            "version >= 1",
            name="ck_repository_authorizations_version",
        ),
        CheckConstraint(
            "(state = 'revoked') = (revoked_at IS NOT NULL)",
            name="ck_repository_authorizations_revoked",
        ),
        CheckConstraint(
            "(state = 'consumed') = (consumed_at IS NOT NULL)",
            name="ck_repository_authorizations_consumed",
        ),
        UniqueConstraint(
            "company_id",
            "capability_id",
            name="uq_repository_authorizations_capability",
        ),
        UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_repository_authorizations_idempotency",
        ),
        UniqueConstraint(
            "company_id",
            "review_id",
            "operation_type",
            name="uq_repository_authorizations_review_operation",
        ),
        UniqueConstraint(
            "company_id",
            "id",
            name="uq_repository_authorizations_company_id",
        ),
        UniqueConstraint(
            "company_id",
            "id",
            "command_id",
            "execution_id",
            "review_decision_id",
            name="uq_repository_authorizations_operation_scope",
        ),
        Index(
            "ix_repository_authorizations_company_state",
            "company_id",
            "state",
            "expires_at",
            "id",
        ),
        Index(
            "ix_repository_authorizations_company_command",
            "company_id",
            "command_id",
            "authorized_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    capability_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, default=uuid4
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
    execution_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    result_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    review_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    review_decision_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    authorized_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    operation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    file_boundary: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    expected_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    expected_base_commit: Mapped[str] = mapped_column(String(40), nullable=False)
    review_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    authorization_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    authorized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EngineeringRepositoryAuthorizationEvent(Base):
    __tablename__ = "engineering_repository_authorization_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "authorization_id"],
            [
                "engineering_repository_authorizations.company_id",
                "engineering_repository_authorizations.id",
            ],
            name="fk_repository_authorization_events_authorization",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["actor_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_repository_authorization_events_membership",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "event_type IN ('requested','granted','revoked','expired','consumed')",
            name="ck_repository_authorization_events_type",
        ),
        CheckConstraint(
            "state IN ('authorized','expired','revoked','consumed')",
            name="ck_repository_authorization_events_state",
        ),
        CheckConstraint(
            "version >= 1",
            name="ck_repository_authorization_events_version",
        ),
        UniqueConstraint(
            "company_id",
            "authorization_id",
            "version",
            "event_type",
            name="uq_repository_authorization_events_version",
        ),
        Index(
            "ix_repository_authorization_events_company_created",
            "company_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    authorization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
