from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MutationReceipt(Base):
    """Tenant-scoped durable authority for one logical API mutation."""

    __tablename__ = "platform_mutation_receipts"
    __table_args__ = (
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
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    actor_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
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
