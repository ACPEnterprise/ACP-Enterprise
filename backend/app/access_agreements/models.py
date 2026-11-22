from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
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
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AccessAgreementDocument(Base):
    __tablename__ = "access_agreement_documents"
    __table_args__ = (
        UniqueConstraint(
            "code", "version", name="uq_access_agreement_document_version"
        ),
        CheckConstraint(
            "status IN ('draft','published','retired')",
            name="ck_access_agreement_document_status",
        ),
        CheckConstraint(
            "length(btrim(content)) > 0", name="ck_access_agreement_document_content"
        ),
        Index("ix_access_agreement_documents_current", "code", "status", "version"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    mandatory: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AccessAgreementAcceptance(Base):
    __tablename__ = "access_agreement_acceptances"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "company_id",
            "agreement_id",
            name="uq_access_agreement_acceptance_identity",
        ),
        Index(
            "ix_access_agreement_acceptances_user_company",
            "user_id",
            "company_id",
            "accepted_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    agreement_id: Mapped[UUID] = mapped_column(
        ForeignKey("access_agreement_documents.id", ondelete="RESTRICT"), nullable=False
    )
    agreement_version: Mapped[int] = mapped_column(Integer, nullable=False)
    agreement_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    recipient_name: Mapped[str] = mapped_column(String(200), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    action: Mapped[str] = mapped_column(
        String(80), nullable=False, default="electronic_signature"
    )
    electronic_signature_consent: Mapped[bool] = mapped_column(nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, default=uuid4
    )
