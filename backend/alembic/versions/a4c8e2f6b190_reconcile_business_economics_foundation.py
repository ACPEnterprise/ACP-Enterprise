"""reconcile business economics foundation

Revision ID: a4c8e2f6b190
Revises: f3a7c9e1b524
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a4c8e2f6b190"
down_revision: str | Sequence[str] | None = "f3a7c9e1b524"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "business_economics_facts",
        sa.Column("fact_key", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "business_economics_facts",
        sa.Column("period_start", sa.Date(), nullable=True),
    )
    op.add_column(
        "business_economics_facts",
        sa.Column("period_end", sa.Date(), nullable=True),
    )
    op.add_column(
        "business_economics_facts",
        sa.Column("measurement_method", sa.String(length=80), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE business_economics_facts SET "
            "fact_key = category, period_start = occurred_at::date, "
            "period_end = occurred_at::date, measurement_method = 'legacy_recorded_fact'"
        )
    )
    for column in ("fact_key", "period_start", "period_end", "measurement_method"):
        op.alter_column("business_economics_facts", column, nullable=False)
    op.create_check_constraint(
        "ck_business_economics_facts_period",
        "business_economics_facts",
        "period_end >= period_start",
    )
    op.create_unique_constraint(
        "uq_business_economics_facts_company_id",
        "business_economics_facts",
        ["company_id", "id"],
    )
    op.create_unique_constraint(
        "uq_business_economics_facts_version",
        "business_economics_facts",
        [
            "company_id",
            "subject_type",
            "subject_id",
            "fact_key",
            "period_start",
            "period_end",
            "version",
        ],
    )

    op.create_table(
        "business_economics_evidence_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("source_system", sa.String(length=80), nullable=False),
        sa.Column("source_record_type", sa.String(length=80), nullable=False),
        sa.Column("reference_id", sa.String(length=160), nullable=False),
        sa.Column("source_version", sa.String(length=80), nullable=False),
        sa.Column("content_digest", sa.String(length=64), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("business_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('business_event', 'source_record', 'allocation', 'reasoning')",
            name="ck_business_economics_evidence_kind",
        ),
        sa.CheckConstraint(
            "length(content_digest) = 64",
            name="ck_business_economics_evidence_digest",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["business_event_id"], ["business_events.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_business_economics_evidence_company_id"
        ),
        sa.UniqueConstraint(
            "company_id",
            "kind",
            "source_system",
            "source_record_type",
            "reference_id",
            "source_version",
            name="uq_business_economics_evidence_source_version",
        ),
    )
    op.create_table(
        "business_economics_fact_evidence",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "fact_id"],
            ["business_economics_facts.company_id", "business_economics_facts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "evidence_id"],
            [
                "business_economics_evidence_references.company_id",
                "business_economics_evidence_references.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("company_id", "fact_id", "evidence_id"),
    )
    # Preserve Phase 1 evidence snapshots while promoting their identities into
    # the normalized authoritative evidence ledger.
    op.execute(
        sa.text(
            "INSERT INTO business_economics_evidence_references "
            "(id, company_id, kind, source_system, source_record_type, reference_id, "
            "source_version, content_digest, explanation, observed_at, recorded_at) "
            "SELECT gen_random_uuid(), company_id, item->>'kind', item->>'source_system', "
            "COALESCE(item->>'source_record_type', 'legacy_reference'), "
            "item->>'reference_id', item->>'source_version', "
            "COALESCE(NULLIF(item->>'content_digest', ''), "
            "md5(item::text) || md5('economics:' || item::text)), "
            "item->>'explanation', "
            "COALESCE((item->>'observed_at')::timestamptz, occurred_at), recorded_at "
            "FROM business_economics_facts, jsonb_array_elements(evidence) item "
            "ON CONFLICT ON CONSTRAINT uq_business_economics_evidence_source_version "
            "DO NOTHING"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO business_economics_fact_evidence (company_id, fact_id, evidence_id) "
            "SELECT fact.company_id, fact.id, evidence.id "
            "FROM business_economics_facts fact "
            "CROSS JOIN LATERAL jsonb_array_elements(fact.evidence) item "
            "JOIN business_economics_evidence_references evidence ON "
            "evidence.company_id = fact.company_id AND evidence.kind = item->>'kind' AND "
            "evidence.source_system = item->>'source_system' AND "
            "evidence.source_record_type = COALESCE(item->>'source_record_type', 'legacy_reference') AND "
            "evidence.reference_id = item->>'reference_id' AND "
            "evidence.source_version = item->>'source_version' "
            "ON CONFLICT DO NOTHING"
        )
    )

    op.create_table(
        "business_economics_allocation_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_key", sa.String(length=80), nullable=False),
        sa.Column("strategy", sa.String(length=64), nullable=False),
        sa.Column("driver_fact_key", sa.String(length=80), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "version >= 1", name="ck_business_economics_policies_version"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_business_economics_policies_company_id"
        ),
        sa.UniqueConstraint(
            "company_id",
            "policy_key",
            "version",
            name="uq_business_economics_policies_version",
        ),
    )
    op.create_table(
        "business_economics_allocation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_fact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("allocated_amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("residual_amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column("confidence_status", sa.String(length=12), nullable=False),
        sa.Column("confidence_percentage", sa.Integer(), nullable=False),
        sa.Column("confidence_explanation", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_amount_minor = allocated_amount_minor + residual_amount_minor",
            name="ck_business_economics_allocation_runs_reconcile",
        ),
        sa.CheckConstraint(
            "confidence_status IN ('measured', 'estimated', 'unknown')",
            name="ck_business_economics_allocation_runs_confidence_status",
        ),
        sa.CheckConstraint(
            "confidence_percentage BETWEEN 0 AND 100",
            name="ck_business_economics_allocation_runs_confidence_percentage",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "policy_id"],
            [
                "business_economics_allocation_policies.company_id",
                "business_economics_allocation_policies.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "source_fact_id"],
            ["business_economics_facts.company_id", "business_economics_facts.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_business_economics_allocation_runs_company_id"
        ),
        sa.UniqueConstraint(
            "company_id",
            "input_digest",
            name="uq_business_economics_allocation_runs_input",
        ),
    )
    op.add_column(
        "business_economics_allocations",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_business_economics_allocations_run_id",
        "business_economics_allocations",
        "business_economics_allocation_runs",
        ["run_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    for name, type_ in (
        ("period_start", sa.Date()),
        ("period_end", sa.Date()),
        ("input_fact_ids", postgresql.JSONB(astext_type=sa.Text())),
        ("input_allocation_ids", postgresql.JSONB(astext_type=sa.Text())),
    ):
        op.add_column(
            "business_economics_profit_measurements",
            sa.Column(name, type_, nullable=True),
        )
    op.execute(
        sa.text(
            "UPDATE business_economics_profit_measurements SET "
            "period_start = measured_at::date, period_end = measured_at::date, "
            "input_fact_ids = '[]'::jsonb, input_allocation_ids = '[]'::jsonb"
        )
    )
    for column in (
        "period_start",
        "period_end",
        "input_fact_ids",
        "input_allocation_ids",
    ):
        op.alter_column(
            "business_economics_profit_measurements", column, nullable=False
        )
    op.create_check_constraint(
        "ck_business_economics_profit_measurements_period",
        "business_economics_profit_measurements",
        "period_end >= period_start",
    )
    op.create_unique_constraint(
        "uq_business_economics_profit_measurements_version",
        "business_economics_profit_measurements",
        [
            "company_id",
            "subject_type",
            "subject_id",
            "period_start",
            "period_end",
            "version",
        ],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_business_economics_profit_measurements_version",
        "business_economics_profit_measurements",
        type_="unique",
    )
    op.drop_constraint(
        "ck_business_economics_profit_measurements_period",
        "business_economics_profit_measurements",
        type_="check",
    )
    for column in (
        "input_allocation_ids",
        "input_fact_ids",
        "period_end",
        "period_start",
    ):
        op.drop_column("business_economics_profit_measurements", column)
    op.drop_constraint(
        "fk_business_economics_allocations_run_id",
        "business_economics_allocations",
        type_="foreignkey",
    )
    op.drop_column("business_economics_allocations", "run_id")
    op.drop_table("business_economics_allocation_runs")
    op.drop_table("business_economics_allocation_policies")
    op.drop_table("business_economics_fact_evidence")
    op.drop_table("business_economics_evidence_references")
    op.drop_constraint(
        "uq_business_economics_facts_version",
        "business_economics_facts",
        type_="unique",
    )
    op.drop_constraint(
        "uq_business_economics_facts_company_id",
        "business_economics_facts",
        type_="unique",
    )
    op.drop_constraint(
        "ck_business_economics_facts_period",
        "business_economics_facts",
        type_="check",
    )
    for column in ("measurement_method", "period_end", "period_start", "fact_key"):
        op.drop_column("business_economics_facts", column)
