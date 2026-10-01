from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AcceptanceServicePrincipal(Base):
    __tablename__ = "acceptance_service_principals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_acceptance_principals_membership_company",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "state IN ('active','revoked')", name="ck_acceptance_principals_state"
        ),
        CheckConstraint("version >= 1", name="ck_acceptance_principals_version"),
        CheckConstraint(
            "length(btrim(environment)) > 0",
            name="ck_acceptance_principals_environment",
        ),
        UniqueConstraint("user_id", name="uq_acceptance_principals_user"),
        UniqueConstraint(
            "company_id",
            "environment",
            "name",
            name="uq_acceptance_principals_scope_name",
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
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    membership_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    environment: Mapped[str] = mapped_column(String(40), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    provisioned_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReleaseServicePrincipal(Base):
    __tablename__ = "release_service_principals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_release_principals_membership_company",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "state IN ('active','revoked')", name="ck_release_principals_state"
        ),
        CheckConstraint("version >= 1", name="ck_release_principals_version"),
        CheckConstraint(
            "environment IN ('beta','preview','test')",
            name="ck_release_principals_environment",
        ),
        UniqueConstraint("user_id", name="uq_release_principals_user"),
        UniqueConstraint(
            "company_id", "environment", name="uq_release_principals_scope"
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
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    membership_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    environment: Mapped[str] = mapped_column(String(40), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
