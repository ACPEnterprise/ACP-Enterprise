from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OperationalTaxPolicy(Base):
    __tablename__ = "operational_tax_policies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_operational_tax_policy_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "tax_classification_id"],
            [
                "price_book_tax_classifications.company_id",
                "price_book_tax_classifications.id",
            ],
            name="fk_operational_tax_policy_classification",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "rate_basis_points BETWEEN 0 AND 10000",
            name="ck_operational_tax_policy_rate",
        ),
        CheckConstraint("version >= 1", name="ck_operational_tax_policy_version"),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name="ck_operational_tax_policy_currency"
        ),
        CheckConstraint(
            "expires_at IS NULL OR expires_at > effective_at",
            name="ck_operational_tax_policy_window",
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_operational_tax_policy_company_id"
        ),
        Index(
            "ix_operational_tax_policy_resolution",
            "company_id",
            "branch_id",
            "tax_classification_id",
            "currency",
            "effective_at",
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
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    tax_classification_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rate_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CompanyTaxPolicy(Base):
    __tablename__ = "company_tax_policies"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_company_tax_policy_version"),
        CheckConstraint(
            "status IN ('draft','certified','superseded')",
            name="ck_company_tax_policy_status",
        ),
        CheckConstraint(
            "customer_service_treatment IN ('NOT_TAXED','TAXED','REVIEW_REQUIRED')",
            name="ck_company_tax_policy_service_treatment",
        ),
        CheckConstraint(
            "customer_material_treatment IN ('NOT_TAXED','TAXED','REVIEW_REQUIRED')",
            name="ck_company_tax_policy_material_treatment",
        ),
        CheckConstraint(
            "purchase_material_tax_handling IN ('PAID_AT_PURCHASE','EXEMPT','REVIEW_REQUIRED')",
            name="ck_company_tax_policy_purchase_handling",
        ),
        CheckConstraint(
            "expires_at IS NULL OR expires_at > effective_at",
            name="ck_company_tax_policy_window",
        ),
        UniqueConstraint(
            "company_id",
            "policy_identity",
            "version",
            name="uq_company_tax_policy_version",
        ),
        Index(
            "ix_company_tax_policy_effective",
            "company_id",
            "status",
            "effective_at",
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
    policy_identity: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    customer_service_treatment: Mapped[str] = mapped_column(String(24), nullable=False)
    customer_material_treatment: Mapped[str] = mapped_column(String(24), nullable=False)
    purchase_material_tax_handling: Mapped[str] = mapped_column(
        String(24), nullable=False
    )
    authority_source: Mapped[str] = mapped_column(String(80), nullable=False)
    authority_notes: Mapped[str | None] = mapped_column(Text)
    authorized_exceptions: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    supersedes_policy_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("company_tax_policies.id", ondelete="RESTRICT"),
    )
    certified_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    certified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
