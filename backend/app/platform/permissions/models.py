from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.platform.company.membership_models import Membership
    from app.platform.company.models import Company
    from app.platform.users.models import User


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(code)) > 0 AND code = upper(btrim(code))",
            name="ck_permissions_code_normalized",
        ),
        CheckConstraint(
            "length(btrim(name)) > 0",
            name="ck_permissions_name_not_blank",
        ),
        CheckConstraint(
            "length(btrim(resource)) > 0",
            name="ck_permissions_resource_not_blank",
        ),
        CheckConstraint(
            "length(btrim(action)) > 0",
            name="ck_permissions_action_not_blank",
        ),
        CheckConstraint(
            "status IN ('active', 'retired')",
            name="ck_permissions_status",
        ),
        CheckConstraint(
            "(status = 'retired') = (retired_at IS NOT NULL)",
            name="ck_permissions_retired_timestamp",
        ),
        UniqueConstraint("code", name="uq_permissions_code"),
        Index("ix_permissions_resource_action", "resource", "action"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    resource: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    role_assignments: Mapped[list["RolePermission"]] = relationship(
        back_populates="permission",
        passive_deletes=True,
    )


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(code)) > 0 AND code = upper(btrim(code))",
            name="ck_roles_code_normalized",
        ),
        CheckConstraint(
            "length(btrim(name)) > 0",
            name="ck_roles_name_not_blank",
        ),
        CheckConstraint(
            "status IN ('active', 'inactive', 'archived')",
            name="ck_roles_status",
        ),
        CheckConstraint(
            "(status = 'archived') = (archived_at IS NOT NULL)",
            name="ck_roles_archived_timestamp",
        ),
        UniqueConstraint(
            "company_id",
            "id",
            name="uq_roles_company_id_id",
        ),
        Index(
            "uq_roles_active_company_code",
            "company_id",
            "code",
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
        Index("ix_roles_company_id_status", "company_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "companies.id",
            name="fk_roles_company_id_companies",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_roles_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_roles_updated_by_user_id_users",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    company: Mapped["Company"] = relationship(back_populates="roles")
    created_by_user: Mapped["User | None"] = relationship(
        back_populates="roles_created",
        foreign_keys=[created_by_user_id],
    )
    updated_by_user: Mapped["User | None"] = relationship(
        back_populates="roles_updated",
        foreign_keys=[updated_by_user_id],
    )
    permission_assignments: Mapped[list["RolePermission"]] = relationship(
        back_populates="role",
        passive_deletes=True,
    )
    membership_assignments: Mapped[list["MembershipRole"]] = relationship(
        back_populates="role",
        primaryjoin=(
            "and_(Role.company_id == MembershipRole.company_id, "
            "Role.id == MembershipRole.role_id)"
        ),
        foreign_keys="MembershipRole.role_id",
        passive_deletes=True,
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint(
            "role_id",
            "permission_id",
            name="uq_role_permissions_role_id_permission_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    role_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "roles.id",
            name="fk_role_permissions_role_id_roles",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    permission_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "permissions.id",
            name="fk_role_permissions_permission_id_permissions",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    assigned_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_role_permissions_assigned_by_user_id_users",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    role: Mapped[Role] = relationship(back_populates="permission_assignments")
    permission: Mapped[Permission] = relationship(back_populates="role_assignments")
    assigned_by_user: Mapped["User | None"] = relationship(
        back_populates="role_permission_assignments",
        foreign_keys=[assigned_by_user_id],
    )


class MembershipRole(Base):
    """Historical role grant; revoked grants remain immutable history."""

    __tablename__ = "membership_roles"
    __table_args__ = (
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= assigned_at",
            name="ck_membership_roles_revocation_after_assignment",
        ),
        ForeignKeyConstraint(
            ["company_id", "membership_id"],
            ["memberships.company_id", "memberships.id"],
            name="fk_membership_roles_company_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "role_id"],
            ["roles.company_id", "roles.id"],
            name="fk_membership_roles_company_role",
            ondelete="RESTRICT",
        ),
        Index(
            "uq_membership_roles_active_membership_role",
            "membership_id",
            "role_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index("ix_membership_roles_membership_id", "membership_id"),
        Index("ix_membership_roles_role_id", "role_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    membership_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    role_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    assigned_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_membership_roles_assigned_by_user_id_users",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    membership: Mapped["Membership"] = relationship(
        back_populates="role_assignments",
        primaryjoin=(
            "and_(MembershipRole.company_id == Membership.company_id, "
            "MembershipRole.membership_id == Membership.id)"
        ),
        foreign_keys=[membership_id],
    )
    role: Mapped[Role] = relationship(
        back_populates="membership_assignments",
        primaryjoin=(
            "and_(MembershipRole.company_id == Role.company_id, "
            "MembershipRole.role_id == Role.id)"
        ),
        foreign_keys=[role_id],
    )
    assigned_by_user: Mapped["User | None"] = relationship(
        back_populates="membership_role_assignments",
        foreign_keys=[assigned_by_user_id],
    )
