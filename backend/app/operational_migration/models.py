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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class HcpMigrationMasterRun(Base):
    """Authoritative envelope for one full HCP rehearsal execution."""

    __tablename__ = "hcp_migration_master_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('prepared','running','interrupted','completed','failed')",
            name="ck_hcp_master_run_status",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_hcp_master_run_branch_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id", "branch_id", "input_digest", name="uq_hcp_master_input"
        ),
        UniqueConstraint(
            "company_id",
            "branch_id",
            "package_digest",
            name="uq_hcp_master_package_scope",
        ),
        UniqueConstraint(
            "id", "company_id", "branch_id", name="uq_hcp_master_run_scope"
        ),
        UniqueConstraint(
            "id",
            "company_id",
            "branch_id",
            "actor_user_id",
            name="uq_hcp_master_run_actor_scope",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    package_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    collection_digests: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    transformation_contracts: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False
    )
    owner_receipts: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    schema_head: Mapped[str] = mapped_column(String(32), nullable=False)
    implementation_version: Mapped[str] = mapped_column(String(100), nullable=False)
    supported_entities: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    baseline_counts: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    source_counts: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    transformed_counts: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    persisted_counts: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    hold_counts: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    exception_counts: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    rejection_counts: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    unresolved_counts: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    non_applicable_counts: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    child_run_ids: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    reconciliation_digest: Mapped[str | None] = mapped_column(String(64))
    replay_state: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    resume_state: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    rollback_state: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    attestation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class HcpCustomerSourceLineage(Base):
    __tablename__ = "hcp_customer_source_lineage"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_hcp_customer_lineage_branch_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id", "native_customer_id", name="uq_hcp_customer_lineage_native"
        ),
        UniqueConstraint(
            "company_id", "evidence_digest", name="uq_hcp_customer_lineage_replay"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    master_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("hcp_migration_master_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    customer_source_identity_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_source_identities.id", ondelete="RESTRICT"),
    )
    native_customer_id: Mapped[str] = mapped_column(String(191), nullable=False)
    package_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    transformation_contract: Mapped[str] = mapped_column(String(100), nullable=False)
    transformation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_disposition: Mapped[str | None] = mapped_column(String(100))
    source_timestamps: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    source_context: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class HcpEmployeeSourceCrosswalk(Base):
    __tablename__ = "hcp_employee_source_crosswalks"
    __table_args__ = (
        CheckConstraint(
            "disposition IN ('CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE',"
            "'EXCLUDE_EMPLOYEE_HOLD_ASSIGNMENTS')",
            name="ck_hcp_employee_crosswalk_disposition",
        ),
        CheckConstraint(
            "disposition <> 'EXCLUDE_EMPLOYEE_HOLD_ASSIGNMENTS' OR employee_id IS NULL",
            name="ck_hcp_employee_crosswalk_excluded_no_target",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_hcp_employee_crosswalk_branch_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "native_employee_id",
            "evidence_version",
            name="uq_hcp_employee_crosswalk_version",
        ),
        UniqueConstraint(
            "company_id", "evidence_digest", name="uq_hcp_employee_crosswalk_replay"
        ),
        Index(
            "uq_hcp_employee_crosswalk_target",
            "company_id",
            "employee_id",
            unique=True,
            postgresql_where=text("employee_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    master_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hcp_migration_master_runs.id"), nullable=False
    )
    prior_evidence_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hcp_employee_source_crosswalks.id")
    )
    employee_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT")
    )
    native_employee_id: Mapped[str] = mapped_column(String(191), nullable=False)
    disposition: Mapped[str] = mapped_column(String(100), nullable=False)
    package_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_receipt_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_version: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class HcpMigrationHold(Base):
    __tablename__ = "hcp_migration_holds"
    __table_args__ = (
        CheckConstraint("state IN ('HELD','RELEASED')", name="ck_hcp_hold_state"),
        CheckConstraint(
            "operational_effects_enabled = false AND financial_truth_accepted = false",
            name="ck_hcp_hold_no_effects",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_hcp_hold_branch_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "master_run_id",
            "entity_kind",
            "native_id",
            name="uq_hcp_hold_native_run",
        ),
        UniqueConstraint("company_id", "hold_digest", name="uq_hcp_hold_replay"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    master_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hcp_migration_master_runs.id"), nullable=False
    )
    prior_hold_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hcp_migration_holds.id")
    )
    entity_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    native_id: Mapped[str] = mapped_column(String(191), nullable=False)
    hold_code: Mapped[str] = mapped_column(String(100), nullable=False)
    owner_disposition: Mapped[str | None] = mapped_column(String(100))
    package_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    reconciliation_key: Mapped[str] = mapped_column(String(191), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    hold_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_version: Mapped[int] = mapped_column(Integer, nullable=False)
    operational_effects_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    financial_truth_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class HcpMigrationPlanOutcome(Base):
    """Non-operational evidence for a builder-classified source outcome."""

    __tablename__ = "hcp_migration_plan_outcomes"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('EXPLICIT_EXCEPTION','REJECTED','INTENTIONALLY_NON_APPLICABLE')",
            name="ck_hcp_plan_outcome_class",
        ),
        CheckConstraint(
            "operational_effects_enabled = false AND financial_truth_accepted = false",
            name="ck_hcp_plan_outcome_no_effects",
        ),
        ForeignKeyConstraint(
            ["master_run_id", "company_id", "branch_id"],
            [
                "hcp_migration_master_runs.id",
                "hcp_migration_master_runs.company_id",
                "hcp_migration_master_runs.branch_id",
            ],
            name="fk_hcp_plan_outcome_master_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "master_run_id",
            "entity_kind",
            "native_identity_sha256",
            name="uq_hcp_plan_outcome_native",
        ),
        UniqueConstraint(
            "company_id", "outcome_digest", name="uq_hcp_plan_outcome_replay"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    master_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    entity_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    native_identity_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    package_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    transformation_version: Mapped[str] = mapped_column(String(100), nullable=False)
    outcome_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    operational_effects_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    financial_truth_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class OperationalMigrationRun(Base):
    __tablename__ = "operational_migration_runs"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('dry_run', 'import')",
            name="ck_operational_migration_runs_mode",
        ),
        CheckConstraint(
            "status IN ('running', 'interrupted', 'completed', "
            "'completed_with_exceptions', 'failed')",
            name="ck_operational_migration_runs_status",
        ),
        CheckConstraint(
            "source_count = accepted_count + rejected_count + duplicate_count "
            "+ unresolved_count",
            name="ck_operational_migration_runs_reconcile",
        ),
        CheckConstraint(
            "source_system <> 'housecall_pro_source4' OR "
            "(master_run_id IS NOT NULL AND "
            "master_domain IN ('operational','financial','history'))",
            name="ck_operational_source4_master_required",
        ),
        ForeignKeyConstraint(
            ["master_run_id", "company_id", "branch_id", "initiated_by_user_id"],
            [
                "hcp_migration_master_runs.id",
                "hcp_migration_master_runs.company_id",
                "hcp_migration_master_runs.branch_id",
                "hcp_migration_master_runs.actor_user_id",
            ],
            name="fk_operational_run_master_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "master_run_id",
            "master_domain",
            "repair_generation",
            name="uq_operational_master_domain_generation",
        ),
        UniqueConstraint(
            "id", "company_id", "branch_id", name="uq_operational_run_scope"
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
    master_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    master_domain: Mapped[str | None] = mapped_column(String(20))
    repair_of_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operational_migration_runs.id", ondelete="RESTRICT"),
    )
    repair_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_system: Mapped[str] = mapped_column(String(80), nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unresolved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HcpMigrationChildAdmission(Base):
    """Immutable plan-conformance decision for a master child execution."""

    __tablename__ = "hcp_migration_child_admissions"
    __table_args__ = (
        CheckConstraint(
            "domain IN ('customer','operational','financial','history')",
            name="ck_hcp_child_admission_domain",
        ),
        CheckConstraint(
            "conformance IN ('PLAN_CONFORMING','PLAN_NONCONFORMING')",
            name="ck_hcp_child_admission_conformance",
        ),
        ForeignKeyConstraint(
            ["master_run_id", "company_id", "branch_id"],
            [
                "hcp_migration_master_runs.id",
                "hcp_migration_master_runs.company_id",
                "hcp_migration_master_runs.branch_id",
            ],
            name="fk_hcp_child_admission_master_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "master_run_id", "domain", "child_run_id", name="uq_hcp_child_admission"
        ),
        UniqueConstraint(
            "master_run_id",
            "domain",
            "admission_digest",
            name="uq_hcp_child_admission_replay",
        ),
        Index(
            "uq_hcp_child_admission_conforming_domain",
            "master_run_id",
            "domain",
            unique=True,
            postgresql_where=text("conformance = 'PLAN_CONFORMING'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    master_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    child_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    domain: Mapped[str] = mapped_column(String(20), nullable=False)
    execution_status: Mapped[str] = mapped_column(String(40), nullable=False)
    conformance: Mapped[str] = mapped_column(String(30), nullable=False)
    plan_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_counts: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    actual_counts: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    admission_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class HcpMigrationChildRepair(Base):
    """Evidence-preserving lineage for a nonconforming child requalification."""

    __tablename__ = "hcp_migration_child_repairs"
    __table_args__ = (
        CheckConstraint(
            "domain IN ('operational','financial','history')",
            name="ck_hcp_child_repair_domain",
        ),
        CheckConstraint(
            "status IN ('qualified','running','completed','failed')",
            name="ck_hcp_child_repair_status",
        ),
        CheckConstraint(
            "repair_generation >= 1", name="ck_hcp_child_repair_generation"
        ),
        ForeignKeyConstraint(
            ["master_run_id", "company_id", "branch_id"],
            [
                "hcp_migration_master_runs.id",
                "hcp_migration_master_runs.company_id",
                "hcp_migration_master_runs.branch_id",
            ],
            name="fk_hcp_child_repair_master_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["original_child_run_id", "company_id", "branch_id"],
            [
                "operational_migration_runs.id",
                "operational_migration_runs.company_id",
                "operational_migration_runs.branch_id",
            ],
            name="fk_hcp_child_repair_original_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "master_run_id",
            "domain",
            "repair_digest",
            name="uq_hcp_child_repair_replay",
        ),
        UniqueConstraint(
            "id", "company_id", "branch_id", name="uq_hcp_child_repair_scope"
        ),
        UniqueConstraint(
            "master_run_id",
            "domain",
            "repair_generation",
            name="uq_hcp_child_repair_generation",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    master_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    original_child_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    repair_child_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operational_migration_runs.id", ondelete="RESTRICT"),
    )
    parent_repair_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("hcp_migration_child_repairs.id", ondelete="RESTRICT"),
    )
    failed_child_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operational_migration_runs.id", ondelete="RESTRICT"),
    )
    sequence_plan_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "hcp_appointment_sequence_plans.id",
            name="fk_hcp_child_repair_sequence_plan",
            ondelete="RESTRICT",
            use_alter=True,
        ),
    )
    repair_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    domain: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    original_plan_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    repair_plan_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    immutable_input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    repair_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HcpAppointmentSequencePlan(Base):
    """Append-only authority superseding Appointment projection semantics."""

    __tablename__ = "hcp_appointment_sequence_plans"
    __table_args__ = (
        CheckConstraint(
            "generation >= 1", name="ck_hcp_appointment_sequence_plan_generation"
        ),
        CheckConstraint(
            "status IN ('qualified','applied','superseded')",
            name="ck_hcp_appointment_sequence_plan_status",
        ),
        ForeignKeyConstraint(
            ["master_run_id", "company_id", "branch_id"],
            [
                "hcp_migration_master_runs.id",
                "hcp_migration_master_runs.company_id",
                "hcp_migration_master_runs.branch_id",
            ],
            name="fk_hcp_appointment_sequence_plan_master_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["repair_id", "company_id", "branch_id"],
            [
                "hcp_migration_child_repairs.id",
                "hcp_migration_child_repairs.company_id",
                "hcp_migration_child_repairs.branch_id",
            ],
            name="fk_hcp_appointment_sequence_plan_repair_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "master_run_id",
            "plan_digest",
            name="uq_hcp_appointment_sequence_plan_digest",
        ),
        UniqueConstraint(
            "id",
            "company_id",
            "branch_id",
            name="uq_hcp_appointment_sequence_plan_scope",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    master_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    repair_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    original_plan_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    superseded_repair_plan_digest: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    sequencing_contract_version: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    sequencing_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    checkpoint_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    retained_identity_digests: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    remaining_identity_digests: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    plan_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class HcpAppointmentSequenceCorrection(Base):
    """Immutable before/after evidence for a target visit-order reprojection."""

    __tablename__ = "hcp_appointment_sequence_corrections"
    __table_args__ = (
        CheckConstraint(
            "prior_sequence >= 1", name="ck_hcp_appointment_correction_prior"
        ),
        CheckConstraint(
            "corrected_sequence >= 1", name="ck_hcp_appointment_correction_corrected"
        ),
        CheckConstraint(
            "status IN ('qualified','applied')",
            name="ck_hcp_appointment_correction_status",
        ),
        ForeignKeyConstraint(
            ["sequence_plan_id", "company_id", "branch_id"],
            [
                "hcp_appointment_sequence_plans.id",
                "hcp_appointment_sequence_plans.company_id",
                "hcp_appointment_sequence_plans.branch_id",
            ],
            name="fk_hcp_appointment_correction_plan_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "sequence_plan_id",
            "appointment_link_id",
            name="uq_hcp_appointment_correction_link",
        ),
        UniqueConstraint(
            "sequence_plan_id",
            "correction_digest",
            name="uq_hcp_appointment_correction_digest",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    sequence_plan_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    appointment_link_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("job_appointment_links.id", ondelete="RESTRICT"),
        nullable=False,
    )
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    appointment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    failed_child_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    prior_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    corrected_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    source_identity_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    correction_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OperationalMigrationProgress(Base):
    __tablename__ = "operational_migration_progress"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('job', 'appointment', 'estimate', 'invoice', 'payment')",
            name="ck_operational_migration_progress_entity",
        ),
        CheckConstraint(
            "processed_count = accepted_count + rejected_count + duplicate_count "
            "+ unresolved_count AND processed_count <= source_count",
            name="ck_operational_migration_progress_reconcile",
        ),
        UniqueConstraint(
            "run_id", "entity_type", name="uq_operational_migration_progress_entity"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operational_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False)
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unresolved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class OperationalMigrationException(Base):
    __tablename__ = "operational_migration_exceptions"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('job', 'appointment', 'estimate', 'invoice', 'payment')",
            name="ck_operational_migration_exceptions_entity",
        ),
        CheckConstraint(
            "disposition IN ('rejected', 'duplicate', 'unresolved')",
            name="ck_operational_migration_exceptions_disposition",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operational_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    record_index: Mapped[int] = mapped_column(Integer, nullable=False)
    source_id_sha256: Mapped[str | None] = mapped_column(String(64))
    disposition: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class UnlinkedEstimateEvidence(Base):
    """Immutable, non-operational source evidence with no Job relationship."""

    __tablename__ = "operational_migration_unlinked_estimate_evidence"
    __table_args__ = (
        CheckConstraint(
            "disposition = 'UNLINKED_NON_OPERATIONAL_ESTIMATE'",
            name="ck_unlinked_estimate_evidence_disposition",
        ),
        CheckConstraint(
            "job_relationship_state = 'ABSENT'",
            name="ck_unlinked_estimate_job_absent",
        ),
        CheckConstraint(
            "operational_effects_enabled = false AND accounting_truth_accepted = false",
            name="ck_unlinked_estimate_non_operational",
        ),
        CheckConstraint(
            "master_run_id IS NOT NULL OR synthetic_qualification = true",
            name="ck_unlinked_estimate_master_or_synthetic",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_unlinked_estimate_evidence_branch_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["master_run_id", "company_id", "branch_id", "recorded_by_user_id"],
            [
                "hcp_migration_master_runs.id",
                "hcp_migration_master_runs.company_id",
                "hcp_migration_master_runs.branch_id",
                "hcp_migration_master_runs.actor_user_id",
            ],
            name="fk_unlinked_estimate_master_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "native_estimate_id",
            name="uq_unlinked_estimate_evidence_native_identity",
        ),
        UniqueConstraint(
            "company_id",
            "branch_id",
            "evidence_digest",
            name="uq_unlinked_estimate_evidence_replay",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    master_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
    )
    synthetic_qualification: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    source_system: Mapped[str] = mapped_column(String(80), nullable=False)
    native_estimate_id: Mapped[str] = mapped_column(String(191), nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    package_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_binding_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    native_customer_id: Mapped[str | None] = mapped_column(String(191))
    native_service_location_id: Mapped[str | None] = mapped_column(String(191))
    source_status: Mapped[str] = mapped_column(String(100), nullable=False)
    option_evidence: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False
    )
    source_timestamps: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    source_context: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    disposition: Mapped[str] = mapped_column(String(80), nullable=False)
    job_relationship_state: Mapped[str] = mapped_column(String(20), nullable=False)
    reconciliation_state: Mapped[str] = mapped_column(String(40), nullable=False)
    operational_effects_enabled: Mapped[bool] = mapped_column(nullable=False)
    accounting_truth_accepted: Mapped[bool] = mapped_column(nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class JobSourceIdentity(Base):
    __tablename__ = "operational_migration_job_source_identities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_job_source_identity_job_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["customer_source_identity_id", "company_id", "customer_id"],
            [
                "customer_source_identities.id",
                "customer_source_identities.company_id",
                "customer_source_identities.customer_id",
            ],
            name="fk_job_source_identity_customer_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "service_location_source_identity_id",
                "company_id",
                "customer_id",
                "service_location_id",
            ],
            [
                "service_location_source_identities.id",
                "service_location_source_identities.company_id",
                "service_location_source_identities.customer_id",
                "service_location_source_identities.service_location_id",
            ],
            name="fk_job_source_identity_location_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "source_job_id",
            name="uq_job_source_identity",
        ),
        UniqueConstraint(
            "company_id", "source_system", "job_id", name="uq_job_source_target"
        ),
        UniqueConstraint(
            "id",
            "company_id",
            "branch_id",
            "job_id",
            "customer_id",
            "service_location_id",
            name="uq_job_source_parent_scope",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    service_location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    customer_source_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    service_location_source_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    source_system: Mapped[str] = mapped_column(String(80), nullable=False)
    source_job_id: Mapped[str] = mapped_column(String(191), nullable=False)
    source_job_number: Mapped[str | None] = mapped_column(String(191))
    source_status: Mapped[str] = mapped_column(String(40), nullable=False)
    assigned_technician_source_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    external_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    first_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operational_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AppointmentSourceIdentity(Base):
    __tablename__ = "operational_migration_appointment_source_identities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "appointment_id"],
            ["appointments.company_id", "appointments.branch_id", "appointments.id"],
            name="fk_appointment_source_identity_appointment_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "job_source_identity_id",
                "company_id",
                "branch_id",
                "job_id",
                "customer_id",
                "service_location_id",
            ],
            [
                "operational_migration_job_source_identities.id",
                "operational_migration_job_source_identities.company_id",
                "operational_migration_job_source_identities.branch_id",
                "operational_migration_job_source_identities.job_id",
                "operational_migration_job_source_identities.customer_id",
                "operational_migration_job_source_identities.service_location_id",
            ],
            name="fk_appointment_source_identity_job_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "source_appointment_id",
            name="uq_appointment_source_identity",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "appointment_id",
            name="uq_appointment_source_target",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    appointment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    job_source_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    service_location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    source_system: Mapped[str] = mapped_column(String(80), nullable=False)
    source_appointment_id: Mapped[str] = mapped_column(String(191), nullable=False)
    source_status: Mapped[str] = mapped_column(String(40), nullable=False)
    assigned_technician_source_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    external_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    first_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operational_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EstimateSourceIdentity(Base):
    __tablename__ = "operational_migration_estimate_source_identities"
    __table_args__ = (
        ForeignKeyConstraint(
            [
                "company_id",
                "branch_id",
                "estimate_id",
                "customer_id",
                "service_location_id",
            ],
            [
                "estimates.company_id",
                "estimates.branch_id",
                "estimates.id",
                "estimates.customer_id",
                "estimates.service_location_id",
            ],
            name="fk_estimate_source_identity_estimate_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "job_source_identity_id",
                "company_id",
                "branch_id",
                "job_id",
                "customer_id",
                "service_location_id",
            ],
            [
                "operational_migration_job_source_identities.id",
                "operational_migration_job_source_identities.company_id",
                "operational_migration_job_source_identities.branch_id",
                "operational_migration_job_source_identities.job_id",
                "operational_migration_job_source_identities.customer_id",
                "operational_migration_job_source_identities.service_location_id",
            ],
            name="fk_estimate_source_identity_job_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "source_estimate_id",
            name="uq_estimate_source_identity",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "estimate_id",
            name="uq_estimate_source_target",
        ),
        UniqueConstraint(
            "id", "company_id", "estimate_id", name="uq_estimate_source_parent_scope"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    estimate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    job_source_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    service_location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    source_system: Mapped[str] = mapped_column(String(80), nullable=False)
    source_estimate_id: Mapped[str] = mapped_column(String(191), nullable=False)
    source_status: Mapped[str] = mapped_column(String(40), nullable=False)
    external_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    first_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operational_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EstimateLineItemSourceIdentity(Base):
    __tablename__ = "operational_migration_estimate_line_item_source_identities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["estimate_source_identity_id", "company_id", "estimate_id"],
            [
                "operational_migration_estimate_source_identities.id",
                "operational_migration_estimate_source_identities.company_id",
                "operational_migration_estimate_source_identities.estimate_id",
            ],
            name="fk_estimate_item_source_parent",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "estimate_id", "estimate_line_item_id"],
            [
                "estimate_line_items.company_id",
                "estimate_line_items.estimate_id",
                "estimate_line_items.id",
            ],
            name="fk_estimate_item_source_target",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "source_line_item_id",
            name="uq_estimate_item_source_identity",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "estimate_line_item_id",
            name="uq_estimate_item_source_target",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    estimate_source_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    estimate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    estimate_line_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    source_system: Mapped[str] = mapped_column(String(80), nullable=False)
    source_line_item_id: Mapped[str] = mapped_column(String(191), nullable=False)
    first_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operational_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class InvoiceSourceIdentity(Base):
    __tablename__ = "operational_migration_invoice_source_identities"
    __table_args__ = (
        ForeignKeyConstraint(
            [
                "company_id",
                "branch_id",
                "invoice_id",
                "customer_id",
                "service_location_id",
            ],
            [
                "invoices.company_id",
                "invoices.branch_id",
                "invoices.id",
                "invoices.customer_id",
                "invoices.service_location_id",
            ],
            name="fk_invoice_source_identity_invoice_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "job_source_identity_id",
                "company_id",
                "branch_id",
                "job_id",
                "customer_id",
                "service_location_id",
            ],
            [
                "operational_migration_job_source_identities.id",
                "operational_migration_job_source_identities.company_id",
                "operational_migration_job_source_identities.branch_id",
                "operational_migration_job_source_identities.job_id",
                "operational_migration_job_source_identities.customer_id",
                "operational_migration_job_source_identities.service_location_id",
            ],
            name="fk_invoice_source_identity_job_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "source_invoice_id",
            name="uq_invoice_source_identity",
        ),
        UniqueConstraint(
            "company_id", "source_system", "invoice_id", name="uq_invoice_source_target"
        ),
        UniqueConstraint(
            "id",
            "company_id",
            "branch_id",
            "invoice_id",
            "customer_id",
            name="uq_invoice_source_parent_scope",
        ),
        UniqueConstraint(
            "id",
            "company_id",
            "invoice_id",
            name="uq_invoice_source_line_item_scope",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    invoice_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    job_source_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    service_location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    source_system: Mapped[str] = mapped_column(String(80), nullable=False)
    source_invoice_id: Mapped[str] = mapped_column(String(191), nullable=False)
    source_status: Mapped[str] = mapped_column(String(40), nullable=False)
    external_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    first_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operational_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class InvoiceLineItemSourceIdentity(Base):
    __tablename__ = "operational_migration_invoice_line_item_source_identities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["invoice_source_identity_id", "company_id", "invoice_id"],
            [
                "operational_migration_invoice_source_identities.id",
                "operational_migration_invoice_source_identities.company_id",
                "operational_migration_invoice_source_identities.invoice_id",
            ],
            name="fk_invoice_item_source_parent",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "invoice_id", "invoice_line_item_id"],
            [
                "invoice_line_items.company_id",
                "invoice_line_items.invoice_id",
                "invoice_line_items.id",
            ],
            name="fk_invoice_item_source_target",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "source_line_item_id",
            name="uq_invoice_item_source_identity",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "invoice_line_item_id",
            name="uq_invoice_item_source_target",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    invoice_source_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    invoice_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    invoice_line_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    source_system: Mapped[str] = mapped_column(String(80), nullable=False)
    source_line_item_id: Mapped[str] = mapped_column(String(191), nullable=False)
    first_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operational_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class PaymentSourceIdentity(Base):
    __tablename__ = "operational_migration_payment_source_identities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "payment_id", "invoice_id", "customer_id"],
            [
                "payments.company_id",
                "payments.branch_id",
                "payments.id",
                "payments.invoice_id",
                "payments.customer_id",
            ],
            name="fk_payment_source_identity_payment_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "invoice_source_identity_id",
                "company_id",
                "branch_id",
                "invoice_id",
                "customer_id",
            ],
            [
                "operational_migration_invoice_source_identities.id",
                "operational_migration_invoice_source_identities.company_id",
                "operational_migration_invoice_source_identities.branch_id",
                "operational_migration_invoice_source_identities.invoice_id",
                "operational_migration_invoice_source_identities.customer_id",
            ],
            name="fk_payment_source_identity_invoice_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "source_payment_id",
            name="uq_payment_source_identity",
        ),
        UniqueConstraint(
            "company_id", "source_system", "payment_id", name="uq_payment_source_target"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    payment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    invoice_source_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    invoice_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_system: Mapped[str] = mapped_column(String(80), nullable=False)
    source_payment_id: Mapped[str] = mapped_column(String(191), nullable=False)
    source_status: Mapped[str] = mapped_column(String(40), nullable=False)
    external_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    first_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operational_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
