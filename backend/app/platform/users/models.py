from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.platform.auth.models import (
        AuthenticationSecurityEvent,
        AuthenticationSession,
        EmailVerificationToken,
        PasswordResetToken,
    )
    from app.platform.company.membership_models import Membership
    from app.platform.permissions.models import MembershipRole, Role, RolePermission


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(normalized_email)) > 0 "
            "AND normalized_email = lower(btrim(normalized_email))",
            name="ck_users_normalized_email",
        ),
        CheckConstraint(
            "length(btrim(first_name)) > 0",
            name="ck_users_first_name_not_blank",
        ),
        CheckConstraint(
            "length(btrim(last_name)) > 0",
            name="ck_users_last_name_not_blank",
        ),
        CheckConstraint(
            "length(btrim(display_name)) > 0",
            name="ck_users_display_name_not_blank",
        ),
        CheckConstraint(
            "status IN ('invited', 'active', 'disabled', 'locked')",
            name="ck_users_status",
        ),
        CheckConstraint(
            "authorization_version >= 1",
            name="ck_users_authorization_version",
        ),
        UniqueConstraint("normalized_email", name="uq_users_normalized_email"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    normalized_email: Mapped[str] = mapped_column(String(320), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="invited")
    authorization_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    credential: Mapped["UserCredential | None"] = relationship(
        back_populates="user",
        passive_deletes=True,
        uselist=False,
    )
    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="user",
        foreign_keys="Membership.user_id",
        passive_deletes=True,
    )
    roles_created: Mapped[list["Role"]] = relationship(
        back_populates="created_by_user",
        foreign_keys="Role.created_by_user_id",
        passive_deletes=True,
    )
    roles_updated: Mapped[list["Role"]] = relationship(
        back_populates="updated_by_user",
        foreign_keys="Role.updated_by_user_id",
        passive_deletes=True,
    )
    role_permission_assignments: Mapped[list["RolePermission"]] = relationship(
        back_populates="assigned_by_user",
        foreign_keys="RolePermission.assigned_by_user_id",
        passive_deletes=True,
    )
    membership_role_assignments: Mapped[list["MembershipRole"]] = relationship(
        back_populates="assigned_by_user",
        foreign_keys="MembershipRole.assigned_by_user_id",
        passive_deletes=True,
    )
    authentication_sessions: Mapped[list["AuthenticationSession"]] = relationship(
        back_populates="user",
        foreign_keys="AuthenticationSession.user_id",
        passive_deletes=True,
    )
    sessions_revoked: Mapped[list["AuthenticationSession"]] = relationship(
        back_populates="revoked_by_user",
        foreign_keys="AuthenticationSession.revoked_by_user_id",
        passive_deletes=True,
    )
    password_reset_tokens: Mapped[list["PasswordResetToken"]] = relationship(
        back_populates="user",
        passive_deletes=True,
    )
    email_verification_tokens: Mapped[list["EmailVerificationToken"]] = relationship(
        back_populates="user",
        passive_deletes=True,
    )
    authentication_security_events: Mapped[list["AuthenticationSecurityEvent"]] = (
        relationship(
            back_populates="user",
            passive_deletes=True,
        )
    )


class UserCredential(Base):
    __tablename__ = "user_credentials"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(password_hash)) > 0",
            name="ck_user_credentials_password_hash_not_blank",
        ),
        CheckConstraint(
            "failed_login_count >= 0",
            name="ck_user_credentials_failed_login_count",
        ),
        CheckConstraint(
            "credential_version >= 1",
            name="ck_user_credentials_credential_version",
        ),
        UniqueConstraint("user_id", name="uq_user_credentials_user_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_user_credentials_user_id_users",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_failed_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    credential_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    user: Mapped[User] = relationship(back_populates="credential")
