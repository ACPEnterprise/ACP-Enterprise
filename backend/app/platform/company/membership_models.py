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
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.platform.branch.models import Branch
    from app.platform.company.models import Company
    from app.platform.permissions.models import MembershipRole
    from app.platform.users.models import User


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        CheckConstraint(
            "status IN ('invited', 'active', 'suspended', 'revoked', 'archived')",
            name="ck_memberships_status",
        ),
        CheckConstraint(
            "accepted_at IS NULL OR invited_at IS NULL OR accepted_at >= invited_at",
            name="ck_memberships_acceptance_after_invitation",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR status IN ('revoked', 'archived')",
            name="ck_memberships_revoked_status",
        ),
        ForeignKeyConstraint(
            ["company_id", "default_branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_memberships_company_default_branch",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "user_id",
            "company_id",
            name="uq_memberships_user_id_company_id",
        ),
        UniqueConstraint(
            "company_id",
            "id",
            name="uq_memberships_company_id_id",
        ),
        Index("ix_memberships_company_id_status", "company_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_memberships_user_id_users",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "companies.id",
            name="fk_memberships_company_id_companies",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="invited",
    )
    default_branch_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True, index=True
    )
    has_all_branch_access: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_memberships_revoked_by_user_id_users",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    user: Mapped["User"] = relationship(
        back_populates="memberships",
        foreign_keys=[user_id],
    )
    company: Mapped["Company"] = relationship(foreign_keys=[company_id])
    default_branch: Mapped["Branch | None"] = relationship(
        primaryjoin=(
            "and_(Membership.company_id == Branch.company_id, "
            "Membership.default_branch_id == Branch.id)"
        ),
        foreign_keys=[default_branch_id],
    )
    revoked_by_user: Mapped["User | None"] = relationship(
        foreign_keys=[revoked_by_user_id]
    )
    branch_access: Mapped[list["MembershipBranchAccess"]] = relationship(
        back_populates="membership",
        passive_deletes=True,
    )
    role_assignments: Mapped[list["MembershipRole"]] = relationship(
        back_populates="membership",
        primaryjoin=(
            "and_(Membership.company_id == MembershipRole.company_id, "
            "Membership.id == MembershipRole.membership_id)"
        ),
        foreign_keys="MembershipRole.membership_id",
        passive_deletes=True,
    )


class MembershipBranchAccess(Base):
    """Explicit branch grant; cross-company ownership is service-validated."""

    __tablename__ = "membership_branch_access"
    __table_args__ = (
        UniqueConstraint(
            "membership_id",
            "branch_id",
            name="uq_membership_branch_access_membership_id_branch_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    membership_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "memberships.id",
            name="fk_membership_branch_access_membership_id_memberships",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    branch_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "branches.id",
            name="fk_membership_branch_access_branch_id_branches",
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
            name="fk_membership_branch_access_assigned_by_user_id_users",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    membership: Mapped[Membership] = relationship(back_populates="branch_access")
    branch: Mapped["Branch"] = relationship(foreign_keys=[branch_id])
    assigned_by_user: Mapped["User | None"] = relationship(
        foreign_keys=[assigned_by_user_id]
    )
