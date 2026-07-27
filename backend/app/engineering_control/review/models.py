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
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EngineeringExecutionReview(Base):
    __tablename__ = "engineering_execution_reviews"
    __table_args__ = (
        CheckConstraint(
            "state IN ('pending','accepted','rejected')",
            name="ck_engineering_execution_reviews_state",
        ),
        CheckConstraint(
            "length(review_digest) = 64",
            name="ck_engineering_execution_reviews_digest",
        ),
        CheckConstraint(
            "version >= 1",
            name="ck_engineering_execution_reviews_version",
        ),
        UniqueConstraint(
            "company_id",
            "result_id",
            name="uq_engineering_execution_reviews_result",
        ),
        UniqueConstraint(
            "company_id",
            "id",
            name="uq_engineering_execution_reviews_company_id",
        ),
        Index(
            "ix_engineering_execution_reviews_company_state",
            "company_id",
            "state",
            "created_at",
            "id",
        ),
        Index(
            "ix_engineering_execution_reviews_company_command",
            "company_id",
            "command_id",
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
        ForeignKey("engineering_commands.id", ondelete="RESTRICT"),
        nullable=False,
    )
    execution_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("engineering_executions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    composition_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("engineering_execution_compositions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    attempt_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("engineering_provider_execution_attempts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    result_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("engineering_normalized_provider_results.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider_identifier: Mapped[str] = mapped_column(String(100), nullable=False)
    instruction_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    composition_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    review_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EngineeringExecutionReviewDecision(Base):
    __tablename__ = "engineering_execution_review_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "review_id"],
            [
                "engineering_execution_reviews.company_id",
                "engineering_execution_reviews.id",
            ],
            name="fk_engineering_review_decisions_review",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["reviewer_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_engineering_review_decisions_membership",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "decision IN ('accept','reject')",
            name="ck_engineering_review_decisions_decision",
        ),
        CheckConstraint(
            "reason_code IS NULL OR length(btrim(reason_code)) BETWEEN 3 AND 80",
            name="ck_engineering_review_decisions_reason",
        ),
        UniqueConstraint(
            "company_id",
            "review_id",
            name="uq_engineering_review_decisions_review",
        ),
        Index(
            "ix_engineering_review_decisions_company_decided",
            "company_id",
            "decided_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    review_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    reviewer_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    review_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(80))
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
