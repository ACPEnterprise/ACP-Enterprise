from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.platform.company.models import Company


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Branch(Base):
    __tablename__ = "branches"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(name)) > 0",
            name="ck_branches_name_not_blank",
        ),
        CheckConstraint(
            "length(btrim(code)) > 0 AND code = upper(code)",
            name="ck_branches_code_normalized",
        ),
        CheckConstraint(
            "status IN ('active', 'inactive')",
            name="ck_branches_status",
        ),
        CheckConstraint(
            "length(btrim(timezone)) > 0",
            name="ck_branches_timezone_not_blank",
        ),
        UniqueConstraint(
            "company_id",
            "code",
            name="uq_branches_company_id_code",
        ),
        UniqueConstraint(
            "company_id",
            "id",
            name="uq_branches_company_id_id",
        ),
        Index(
            "uq_branches_active_primary_company",
            "company_id",
            unique=True,
            postgresql_where=text(
                "is_primary AND status = 'active' AND archived_at IS NULL"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "companies.id",
            name="fk_branches_company_id_companies",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    company: Mapped["Company"] = relationship(back_populates="branches")
