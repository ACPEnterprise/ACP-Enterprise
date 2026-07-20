from datetime import date, datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.platform.branch.models import Branch
    from app.platform.company.membership_models import Membership
    from app.platform.company.models import Company
    from app.platform.users.models import User


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(employee_number)) > 0",
            name="ck_employees_employee_number_not_blank",
        ),
        CheckConstraint(
            "length(btrim(first_name)) > 0",
            name="ck_employees_first_name_not_blank",
        ),
        CheckConstraint(
            "length(btrim(last_name)) > 0",
            name="ck_employees_last_name_not_blank",
        ),
        CheckConstraint(
            "length(btrim(display_name)) > 0",
            name="ck_employees_display_name_not_blank",
        ),
        CheckConstraint(
            "employee_type IN ('employee', 'contractor', 'vendor')",
            name="ck_employees_employee_type",
        ),
        CheckConstraint(
            "status IN ('active', 'inactive', 'leave', 'terminated')",
            name="ck_employees_status",
        ),
        CheckConstraint(
            "termination_date IS NULL OR hire_date IS NULL "
            "OR termination_date >= hire_date",
            name="ck_employees_termination_after_hire",
        ),
        ForeignKeyConstraint(
            ["company_id", "membership_id"],
            ["memberships.company_id", "memberships.id"],
            name="fk_employees_company_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "home_branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_employees_company_home_branch",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("membership_id", name="uq_employees_membership_id"),
        Index(
            "uq_employees_active_company_employee_number",
            "company_id",
            "employee_number",
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
        Index("ix_employees_company_id_status", "company_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "companies.id",
            name="fk_employees_company_id_companies",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    membership_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    home_branch_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True, index=True
    )
    employee_number: Mapped[str] = mapped_column(String(50), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    job_title: Mapped[str | None] = mapped_column(String(150))
    employee_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    hire_date: Mapped[date | None] = mapped_column(Date)
    termination_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_employees_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_employees_updated_by_user_id_users",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    company: Mapped["Company"] = relationship(foreign_keys=[company_id])
    membership: Mapped["Membership | None"] = relationship(
        primaryjoin=(
            "and_(Employee.company_id == Membership.company_id, "
            "Employee.membership_id == Membership.id)"
        ),
        foreign_keys=[membership_id],
    )
    home_branch: Mapped["Branch | None"] = relationship(
        primaryjoin=(
            "and_(Employee.company_id == Branch.company_id, "
            "Employee.home_branch_id == Branch.id)"
        ),
        foreign_keys=[home_branch_id],
    )
    created_by_user: Mapped["User | None"] = relationship(
        foreign_keys=[created_by_user_id]
    )
    updated_by_user: Mapped["User | None"] = relationship(
        foreign_keys=[updated_by_user_id]
    )
