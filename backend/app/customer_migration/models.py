from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
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


class CustomerMigrationRun(Base):
    __tablename__ = "customer_migration_runs"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('dry_run', 'import')", name="ck_customer_migration_runs_mode"
        ),
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_customer_migration_runs_status",
        ),
        CheckConstraint(
            "source_count >= 0 AND accepted_count >= 0 AND rejected_count >= 0 "
            "AND duplicate_count >= 0 AND unresolved_count >= 0",
            name="ck_customer_migration_runs_counts_nonnegative",
        ),
        CheckConstraint(
            "source_count = accepted_count + rejected_count + duplicate_count "
            "+ unresolved_count",
            name="ck_customer_migration_runs_counts_reconcile",
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
    branch_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="RESTRICT"),
        nullable=False,
    )
    initiated_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(50), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unresolved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CustomerSourceIdentity(Base):
    __tablename__ = "customer_source_identities"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "source_system",
            "source_customer_id",
            name="uq_customer_source_identity",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "customer_id",
            name="uq_customer_source_target",
        ),
        UniqueConstraint(
            "id", "company_id", name="uq_customer_source_identities_id_company"
        ),
        UniqueConstraint(
            "id",
            "company_id",
            "customer_id",
            name="uq_customer_source_identities_parent_scope",
        ),
        UniqueConstraint(
            "id",
            "company_id",
            "branch_id",
            "customer_id",
            name="uq_customer_source_identities_branch_scope",
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
    branch_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="RESTRICT"),
        nullable=False,
    )
    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(50), nullable=False)
    source_customer_id: Mapped[str] = mapped_column(String(191), nullable=False)
    first_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CustomerIdentityConsolidationEvidence(Base):
    """Append-only consolidation result for one provider-native Customer identity."""

    __tablename__ = "customer_identity_consolidation_evidence"
    __table_args__ = (
        CheckConstraint(
            "observation_count >= 1", name="ck_customer_identity_consolidation_count"
        ),
        CheckConstraint(
            "outcome IN ('resolved','unresolved','missing_source_identifier',"
            "'duplicate_source_evidence','conflicting_source_evidence','ambiguous_target',"
            "'existing_binding_conflict','company_branch_scope_conflict',"
            "'multiple_native_identities_one_customer')",
            name="ck_customer_identity_consolidation_outcome",
        ),
        CheckConstraint(
            "(outcome = 'resolved') = (customer_source_identity_id IS NOT NULL)",
            name="ck_customer_identity_consolidation_resolved_target",
        ),
        CheckConstraint(
            "(customer_source_identity_id IS NULL) = (customer_id IS NULL)",
            name="ck_customer_identity_consolidation_target_pair",
        ),
        ForeignKeyConstraint(
            ["customer_source_identity_id", "company_id", "branch_id", "customer_id"],
            [
                "customer_source_identities.id",
                "customer_source_identities.company_id",
                "customer_source_identities.branch_id",
                "customer_source_identities.customer_id",
            ],
            name="fk_customer_identity_consolidation_target_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_customer_identity_consolidation_branch_company",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "branch_id",
            "source_system",
            "source_identity_key",
            "evidence_digest",
            name="uq_customer_identity_consolidation_replay",
        ),
        Index(
            "ix_customer_identity_consolidation_review",
            "company_id",
            "branch_id",
            "outcome",
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
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_source_identity_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True)
    )
    customer_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    evaluated_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(50), nullable=False)
    source_entity_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="customer"
    )
    source_identity_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source_customer_id_sha256: Mapped[str | None] = mapped_column(String(64))
    consolidation_contract_version: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    outcome: Mapped[str] = mapped_column(String(60), nullable=False)
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CustomerMigrationCutoverReadinessEvidence(Base):
    """Immutable deterministic cutover-readiness snapshot; never a cutover command."""

    __tablename__ = "customer_migration_cutover_readiness_evidence"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ready_for_owner_review','not_ready')",
            name="ck_customer_cutover_readiness_status",
        ),
        CheckConstraint(
            "confidence_basis_points BETWEEN 0 AND 10000 AND "
            "completeness_basis_points BETWEEN 0 AND 10000",
            name="ck_customer_cutover_readiness_scores",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_customer_cutover_readiness_branch_company",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "branch_id",
            "readiness_key",
            name="uq_customer_cutover_readiness_key",
        ),
        UniqueConstraint(
            "company_id",
            "branch_id",
            "evidence_digest",
            name="uq_customer_cutover_readiness_replay",
        ),
        UniqueConstraint(
            "id",
            "company_id",
            "branch_id",
            name="uq_customer_cutover_readiness_scope",
        ),
        Index(
            "ix_customer_cutover_readiness_latest",
            "company_id",
            "branch_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    evaluated_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    readiness_key: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    ready: Mapped[bool] = mapped_column(Boolean, nullable=False)
    completed_prerequisites: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    missing_prerequisites: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    blocking_conditions: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    owner_disposition_counts: Mapped[dict[str, int]] = mapped_column(
        JSONB, nullable=False
    )
    reconciliation_counts: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    confidence_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    completeness_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CustomerMigrationCutoverPlanEvidence(Base):
    """Immutable deterministic plan evidence with no execution behavior."""

    __tablename__ = "customer_migration_cutover_plan_evidence"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ready_for_owner_approval','blocked')",
            name="ck_customer_cutover_plan_status",
        ),
        ForeignKeyConstraint(
            ["readiness_evidence_id", "company_id", "branch_id"],
            [
                "customer_migration_cutover_readiness_evidence.id",
                "customer_migration_cutover_readiness_evidence.company_id",
                "customer_migration_cutover_readiness_evidence.branch_id",
            ],
            name="fk_customer_cutover_plan_readiness_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_customer_cutover_plan_branch_company",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "branch_id",
            "plan_key",
            name="uq_customer_cutover_plan_key",
        ),
        UniqueConstraint(
            "company_id",
            "branch_id",
            "evidence_digest",
            name="uq_customer_cutover_plan_replay",
        ),
        UniqueConstraint(
            "id",
            "company_id",
            "branch_id",
            name="uq_customer_cutover_plan_scope",
        ),
        Index(
            "ix_customer_cutover_plan_latest", "company_id", "branch_id", "created_at"
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    readiness_evidence_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    planned_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    plan_key: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(100), nullable=False)
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    plan_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    ordered_steps: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False
    )
    dependency_graph: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False
    )
    preconditions: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False
    )
    rollback_prerequisites: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False
    )
    owner_checkpoints: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False
    )
    blocking_conditions: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    required_approvals: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False
    )
    recovery_instructions: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False
    )
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CustomerMigrationCutoverRehearsalEvidence(Base):
    __tablename__ = "customer_migration_cutover_rehearsal_evidence"
    __table_args__ = (
        CheckConstraint(
            "status IN ('simulated_success','blocked','interrupted')",
            name="ck_customer_cutover_rehearsal_status",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_customer_cutover_rehearsal_branch_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["plan_id", "company_id", "branch_id"],
            [
                "customer_migration_cutover_plan_evidence.id",
                "customer_migration_cutover_plan_evidence.company_id",
                "customer_migration_cutover_plan_evidence.branch_id",
            ],
            name="fk_customer_cutover_rehearsal_plan_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "id", "company_id", "branch_id", name="uq_customer_cutover_rehearsal_scope"
        ),
        UniqueConstraint(
            "company_id",
            "branch_id",
            "plan_id",
            "evidence_digest",
            name="uq_customer_cutover_rehearsal_replay",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    plan_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    contract_version: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class CustomerMigrationCutoverRehearsalStepEvidence(Base):
    __tablename__ = "customer_migration_cutover_rehearsal_step_evidence"
    __table_args__ = (
        CheckConstraint(
            "ordinal >= 0", name="ck_customer_cutover_rehearsal_step_ordinal"
        ),
        CheckConstraint(
            "outcome IN ('eligible','simulated_success','blocked','skipped')",
            name="ck_customer_cutover_rehearsal_step_outcome",
        ),
        ForeignKeyConstraint(
            ["rehearsal_id", "company_id", "branch_id"],
            [
                "customer_migration_cutover_rehearsal_evidence.id",
                "customer_migration_cutover_rehearsal_evidence.company_id",
                "customer_migration_cutover_rehearsal_evidence.branch_id",
            ],
            name="fk_customer_cutover_rehearsal_step_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "rehearsal_id", "ordinal", name="uq_customer_cutover_rehearsal_step_order"
        ),
        UniqueConstraint(
            "rehearsal_id",
            "step_id",
            name="uq_customer_cutover_rehearsal_step_identity",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    rehearsal_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    step_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    step_code: Mapped[str] = mapped_column(String(100), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(100))
    recovery_instruction_code: Mapped[str | None] = mapped_column(String(100))
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)


class CustomerMigrationException(Base):
    __tablename__ = "customer_migration_exceptions"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('customer', 'contact', 'service_location')",
            name="ck_customer_migration_exceptions_entity_type",
        ),
        CheckConstraint(
            "disposition IN ('rejected', 'duplicate', 'unresolved')",
            name="ck_customer_migration_exceptions_disposition",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    entity_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="customer"
    )
    source_id_sha256: Mapped[str | None] = mapped_column(String(64))
    disposition: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CustomerContactSourceIdentity(Base):
    __tablename__ = "customer_contact_source_identities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["customer_source_identity_id", "company_id", "customer_id"],
            [
                "customer_source_identities.id",
                "customer_source_identities.company_id",
                "customer_source_identities.customer_id",
            ],
            name="fk_contact_source_identity_customer_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["contact_id", "customer_id"],
            ["customer_contacts.id", "customer_contacts.customer_id"],
            name="fk_contact_source_identity_contact_customer",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "source_contact_id",
            name="uq_customer_contact_source_identity",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "contact_id",
            name="uq_customer_contact_source_target",
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
    customer_source_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    contact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(50), nullable=False)
    source_contact_id: Mapped[str] = mapped_column(String(191), nullable=False)
    first_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ServiceLocationSourceIdentity(Base):
    __tablename__ = "service_location_source_identities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["customer_source_identity_id", "company_id", "customer_id"],
            [
                "customer_source_identities.id",
                "customer_source_identities.company_id",
                "customer_source_identities.customer_id",
            ],
            name="fk_location_source_identity_customer_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["service_location_id", "customer_id"],
            ["service_locations.id", "service_locations.customer_id"],
            name="fk_location_source_identity_location_customer",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "source_location_id",
            name="uq_service_location_source_identity",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "service_location_id",
            name="uq_service_location_source_target",
        ),
        UniqueConstraint(
            "id",
            "company_id",
            "customer_id",
            "service_location_id",
            name="uq_service_location_source_parent_scope",
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
    customer_source_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    service_location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(50), nullable=False)
    source_location_id: Mapped[str] = mapped_column(String(191), nullable=False)
    first_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ServiceLocationIdentityEvidence(Base):
    """Append-only, migration-owned evidence for a provider-native location ID."""

    __tablename__ = "service_location_identity_evidence"
    __table_args__ = (
        CheckConstraint(
            "source_entity_type = 'service_location'",
            name="ck_location_identity_evidence_entity_type",
        ),
        CheckConstraint("evidence_version >= 1", name="ck_location_identity_version"),
        CheckConstraint(
            "readiness IN ('ready', 'reconciliation_required', 'exception')",
            name="ck_location_identity_evidence_readiness",
        ),
        ForeignKeyConstraint(
            ["customer_source_identity_id", "company_id"],
            ["customer_source_identities.id", "customer_source_identities.company_id"],
            name="fk_location_identity_evidence_customer_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_location_identity_evidence_branch_company",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "source_entity_type",
            "observation_sha256",
            "evidence_version",
            name="uq_location_identity_evidence_observation_version",
        ),
        UniqueConstraint(
            "id", "company_id", name="uq_location_identity_evidence_scope"
        ),
        UniqueConstraint(
            "id",
            "company_id",
            "branch_id",
            name="uq_location_identity_evidence_branch_scope",
        ),
        Index(
            "ix_location_identity_evidence_review",
            "company_id",
            "readiness",
            "classification",
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
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_source_identity_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True)
    )
    prior_evidence_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("service_location_identity_evidence.id", ondelete="RESTRICT"),
    )
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(50), nullable=False)
    source_entity_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="service_location"
    )
    observation_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_location_id_sha256: Mapped[str | None] = mapped_column(String(64))
    source_customer_id_sha256: Mapped[str | None] = mapped_column(String(64))
    source_artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_record_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    address_evidence_sha256: Mapped[str | None] = mapped_column(String(64))
    classification: Mapped[str] = mapped_column(String(80), nullable=False)
    readiness: Mapped[str] = mapped_column(String(30), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ServiceLocationReconciliationEvidence(Base):
    """Append-only result of matching native evidence to an Enterprise location."""

    __tablename__ = "service_location_reconciliation_evidence"
    __table_args__ = (
        CheckConstraint(
            "candidate_count >= 0", name="ck_location_reconciliation_candidate_count"
        ),
        CheckConstraint(
            "outcome IN ('matched','no_match','identity_not_ready','duplicate_native_identity',"
            "'ambiguous_address','address_review_required','parent_mismatch',"
            "'existing_binding_conflict','company_branch_scope_conflict')",
            name="ck_location_reconciliation_outcome",
        ),
        CheckConstraint(
            "(outcome = 'matched') = (service_location_id IS NOT NULL)",
            name="ck_location_reconciliation_matched_target",
        ),
        CheckConstraint(
            "(service_location_id IS NULL) = (customer_id IS NULL)",
            name="ck_location_reconciliation_target_pair",
        ),
        ForeignKeyConstraint(
            ["identity_evidence_id", "company_id", "branch_id"],
            [
                "service_location_identity_evidence.id",
                "service_location_identity_evidence.company_id",
                "service_location_identity_evidence.branch_id",
            ],
            name="fk_location_reconciliation_identity_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_location_reconciliation_branch_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["service_location_id", "customer_id"],
            ["service_locations.id", "service_locations.customer_id"],
            name="fk_location_reconciliation_target_customer",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "identity_evidence_id",
            "evidence_digest",
            name="uq_location_reconciliation_replay",
        ),
        Index(
            "ix_location_reconciliation_review", "company_id", "branch_id", "outcome"
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
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    identity_evidence_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    service_location_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    customer_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    evaluated_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    matching_contract_version: Mapped[str] = mapped_column(String(100), nullable=False)
    outcome: Mapped[str] = mapped_column(String(50), nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CustomerMigrationProgress(Base):
    __tablename__ = "customer_migration_progress"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('customer', 'contact', 'service_location')",
            name="ck_customer_migration_progress_entity_type",
        ),
        CheckConstraint(
            "source_count >= 0 AND processed_count >= 0 "
            "AND accepted_count >= 0 AND rejected_count >= 0 "
            "AND duplicate_count >= 0 AND unresolved_count >= 0",
            name="ck_customer_migration_progress_counts_nonnegative",
        ),
        CheckConstraint(
            "processed_count = accepted_count + rejected_count + duplicate_count "
            "+ unresolved_count AND processed_count <= source_count",
            name="ck_customer_migration_progress_counts_reconcile",
        ),
        UniqueConstraint(
            "run_id", "entity_type", name="uq_customer_migration_progress_entity"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False)
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unresolved_count: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class CustomerMigrationSourceArtifact(Base):
    __tablename__ = "customer_migration_source_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "branch_id",
            "source_system",
            "source_sha256",
            name="uq_customer_migration_source_artifact",
        ),
        CheckConstraint("byte_size >= 0", name="ck_customer_source_artifact_size"),
        CheckConstraint("row_count >= 0", name="ck_customer_source_artifact_rows"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(50), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(100), nullable=False)
    transformation_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CustomerMigrationStagingRun(Base):
    __tablename__ = "customer_migration_staging_runs"
    __table_args__ = (
        CheckConstraint(
            "customers_proposed >= 0 AND contacts_proposed >= 0 "
            "AND service_locations_proposed >= 0 "
            "AND billing_addresses_proposed >= 0 AND child_exception_count >= 0 "
            "AND unmapped_field_count >= 0",
            name="ck_customer_staging_run_counts_nonnegative",
        ),
    )

    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_migration_runs.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    artifact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_migration_source_artifacts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reused_staging: Mapped[bool] = mapped_column(Boolean, nullable=False)
    customers_proposed: Mapped[int] = mapped_column(Integer, nullable=False)
    contacts_proposed: Mapped[int] = mapped_column(Integer, nullable=False)
    service_locations_proposed: Mapped[int] = mapped_column(Integer, nullable=False)
    billing_addresses_proposed: Mapped[int] = mapped_column(Integer, nullable=False)
    child_exception_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unmapped_field_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CustomerMigrationSourceRow(Base):
    __tablename__ = "customer_migration_source_rows"
    __table_args__ = (
        CheckConstraint("row_number >= 2", name="ck_customer_source_row_number"),
        CheckConstraint(
            "disposition IN ('accepted', 'rejected', 'duplicate')",
            name="ck_customer_source_row_disposition",
        ),
        UniqueConstraint(
            "artifact_id", "row_number", name="uq_customer_source_row_artifact_row"
        ),
        Index(
            "ix_customer_source_rows_artifact_disposition",
            "artifact_id",
            "disposition",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    artifact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_migration_source_artifacts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_identity: Mapped[str | None] = mapped_column(String(191))
    source_id_sha256: Mapped[str | None] = mapped_column(String(64))
    source_row_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    disposition: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CustomerMigrationCandidate(Base):
    __tablename__ = "customer_migration_candidates"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('customer', 'contact', 'service_location', "
            "'billing_address')",
            name="ck_customer_migration_candidate_entity",
        ),
        CheckConstraint("ordinal >= 0", name="ck_customer_candidate_ordinal"),
        UniqueConstraint(
            "source_row_id",
            "entity_type",
            "ordinal",
            name="uq_customer_candidate_source_entity_ordinal",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    source_row_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_migration_source_rows.id", ondelete="RESTRICT"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CustomerMigrationEvidence(Base):
    __tablename__ = "customer_migration_evidence"
    __table_args__ = (
        CheckConstraint(
            "evidence_type IN ('unmapped_field', 'incomplete_address_group')",
            name="ck_customer_migration_evidence_type",
        ),
        UniqueConstraint(
            "source_row_id",
            "evidence_type",
            "evidence_key",
            name="uq_customer_migration_evidence_source_key",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    source_row_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_migration_source_rows.id", ondelete="RESTRICT"),
        nullable=False,
    )
    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_key: Mapped[str] = mapped_column(String(191), nullable=False)
    evidence_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CustomerMigrationChildException(Base):
    __tablename__ = "customer_migration_child_exceptions"
    __table_args__ = (
        UniqueConstraint(
            "source_row_id",
            "reason_code",
            "address_group_number",
            name="uq_customer_child_exception_source_group",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    source_row_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_migration_source_rows.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_id_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(100), nullable=False)
    address_group_number: Mapped[int] = mapped_column(Integer, nullable=False)
    missing_fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
