from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MutationReceipt(Base):
    """Tenant-scoped durable authority for one logical API mutation."""

    __tablename__ = "platform_mutation_receipts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_platform_mutation_receipts_branch_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id", "operation", "idempotency_key",
            name="uq_platform_mutation_receipts_company_operation_key",
        ),
        CheckConstraint(
            "state IN ('in_progress', 'completed', 'reconciliation_required')",
            name="ck_platform_mutation_receipts_state",
        ),
        CheckConstraint(
            "retention_class IN ('transport', 'operational', 'financial_audit')",
            name="ck_platform_mutation_receipts_retention_class",
        ),
        CheckConstraint(
            "length(request_digest) = 64",
            name="ck_platform_mutation_receipts_request_digest",
        ),
        CheckConstraint(
            "response_status IS NULL OR response_status BETWEEN 100 AND 599",
            name="ck_platform_mutation_receipts_response_status",
        ),
        CheckConstraint(
            "state <> 'completed' OR (result_type IS NOT NULL AND result_id IS NOT NULL "
            "AND response_status IS NOT NULL AND completed_at IS NOT NULL)",
            name="ck_platform_mutation_receipts_completed_result",
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
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    operation: Mapped[str] = mapped_column(String(160), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="in_progress")
    result_type: Mapped[str | None] = mapped_column(String(120))
    result_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    response_status: Mapped[int | None]
    retention_class: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
