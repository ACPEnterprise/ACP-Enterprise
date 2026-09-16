"""Persistence models for generic Finance/Economics policy authority."""

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
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


class CompanyFinancePolicyVersion(Base):
    __tablename__ = "economics_company_policy_versions"
    __table_args__ = (
        CheckConstraint("policy_version >= 1", name="ck_eco_policy_version"),
        CheckConstraint(
            "lifecycle IN ('draft','approved','superseded','retired')",
            name="ck_eco_policy_lifecycle",
        ),
        CheckConstraint(
            "disposition IN ('selected','deferred')",
            name="ck_eco_policy_disposition",
        ),
        CheckConstraint(
            "effective_end IS NULL OR effective_end > effective_start",
            name="ck_eco_policy_interval",
        ),
        CheckConstraint("branch_id IS NULL", name="ck_eco_policy_company_scope_v1"),
        UniqueConstraint(
            "company_id",
            "family_key",
            "policy_version",
            name="uq_eco_policy_family_version",
        ),
        UniqueConstraint("company_id", "id", name="uq_eco_policy_company_id"),
        Index(
            "ix_eco_policy_resolution",
            "company_id",
            "family_key",
            "lifecycle",
            "effective_start",
            "effective_end",
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
    family_key: Mapped[str] = mapped_column(String(100), nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy_key: Mapped[str | None] = mapped_column(String(100))
    disposition: Mapped[str] = mapped_column(String(20), nullable=False)
    parameters: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    evidence_acceptance_rule_refs: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    effective_start: Mapped[date] = mapped_column(Date, nullable=False)
    effective_end: Mapped[date | None] = mapped_column(Date)
    lifecycle: Mapped[str] = mapped_column(String(20), nullable=False)
    definition_version: Mapped[str] = mapped_column(String(80), nullable=False)
    decision_evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    supersedes_policy_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("economics_company_policy_versions.id", ondelete="RESTRICT"),
    )
    drafted_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    audit_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class JobDirectExpenseAllocation(Base):
    """Immutable certified split from one exact source line to one Job."""

    __tablename__ = "economics_job_direct_expense_allocations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_eco_direct_expense_job",
            ondelete="RESTRICT",
        ),
        CheckConstraint("allocation_version >= 1", name="ck_eco_expense_version"),
        CheckConstraint("amount_minor > 0", name="ck_eco_expense_amount"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_eco_expense_currency"),
        CheckConstraint(
            "status IN ('draft','ready_for_certification','certified','superseded','inactive')",
            name="ck_eco_expense_status",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "source_record_type",
            "source_transaction_id",
            "source_line_id",
            "allocation_version",
            "job_id",
            name="uq_eco_expense_source_version_job",
        ),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_eco_expense_idempotency"
        ),
        UniqueConstraint("company_id", "id", name="uq_eco_expense_company_id"),
        Index(
            "ix_eco_expense_job_period",
            "company_id",
            "branch_id",
            "job_id",
            "effective_date",
            "status",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_system: Mapped[str] = mapped_column(String(40), nullable=False)
    source_record_type: Mapped[str] = mapped_column(String(60), nullable=False)
    source_transaction_id: Mapped[str] = mapped_column(String(191), nullable=False)
    source_line_id: Mapped[str] = mapped_column(String(191), nullable=False)
    source_evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    allocation_version: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    allocation_basis: Mapped[str] = mapped_column(String(40), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    allocation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    supersedes_allocation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("economics_job_direct_expense_allocations.id", ondelete="RESTRICT"),
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    expected_prior_version: Mapped[int | None] = mapped_column(Integer)
    drafted_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    certified_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    certified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class FinancePolicySnapshotRecord(Base):
    __tablename__ = "economics_policy_snapshots"
    __table_args__ = (
        CheckConstraint("branch_id IS NULL", name="ck_eco_snapshot_company_scope_v1"),
        UniqueConstraint(
            "company_id", "snapshot_digest", name="uq_eco_snapshot_digest"
        ),
        Index("ix_eco_snapshot_replay", "company_id", "subject_identity", "as_of_date"),
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
    subject_identity: Mapped[str] = mapped_column(String(200), nullable=False)
    reconciliation_key: Mapped[str] = mapped_column(String(240), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    policy_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    policy_digests: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    deferred_family_keys: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    parameter_gap_digests: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    definition_version: Mapped[str] = mapped_column(String(80), nullable=False)
    snapshot_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CompanyFinancePolicyParameter(Base):
    __tablename__ = "economics_company_policy_parameters"
    __table_args__ = (
        CheckConstraint("parameter_version >= 1", name="ck_eco_parameter_version"),
        CheckConstraint("branch_id IS NULL", name="ck_eco_parameter_company_scope_v1"),
        CheckConstraint(
            "effective_end IS NULL OR effective_end > effective_start",
            name="ck_eco_parameter_interval",
        ),
        UniqueConstraint(
            "company_id",
            "family_key",
            "parameter_key",
            "parameter_version",
            name="uq_eco_parameter_version",
        ),
        Index(
            "ix_eco_parameter_resolution",
            "company_id",
            "family_key",
            "parameter_key",
            "effective_start",
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
    family_key: Mapped[str] = mapped_column(String(100), nullable=False)
    parameter_key: Mapped[str] = mapped_column(String(100), nullable=False)
    parameter_version: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[object] = mapped_column(JSONB, nullable=False)
    effective_start: Mapped[date] = mapped_column(Date, nullable=False)
    effective_end: Mapped[date | None] = mapped_column(Date)
    definition_version: Mapped[str] = mapped_column(String(80), nullable=False)
    parameter_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CompanyFinancePolicyGap(Base):
    __tablename__ = "economics_company_policy_gaps"
    __table_args__ = (
        CheckConstraint("branch_id IS NULL", name="ck_eco_policy_gap_company_scope_v1"),
        CheckConstraint(
            "state IN ('open','satisfied','conflicting','superseded')",
            name="ck_eco_policy_gap_state",
        ),
        UniqueConstraint(
            "company_id",
            "family_key",
            "gap_key",
            "effective_start",
            name="uq_eco_policy_gap_identity",
        ),
        Index("ix_eco_policy_gap_open", "company_id", "family_key", "state"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    family_key: Mapped[str] = mapped_column(String(100), nullable=False)
    gap_key: Mapped[str] = mapped_column(String(120), nullable=False)
    requirement: Mapped[str] = mapped_column(Text, nullable=False)
    authority_dependency: Mapped[str] = mapped_column(String(200), nullable=False)
    effective_start: Mapped[date] = mapped_column(Date, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    decision_evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    gap_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    registered_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class EvidenceAcceptanceContractRecord(Base):
    __tablename__ = "economics_evidence_acceptance_contracts"
    __table_args__ = (
        UniqueConstraint(
            "contract_id",
            "contract_version",
            name="uq_eco_acceptance_contract_version",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    contract_id: Mapped[str] = mapped_column(String(200), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(80), nullable=False)
    family_key: Mapped[str] = mapped_column(String(100), nullable=False)
    gap_key: Mapped[str] = mapped_column(String(120), nullable=False)
    definition: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    contract_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EvidenceAcceptanceGrantRecord(Base):
    __tablename__ = "economics_evidence_acceptance_grants"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "grant_id", name="uq_eco_acceptance_grant_identity"
        ),
        UniqueConstraint(
            "company_id", "grant_digest", name="uq_eco_acceptance_grant_digest"
        ),
        Index(
            "ix_eco_acceptance_grant_replay",
            "company_id",
            "contract_id",
            "subject_id",
            "effective_start",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    grant_id: Mapped[str] = mapped_column(String(200), nullable=False)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    subject_id: Mapped[str] = mapped_column(String(200), nullable=False)
    contract_id: Mapped[str] = mapped_column(String(200), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence_id: Mapped[str] = mapped_column(String(240), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    authority: Mapped[str] = mapped_column(String(160), nullable=False)
    effective_start: Mapped[date] = mapped_column(Date, nullable=False)
    effective_end: Mapped[date | None] = mapped_column(Date)
    approved_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    grant_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class PolicyGapClosureRecord(Base):
    __tablename__ = "economics_policy_gap_closures"
    __table_args__ = (
        CheckConstraint(
            "state IN ('open','satisfied','conflicting','superseded')",
            name="ck_eco_gap_closure_state",
        ),
        UniqueConstraint(
            "company_id", "closure_digest", name="uq_eco_gap_closure_digest"
        ),
        Index(
            "ix_eco_gap_closure_replay",
            "company_id",
            "gap_id",
            "effective_date",
            "as_of",
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
    gap_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("economics_company_policy_gaps.id", ondelete="RESTRICT"),
        nullable=False,
    )
    subject_id: Mapped[str] = mapped_column(String(200), nullable=False)
    reconciliation_key: Mapped[str] = mapped_column(String(240), nullable=False)
    contract_id: Mapped[str] = mapped_column(String(200), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(80), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    evidence_digests: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    authorities: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provisional: Mapped[bool] = mapped_column(nullable=False)
    limitations: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    supersedes_closure_id: Mapped[str | None] = mapped_column(String(128))
    closure_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EconomicsProfitabilityResultRecord(Base):
    """Immutable admitted profitability result and explanation lineage."""

    __tablename__ = "economics_profitability_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_eco_profitability_result_company_branch",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "lifecycle IN ('admitted','superseded','voided')",
            name="ck_eco_profitability_result_lifecycle",
        ),
        UniqueConstraint(
            "company_id", "result_identity", name="uq_eco_profitability_result_identity"
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_eco_profitability_result_company_id"
        ),
        Index(
            "ix_eco_profitability_result_subject",
            "company_id",
            "subject_id",
            "period_start",
            "period_end",
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
    subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    subject_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    basis: Mapped[str] = mapped_column(String(32), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    admission_id: Mapped[str] = mapped_column(String(128), nullable=False)
    admission_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    package_id: Mapped[str] = mapped_column(String(128), nullable=False)
    package_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    computation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    result_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    result_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    metrics: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    components: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    quality: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    explanation: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    acquisition_digests: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    allocation_digests: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    explanation_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EconomicsProfitabilityResultSupersessionRecord(Base):
    """Immutable edge between two immutable results in one economic lineage."""

    __tablename__ = "economics_profitability_result_supersessions"
    __table_args__ = (
        CheckConstraint(
            "predecessor_result_id <> successor_result_id",
            name="ck_eco_profitability_supersession_distinct",
        ),
        CheckConstraint(
            "reason IN ('source_correction','policy_recomputation',"
            "'computation_version','attribution_correction')",
            name="ck_eco_profitability_supersession_reason",
        ),
        ForeignKeyConstraint(
            ["company_id", "predecessor_result_id"],
            [
                "economics_profitability_results.company_id",
                "economics_profitability_results.id",
            ],
            name="fk_eco_profitability_supersession_predecessor",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "successor_result_id"],
            [
                "economics_profitability_results.company_id",
                "economics_profitability_results.id",
            ],
            name="fk_eco_profitability_supersession_successor",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "predecessor_result_id", name="uq_eco_profitability_single_successor"
        ),
        UniqueConstraint(
            "successor_result_id", name="uq_eco_profitability_single_predecessor"
        ),
        UniqueConstraint(
            "company_id", "supersession_digest", name="uq_eco_supersession_digest"
        ),
        Index(
            "ix_eco_profitability_supersession_lineage",
            "company_id",
            "subject_id",
            "period_start",
            "period_end",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    predecessor_result_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    successor_result_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    subject_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    basis: Mapped[str] = mapped_column(String(32), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    predecessor_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    successor_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    predecessor_package_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    successor_package_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    predecessor_computation_digest: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    successor_computation_digest: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    supersession_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
