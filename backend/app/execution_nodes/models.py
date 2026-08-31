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
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EngineeringExecutionNode(Base):
    __tablename__ = "engineering_execution_nodes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            name="fk_execution_nodes_worker_company",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('active','revoked','expired')", name="ck_execution_nodes_status"
        ),
        CheckConstraint("version >= 1", name="ck_execution_nodes_version"),
        UniqueConstraint("company_id", "worker_id", name="uq_execution_nodes_worker"),
        UniqueConstraint("company_id", "id", name="uq_execution_nodes_company_id"),
        UniqueConstraint(
            "company_id", "credential_fingerprint", name="uq_execution_nodes_credential"
        ),
        Index("ix_execution_nodes_company_status", "company_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    worker_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_identifier: Mapped[str] = mapped_column(String(100), nullable=False)
    credential_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    capabilities: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_authenticated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ProviderExecutionTransition(Base):
    __tablename__ = "engineering_provider_execution_transitions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "execution_id", "command_id"],
            [
                "engineering_executions.company_id",
                "engineering_executions.id",
                "engineering_executions.command_id",
            ],
            name="fk_provider_transitions_execution_command",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "node_id"],
            ["engineering_execution_nodes.company_id", "engineering_execution_nodes.id"],
            name="fk_provider_transitions_node_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "lease_id"],
            ["engineering_worker_leases.company_id", "engineering_worker_leases.id"],
            name="fk_provider_transitions_lease_company",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "phase IN ('queued','composed','workspace_ready','executing','validating',"
            "'commit_ready','publishing_result','completed','failed','cancelled','reconciliation_required')",
            name="ck_provider_execution_transition_phase",
        ),
        UniqueConstraint(
            "company_id",
            "execution_id",
            "sequence",
            name="uq_provider_execution_transition_sequence",
        ),
        Index(
            "ix_provider_execution_transition_execution",
            "company_id",
            "execution_id",
            "sequence",
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
    node_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    command_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    execution_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    lease_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
