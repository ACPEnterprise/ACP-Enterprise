from __future__ import annotations

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
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


ACTIVE_STAGES = (
    "new",
    "contacted",
    "qualified",
    "appointment_needed",
    "scheduled",
    "estimate_follow_up",
    "nurture",
)
ALL_STAGES = (*ACTIVE_STAGES, "won", "lost")


class Lead(Base):
    __tablename__ = "pipeline_leads"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_pipeline_leads_company_branch",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "stage IN ('new','contacted','qualified','appointment_needed',"
            "'scheduled','estimate_follow_up','won','lost','nurture')",
            name="ck_pipeline_leads_stage",
        ),
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('won','lost','nurture')",
            name="ck_pipeline_leads_outcome",
        ),
        CheckConstraint(
            "contact_attempt_count >= 0", name="ck_pipeline_leads_attempts"
        ),
        CheckConstraint("version >= 1", name="ck_pipeline_leads_version"),
        CheckConstraint(
            "attributable_value_minor IS NULL OR attributable_value_minor >= 0",
            name="ck_pipeline_leads_value",
        ),
        CheckConstraint(
            "customer_id IS NOT NULL OR length(btrim(prospect_name)) > 0",
            name="ck_pipeline_leads_subject",
        ),
        CheckConstraint(
            "stage <> 'lost' OR length(btrim(lost_reason)) > 0",
            name="ck_pipeline_leads_lost_reason",
        ),
        UniqueConstraint("company_id", "id", name="uq_pipeline_leads_company_id"),
        Index(
            "ix_pipeline_leads_queue",
            "company_id",
            "branch_id",
            "stage",
            "next_action_due_at",
        ),
        Index(
            "ix_pipeline_leads_assignee",
            "company_id",
            "assigned_user_id",
            "next_action_due_at",
        ),
        Index("ix_pipeline_leads_customer", "company_id", "customer_id", "created_at"),
        Index(
            "uq_pipeline_leads_source_identity",
            "company_id",
            "source_system",
            "source_provider_id",
            unique=True,
            postgresql_where=text("source_provider_id IS NOT NULL"),
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
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT")
    )
    prospect_name: Mapped[str | None] = mapped_column(String(300))
    contact_phone: Mapped[str | None] = mapped_column(String(40))
    contact_email: Mapped[str | None] = mapped_column(String(320))
    lead_source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_detail: Mapped[str | None] = mapped_column(String(300))
    source_system: Mapped[str | None] = mapped_column(String(80))
    source_provider_id: Mapped[str | None] = mapped_column(String(200))
    source_version: Mapped[str | None] = mapped_column(String(80))
    source_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    service_category: Mapped[str | None] = mapped_column(String(120))
    service_need: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    assigned_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    stage: Mapped[str] = mapped_column(String(40), nullable=False, default="new")
    first_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_action_type: Mapped[str | None] = mapped_column(String(80))
    next_action_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    contact_attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    appointment_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("appointments.id", ondelete="RESTRICT")
    )
    job_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="RESTRICT")
    )
    estimate_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("estimates.id", ondelete="RESTRICT")
    )
    outcome: Mapped[str | None] = mapped_column(String(20))
    lost_reason: Mapped[str | None] = mapped_column(String(200))
    attributable_value_minor: Mapped[int | None] = mapped_column(Integer)
    value_currency: Mapped[str | None] = mapped_column(String(3))
    value_authority: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    updated_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class LeadHistory(Base):
    __tablename__ = "pipeline_lead_history"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    lead_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("pipeline_leads.id", ondelete="CASCADE"),
        nullable=False,
    )
    action_type: Mapped[str] = mapped_column(String(80), nullable=False)
    from_stage: Mapped[str | None] = mapped_column(String(40))
    to_stage: Mapped[str | None] = mapped_column(String(40))
    detail: Mapped[str | None] = mapped_column(String(500))
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "lead_id",
            "idempotency_key",
            name="uq_pipeline_history_idempotency",
        ),
        Index("ix_pipeline_lead_history_lead", "company_id", "lead_id", "occurred_at"),
    )
