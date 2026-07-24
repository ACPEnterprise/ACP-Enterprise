from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WorkerIdentity(Base):
    __tablename__ = "worker_identities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["registered_by_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_worker_identities_registering_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "orchestration_worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            name="fk_worker_identities_orchestration_worker",
            ondelete="RESTRICT",
        ),
        CheckConstraint("length(btrim(name)) > 0", name="ck_worker_identities_name"),
        CheckConstraint(
            "state IN ('registered','active','suspended','revoked')",
            name="ck_worker_identities_state",
        ),
        CheckConstraint("version >= 1", name="ck_worker_identities_version"),
        UniqueConstraint(
            "company_id", "name", name="uq_worker_identities_company_name"
        ),
        UniqueConstraint("company_id", "id", name="uq_worker_identities_company_id"),
        UniqueConstraint(
            "company_id",
            "orchestration_worker_id",
            name="uq_worker_identities_orchestration_worker",
        ),
        Index("ix_worker_identities_company_state", "company_id", "state", "id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    registered_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    orchestration_worker_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class WorkerCredential(Base):
    __tablename__ = "worker_identity_credentials"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "identity_id"],
            ["worker_identities.company_id", "worker_identities.id"],
            name="fk_worker_credentials_identity",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "state IN ('pending','active','revoked','expired')",
            name="ck_worker_credentials_state",
        ),
        CheckConstraint("version >= 1", name="ck_worker_credentials_version"),
        CheckConstraint(
            "length(btrim(verifier)) > 0 AND length(btrim(verifier_algorithm)) > 0 "
            "AND length(btrim(public_key_id)) > 0",
            name="ck_worker_credentials_public_metadata",
        ),
        CheckConstraint("expires_at > issued_at", name="ck_worker_credentials_expiry"),
        UniqueConstraint(
            "company_id",
            "identity_id",
            "version",
            name="uq_worker_credentials_identity_version",
        ),
        UniqueConstraint(
            "company_id",
            "identity_id",
            "id",
            name="uq_worker_credentials_identity_id",
        ),
        Index(
            "uq_worker_credentials_active_identity",
            "company_id",
            "identity_id",
            unique=True,
            postgresql_where=text("state = 'active'"),
        ),
        Index(
            "ix_worker_credentials_public_key",
            "company_id",
            "public_key_id",
            unique=True,
        ),
        Index(
            "ix_worker_credentials_expiration",
            "company_id",
            "state",
            "expires_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    identity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    verifier: Mapped[str] = mapped_column(String(512), nullable=False)
    verifier_algorithm: Mapped[str] = mapped_column(String(50), nullable=False)
    public_key_id: Mapped[str] = mapped_column(String(200), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
