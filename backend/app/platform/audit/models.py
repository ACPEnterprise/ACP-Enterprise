from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuditRecord(Base):
    __tablename__ = "audit_records"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(action)) > 0", name="ck_audit_records_action_not_blank"
        ),
        CheckConstraint(
            "length(btrim(resource_type)) > 0",
            name="ck_audit_records_resource_type_not_blank",
        ),
        CheckConstraint(
            "outcome IN ('success', 'failure', 'denied')",
            name="ck_audit_records_outcome",
        ),
        Index("ix_audit_records_occurred_at", "occurred_at"),
        Index(
            "ix_audit_records_actor_user_id_occurred_at", "actor_user_id", "occurred_at"
        ),
        Index("ix_audit_records_company_id_occurred_at", "company_id", "occurred_at"),
        Index("ix_audit_records_action_occurred_at", "action", "occurred_at"),
        Index("ix_audit_records_resource", "resource_type", "resource_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    company_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reason_code: Mapped[str | None] = mapped_column(String(100))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, default=uuid4
    )
    details: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
