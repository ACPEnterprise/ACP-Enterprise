from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.platform.company.models import Company
    from app.platform.users.models import User


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PendingEmailChange(Base):
    __tablename__ = "pending_email_changes"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(proposed_normalized_email)) > 0 "
            "AND proposed_normalized_email = lower(btrim(proposed_normalized_email))",
            name="ck_pending_email_changes_normalized_email",
        ),
        CheckConstraint(
            "proposed_display_email IS NULL "
            "OR length(btrim(proposed_display_email)) > 0",
            name="ck_pending_email_changes_display_email_not_blank",
        ),
        CheckConstraint(
            "length(btrim(verification_token_hash)) > 0",
            name="ck_pending_email_changes_token_hash_not_blank",
        ),
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'revoked', 'superseded', 'expired')",
            name="ck_pending_email_changes_status",
        ),
        CheckConstraint(
            "expires_at > created_at",
            name="ck_pending_email_changes_expiration",
        ),
        CheckConstraint(
            "reason_code IN "
            "('self_service', 'company_administration', 'platform_administration')",
            name="ck_pending_email_changes_reason_code",
        ),
        CheckConstraint(
            "reason_code <> 'company_administration' "
            "OR initiating_company_id IS NOT NULL",
            name="ck_pending_email_changes_company_admin_origin",
        ),
        CheckConstraint(
            "(status = 'pending' AND confirmed_at IS NULL AND revoked_at IS NULL "
            "AND superseded_at IS NULL AND expired_at IS NULL) OR "
            "(status = 'confirmed' AND confirmed_at IS NOT NULL "
            "AND revoked_at IS NULL AND superseded_at IS NULL AND expired_at IS NULL) OR "
            "(status = 'revoked' AND revoked_at IS NOT NULL "
            "AND confirmed_at IS NULL AND superseded_at IS NULL AND expired_at IS NULL) OR "
            "(status = 'superseded' AND superseded_at IS NOT NULL "
            "AND confirmed_at IS NULL AND revoked_at IS NULL AND expired_at IS NULL) OR "
            "(status = 'expired' AND expired_at IS NOT NULL "
            "AND confirmed_at IS NULL AND revoked_at IS NULL AND superseded_at IS NULL)",
            name="ck_pending_email_changes_lifecycle",
        ),
        CheckConstraint(
            "confirmed_at IS NULL OR confirmed_at >= created_at",
            name="ck_pending_email_changes_confirmed_timestamp",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="ck_pending_email_changes_revoked_timestamp",
        ),
        CheckConstraint(
            "superseded_at IS NULL OR superseded_at >= created_at",
            name="ck_pending_email_changes_superseded_timestamp",
        ),
        CheckConstraint(
            "expired_at IS NULL OR expired_at >= created_at",
            name="ck_pending_email_changes_expired_timestamp",
        ),
        Index(
            "uq_pending_email_changes_active_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "uq_pending_email_changes_active_email",
            "proposed_normalized_email",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "ix_pending_email_changes_token_hash",
            "verification_token_hash",
            unique=True,
        ),
        Index(
            "ix_pending_email_changes_user_id_status",
            "user_id",
            "status",
        ),
        Index(
            "ix_pending_email_changes_status_expires_at",
            "status",
            "expires_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_pending_email_changes_user_id_users",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    proposed_normalized_email: Mapped[str] = mapped_column(String(320), nullable=False)
    proposed_display_email: Mapped[str | None] = mapped_column(String(320))
    verification_token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    reason_code: Mapped[str] = mapped_column(String(40), nullable=False)
    initiated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_pending_email_changes_initiated_by_user_id_users",
            ondelete="RESTRICT",
        ),
    )
    initiating_company_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "companies.id",
            name="fk_pending_email_changes_initiating_company_id_companies",
            ondelete="RESTRICT",
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(
        back_populates="pending_email_changes",
        foreign_keys=[user_id],
    )
    initiated_by_user: Mapped["User | None"] = relationship(
        back_populates="email_changes_initiated",
        foreign_keys=[initiated_by_user_id],
    )
    initiating_company: Mapped["Company | None"] = relationship()
