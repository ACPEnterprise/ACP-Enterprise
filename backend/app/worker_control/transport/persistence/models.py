from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WorkerTransportChallenge(Base):
    __tablename__ = "engineering_worker_transport_challenges"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            name="fk_worker_transport_challenges_worker",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "length(challenge_digest) = 64",
            name="ck_worker_transport_challenges_digest",
        ),
        CheckConstraint(
            "expires_at > issued_at", name="ck_worker_transport_challenges_expiration"
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_worker_transport_challenges_company_id"
        ),
        Index(
            "ix_worker_transport_challenges_worker_expiration",
            "company_id",
            "worker_id",
            "expires_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    worker_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    challenge_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    key_version: Mapped[str] = mapped_column(String(100), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkerTransportSession(Base):
    __tablename__ = "engineering_worker_transport_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            name="fk_worker_transport_sessions_worker",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "worker_identity_id"],
            ["worker_identities.company_id", "worker_identities.id"],
            name="fk_worker_transport_sessions_identity",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "worker_identity_id", "credential_id"],
            [
                "worker_identity_credentials.company_id",
                "worker_identity_credentials.identity_id",
                "worker_identity_credentials.id",
            ],
            name="fk_worker_transport_sessions_credential",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "state IN ('active','expired','revoked')",
            name="ck_worker_transport_sessions_state",
        ),
        CheckConstraint(
            "expires_at > established_at",
            name="ck_worker_transport_sessions_expiration",
        ),
        CheckConstraint(
            "next_sequence >= 1", name="ck_worker_transport_sessions_sequence"
        ),
        CheckConstraint("version >= 1", name="ck_worker_transport_sessions_version"),
        CheckConstraint(
            "length(authentication_subject_digest) = 64",
            name="ck_worker_transport_sessions_subject_digest",
        ),
        CheckConstraint(
            "(worker_identity_id IS NOT NULL AND credential_id IS NOT NULL "
            "AND credential_version IS NOT NULL) OR "
            "(state = 'revoked' AND worker_identity_id IS NULL "
            "AND credential_id IS NULL AND credential_version IS NULL)",
            name="ck_worker_transport_sessions_identity_binding",
        ),
        CheckConstraint(
            "credential_version IS NULL OR credential_version >= 1",
            name="ck_worker_transport_sessions_credential_version",
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_worker_transport_sessions_company_id"
        ),
        Index(
            "ix_worker_transport_sessions_worker_state",
            "company_id",
            "worker_id",
            "state",
            "expires_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    worker_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    worker_identity_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    credential_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    credential_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_identifier: Mapped[str] = mapped_column(String(100), nullable=False)
    authentication_subject_digest: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    capabilities: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    key_version: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    established_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    next_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)


class WorkerTransportReceipt(Base):
    __tablename__ = "engineering_worker_transport_receipts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "session_id"],
            [
                "engineering_worker_transport_sessions.company_id",
                "engineering_worker_transport_sessions.id",
            ],
            name="fk_worker_transport_receipts_session",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            name="fk_worker_transport_receipts_worker",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "sequence_number >= 1", name="ck_worker_transport_receipts_sequence"
        ),
        CheckConstraint(
            "length(envelope_digest) = 64",
            name="ck_worker_transport_receipts_digest",
        ),
        UniqueConstraint(
            "company_id",
            "session_id",
            "sequence_number",
            name="uq_worker_transport_receipts_session_sequence",
        ),
        Index(
            "ix_worker_transport_receipts_session_accepted",
            "company_id",
            "session_id",
            "accepted_at",
        ),
    )

    message_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    session_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    worker_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    envelope_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    outcome_reference: Mapped[str] = mapped_column(String(255), nullable=False)
