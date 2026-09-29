from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProviderConnectionBinding(Base):
    """Safe connection metadata; secret material lives behind opaque references."""

    __tablename__ = "platform_provider_connection_bindings"
    __table_args__ = (
        CheckConstraint(
            "environment IN ('development','test','preview','beta','production')",
            name="ck_provider_connection_environment",
        ),
        CheckConstraint(
            "state IN ('pending_consent','active','disabled','revoked')",
            name="ck_provider_connection_state",
        ),
        CheckConstraint(
            "client_credential_reference NOT LIKE '%://%' AND "
            "account_token_reference NOT LIKE '%://%'",
            name="ck_provider_connection_opaque_references",
        ),
        UniqueConstraint("company_id", "id", name="uq_provider_connection_company_id"),
        Index(
            "ix_provider_connection_company_provider",
            "company_id",
            "environment",
            "provider_family",
            "state",
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
    environment: Mapped[str] = mapped_column(String(24), nullable=False)
    provider_family: Mapped[str] = mapped_column(String(80), nullable=False)
    client_credential_reference: Mapped[str] = mapped_column(
        String(240), nullable=False
    )
    account_token_reference: Mapped[str] = mapped_column(String(240), nullable=False)
    granted_scopes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    consent_actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    token_fingerprint: Mapped[str | None] = mapped_column(String(64))
    token_generation: Mapped[int | None]
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    callback_identity: Mapped[str] = mapped_column(String(240), nullable=False)
    state: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending_consent"
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
