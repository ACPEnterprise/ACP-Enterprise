from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
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


class LiveClientSupervisorModel(Base):
    __tablename__ = "engineering_live_client_supervisors"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "state IN ('stopped','starting','ready','recovering','reconnecting',"
            "'timed_out','cancelled','failed')",
            name="ck_live_client_supervisors_state",
        ),
        CheckConstraint("version >= 1", name="ck_live_client_supervisors_version"),
        UniqueConstraint(
            "company_id", "worker_id", name="uq_live_client_supervisors_worker"
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_live_client_supervisors_company_id"
        ),
        Index(
            "ix_live_client_supervisors_company_state",
            "company_id",
            "state",
            "updated_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    worker_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    state: Mapped[str] = mapped_column(String(30), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_transition_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    failure_classification: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ProviderSessionModel(Base):
    __tablename__ = "engineering_provider_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "supervisor_id"],
            [
                "engineering_live_client_supervisors.company_id",
                "engineering_live_client_supervisors.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "composition_id"],
            [
                "engineering_execution_compositions.company_id",
                "engineering_execution_compositions.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "attempt_id"],
            [
                "engineering_provider_execution_attempts.company_id",
                "engineering_provider_execution_attempts.id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "state IN ('created','opening','ready','active','closing','closed',"
            "'expired','failed','cancelled')",
            name="ck_provider_sessions_state",
        ),
        CheckConstraint(
            "runtime_state IN ('created','initializing','credential_validation',"
            "'provider_initializing','provider_ready','opening','ready','active',"
            "'closing','closed','recovering','failed','cancelled',"
            "'credential_failure','provider_failure','timeout')",
            name="ck_provider_sessions_runtime_state",
        ),
        CheckConstraint(
            "credential_status IN ('unavailable','invalid','expired','usable')",
            name="ck_provider_sessions_credential_status",
        ),
        CheckConstraint(
            "provider_ready = false OR "
            "(runtime_state = 'provider_ready' AND credential_status = 'usable' "
            "AND provider_session_reference IS NOT NULL)",
            name="ck_provider_sessions_provider_ready",
        ),
        CheckConstraint("version >= 1", name="ck_provider_sessions_version"),
        CheckConstraint(
            "expires_at > created_at", name="ck_provider_sessions_expiration"
        ),
        UniqueConstraint(
            "company_id",
            "composition_id",
            "attempt_id",
            name="uq_provider_sessions_composition_attempt",
        ),
        UniqueConstraint("company_id", "id", name="uq_provider_sessions_company_id"),
        Index(
            "ix_provider_sessions_company_state",
            "company_id",
            "state",
            "updated_at",
        ),
        Index(
            "ix_provider_sessions_company_composition",
            "company_id",
            "composition_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    supervisor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    composition_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    attempt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    worker_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    lease_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    provider_identifier: Mapped[str] = mapped_column(String(100), nullable=False)
    effective_capabilities: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    approved_code_changes: Mapped[bool] = mapped_column(Boolean, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    runtime_state: Mapped[str] = mapped_column(
        String(40), nullable=False, default="created"
    )
    credential_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unavailable"
    )
    provider_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    provider_session_reference: Mapped[str | None] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    opening_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    failure_classification: Mapped[str | None] = mapped_column(String(100))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
