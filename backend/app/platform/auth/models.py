from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.platform.users.models import User


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuthenticationSession(Base):
    __tablename__ = "authentication_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'revoked', 'expired', 'compromised')",
            name="ck_authentication_sessions_status",
        ),
        CheckConstraint(
            "absolute_expires_at > created_at",
            name="ck_authentication_sessions_absolute_expiration",
        ),
        CheckConstraint(
            "idle_expires_at IS NULL OR "
            "(idle_expires_at > created_at "
            "AND idle_expires_at <= absolute_expires_at)",
            name="ck_authentication_sessions_idle_expiration",
        ),
        CheckConstraint(
            "last_seen_at >= created_at",
            name="ck_authentication_sessions_last_seen",
        ),
        CheckConstraint(
            "(status IN ('revoked', 'compromised')) = (revoked_at IS NOT NULL)",
            name="ck_authentication_sessions_revocation_status",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="ck_authentication_sessions_revocation_timestamp",
        ),
        CheckConstraint(
            "length(btrim(authentication_method)) > 0",
            name="ck_authentication_sessions_method_not_blank",
        ),
        CheckConstraint(
            "credential_version >= 1",
            name="ck_authentication_sessions_credential_version",
        ),
        CheckConstraint(
            "authorization_version >= 1",
            name="ck_authentication_sessions_authorization_version",
        ),
        Index(
            "ix_authentication_sessions_user_id_status",
            "user_id",
            "status",
        ),
        Index(
            "ix_authentication_sessions_absolute_expires_at",
            "absolute_expires_at",
        ),
        Index(
            "ix_authentication_sessions_idle_expires_at",
            "idle_expires_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_authentication_sessions_user_id_users",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    absolute_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    idle_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocation_reason: Mapped[str | None] = mapped_column(String(200))
    revoked_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_authentication_sessions_revoked_by_user_id_users",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    device_label: Mapped[str | None] = mapped_column(String(200))
    authentication_method: Mapped[str] = mapped_column(String(50), nullable=False)
    credential_version: Mapped[int] = mapped_column(Integer, nullable=False)
    authorization_version: Mapped[int] = mapped_column(Integer, nullable=False)

    user: Mapped["User"] = relationship(
        back_populates="authentication_sessions",
        foreign_keys=[user_id],
    )
    revoked_by_user: Mapped["User | None"] = relationship(
        back_populates="sessions_revoked",
        foreign_keys=[revoked_by_user_id],
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="session",
        foreign_keys="RefreshToken.session_id",
        passive_deletes=True,
    )
    security_events: Mapped[list["AuthenticationSecurityEvent"]] = relationship(
        back_populates="session",
        passive_deletes=True,
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(token_hash)) > 0",
            name="ck_refresh_tokens_hash_not_blank",
        ),
        CheckConstraint(
            "sequence_number >= 0",
            name="ck_refresh_tokens_sequence_number",
        ),
        CheckConstraint(
            "expires_at > issued_at",
            name="ck_refresh_tokens_expiration",
        ),
        CheckConstraint(
            "used_at IS NULL OR used_at >= issued_at",
            name="ck_refresh_tokens_used_timestamp",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= issued_at",
            name="ck_refresh_tokens_revoked_timestamp",
        ),
        CheckConstraint(
            "reuse_detected_at IS NULL OR "
            "(used_at IS NOT NULL AND reuse_detected_at >= used_at)",
            name="ck_refresh_tokens_reuse_timestamp",
        ),
        CheckConstraint(
            "replaced_by_token_id IS NULL OR used_at IS NOT NULL",
            name="ck_refresh_tokens_replacement_requires_use",
        ),
        CheckConstraint(
            "replaced_by_token_id IS NULL OR replaced_by_token_id <> id",
            name="ck_refresh_tokens_not_self_replaced",
        ),
        CheckConstraint(
            "parent_token_id IS NULL OR parent_token_id <> id",
            name="ck_refresh_tokens_not_self_parent",
        ),
        UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
        UniqueConstraint(
            "family_id",
            "sequence_number",
            name="uq_refresh_tokens_family_id_sequence_number",
        ),
        Index(
            "ix_refresh_tokens_session_id_expires_at",
            "session_id",
            "expires_at",
        ),
        Index("ix_refresh_tokens_family_id", "family_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "authentication_sessions.id",
            name="fk_refresh_tokens_session_id_authentication_sessions",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    family_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, default=uuid4
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_token_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "refresh_tokens.id",
            name="fk_refresh_tokens_replaced_by_token_id_refresh_tokens",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    parent_token_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "refresh_tokens.id",
            name="fk_refresh_tokens_parent_token_id_refresh_tokens",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    revocation_reason: Mapped[str | None] = mapped_column(String(200))
    reuse_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    session: Mapped[AuthenticationSession] = relationship(
        back_populates="refresh_tokens",
        foreign_keys=[session_id],
    )
    parent_token: Mapped["RefreshToken | None"] = relationship(
        back_populates="child_tokens",
        foreign_keys=[parent_token_id],
        remote_side=[id],
    )
    child_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="parent_token",
        foreign_keys=[parent_token_id],
        passive_deletes=True,
    )
    replaced_by_token: Mapped["RefreshToken | None"] = relationship(
        back_populates="replacement_for",
        foreign_keys=[replaced_by_token_id],
        remote_side=[id],
    )
    replacement_for: Mapped[list["RefreshToken"]] = relationship(
        back_populates="replaced_by_token",
        foreign_keys=[replaced_by_token_id],
        passive_deletes=True,
    )


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(token_hash)) > 0",
            name="ck_password_reset_tokens_hash_not_blank",
        ),
        CheckConstraint(
            "expires_at > issued_at",
            name="ck_password_reset_tokens_expiration",
        ),
        CheckConstraint(
            "consumed_at IS NULL OR consumed_at >= issued_at",
            name="ck_password_reset_tokens_consumed_timestamp",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= issued_at",
            name="ck_password_reset_tokens_revoked_timestamp",
        ),
        CheckConstraint(
            "NOT (consumed_at IS NOT NULL AND revoked_at IS NOT NULL)",
            name="ck_password_reset_tokens_terminal_state",
        ),
        UniqueConstraint(
            "token_hash",
            name="uq_password_reset_tokens_token_hash",
        ),
        Index(
            "ix_password_reset_tokens_user_id_expires_at",
            "user_id",
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
            name="fk_password_reset_tokens_user_id_users",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_ip_address: Mapped[str | None] = mapped_column(String(45))
    request_user_agent: Mapped[str | None] = mapped_column(Text)

    user: Mapped["User"] = relationship(back_populates="password_reset_tokens")


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(normalized_email)) > 0 "
            "AND normalized_email = lower(btrim(normalized_email))",
            name="ck_email_verification_tokens_normalized_email",
        ),
        CheckConstraint(
            "length(btrim(token_hash)) > 0",
            name="ck_email_verification_tokens_hash_not_blank",
        ),
        CheckConstraint(
            "expires_at > issued_at",
            name="ck_email_verification_tokens_expiration",
        ),
        CheckConstraint(
            "consumed_at IS NULL OR consumed_at >= issued_at",
            name="ck_email_verification_tokens_consumed_timestamp",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= issued_at",
            name="ck_email_verification_tokens_revoked_timestamp",
        ),
        CheckConstraint(
            "NOT (consumed_at IS NOT NULL AND revoked_at IS NOT NULL)",
            name="ck_email_verification_tokens_terminal_state",
        ),
        UniqueConstraint(
            "token_hash",
            name="uq_email_verification_tokens_token_hash",
        ),
        Index(
            "ix_email_verification_tokens_user_id_expires_at",
            "user_id",
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
            name="fk_email_verification_tokens_user_id_users",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    normalized_email: Mapped[str] = mapped_column(String(320), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="email_verification_tokens")


class AuthenticationSecurityEvent(Base):
    """Operational authentication evidence, not the enterprise audit ledger."""

    __tablename__ = "authentication_security_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('login_succeeded', 'login_failed', 'account_locked', "
            "'password_reset_requested', 'password_reset_completed', "
            "'refresh_token_reused', 'session_revoked', "
            "'email_verification_requested', 'email_verified')",
            name="ck_authentication_security_events_type",
        ),
        CheckConstraint(
            "normalized_attempted_email IS NULL OR "
            "(length(btrim(normalized_attempted_email)) > 0 AND "
            "normalized_attempted_email = lower(btrim(normalized_attempted_email)))",
            name="ck_authentication_security_events_normalized_email",
        ),
        CheckConstraint(
            "NOT success OR failure_reason IS NULL",
            name="ck_authentication_security_events_success_reason",
        ),
        Index(
            "ix_authentication_security_events_occurred_at",
            "occurred_at",
        ),
        Index(
            "ix_authentication_security_events_user_id",
            "user_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_authentication_security_events_user_id_users",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    normalized_attempted_email: Mapped[str | None] = mapped_column(String(320))
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(200))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(Text)
    session_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "authentication_sessions.id",
            name="fk_auth_security_events_session_id_sessions",
            ondelete="RESTRICT",
        ),
        nullable=True,
        index=True,
    )

    user: Mapped["User | None"] = relationship(
        back_populates="authentication_security_events"
    )
    session: Mapped[AuthenticationSession | None] = relationship(
        back_populates="security_events"
    )
