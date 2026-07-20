from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.platform.branch.models import Branch
    from app.platform.permissions.models import Role


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(name)) > 0",
            name="ck_companies_name_not_blank",
        ),
        CheckConstraint(
            "length(btrim(code)) > 0 AND code = upper(code)",
            name="ck_companies_code_normalized",
        ),
        CheckConstraint(
            "status IN ('active', 'inactive', 'suspended')",
            name="ck_companies_status",
        ),
        CheckConstraint(
            "length(btrim(timezone)) > 0",
            name="ck_companies_timezone_not_blank",
        ),
        UniqueConstraint("code", name="uq_companies_code"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    branches: Mapped[list["Branch"]] = relationship(
        back_populates="company",
        passive_deletes=True,
    )
    roles: Mapped[list["Role"]] = relationship(
        back_populates="company",
        passive_deletes=True,
    )
