from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BeaconSignalReviewEventModel(Base):
    __tablename__ = "beacon_signal_review_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "actor_membership_id"],
            ["memberships.company_id", "memberships.id"],
            name="fk_beacon_review_events_actor_membership",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "action IN ('acknowledge','review','snooze')",
            name="ck_beacon_review_events_action",
        ),
        CheckConstraint(
            "(action = 'snooze' AND snooze_until IS NOT NULL "
            "AND snooze_until > action_at) OR "
            "(action <> 'snooze' AND snooze_until IS NULL)",
            name="ck_beacon_review_events_snooze",
        ),
        CheckConstraint(
            "length(evidence_digest) = 64",
            name="ck_beacon_review_events_evidence_digest",
        ),
        CheckConstraint(
            "length(btrim(rule_code)) BETWEEN 3 AND 160",
            name="ck_beacon_review_events_rule_code",
        ),
        CheckConstraint(
            "signal_source IN ('scheduling','jobs','invoices')",
            name="ck_beacon_review_events_signal_source",
        ),
        Index(
            "ix_beacon_review_events_company_condition",
            "company_id",
            "condition_key",
            "action_at",
            "id",
        ),
        Index(
            "ix_beacon_review_events_company_created",
            "company_id",
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
    condition_key: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    signal_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    rule_code: Mapped[str] = mapped_column(String(160), nullable=False)
    signal_source: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_membership_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    action_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    snooze_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
