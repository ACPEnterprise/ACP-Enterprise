"""Create bounded Payroll cutover review and bridge evidence authority.

Revision ID: i9k1m3o5q7s9
Revises: h8j0l2n4p6r8
"""

from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "i9k1m3o5q7s9"
down_revision = "h8j0l2n4p6r8"
branch_labels = None
depends_on = None

PERMISSIONS = (
    (
        "96f45db6-f17a-58ed-b8aa-dbbef4a28cef",
        "COMPANY_PAYROLL_CUTOVER_READ",
        "cutover_read",
    ),
    (
        "75565bd2-a647-5910-97aa-e82b1f11e4c3",
        "COMPANY_PAYROLL_CUTOVER_OWNER_CERTIFY",
        "cutover_owner_certify",
    ),
    (
        "51b84db5-12ae-58d2-94e0-f47c30f8f87e",
        "COMPANY_PAYROLL_CUTOVER_ACCOUNTANT_CERTIFY",
        "cutover_accountant_certify",
    ),
    (
        "45822116-8510-5a81-a4d6-b782379543ad",
        "COMPANY_PAYROLL_CUTOVER_APPROVE",
        "cutover_approve",
    ),
)


def upgrade() -> None:
    occurred_at = datetime.now(timezone.utc)
    for permission_id, code, action in PERMISSIONS:
        op.execute(
            sa.text(
                "INSERT INTO permissions (id, code, name, description, resource, action, status, created_at, updated_at, retired_at) VALUES (:id, :code, :name, NULL, 'payroll_authority', :action, 'active', :at, :at, NULL) ON CONFLICT (code) DO NOTHING"
            ).bindparams(
                id=UUID(permission_id),
                code=code,
                name=code.replace("_", " ").title(),
                action=action,
                at=occurred_at,
            )
        )
    op.execute(
        sa.text("""
        INSERT INTO role_permissions (id, role_id, permission_id, assigned_at, assigned_by_user_id)
        SELECT (
            substr(md5(r.id::text || p.id::text), 1, 8) || '-' ||
            substr(md5(r.id::text || p.id::text), 9, 4) || '-' ||
            substr(md5(r.id::text || p.id::text), 13, 4) || '-' ||
            substr(md5(r.id::text || p.id::text), 17, 4) || '-' ||
            substr(md5(r.id::text || p.id::text), 21, 12)
        )::uuid, r.id, p.id, :at, NULL
        FROM roles r JOIN permissions p ON p.code IN (
            'COMPANY_PAYROLL_CUTOVER_READ',
            'COMPANY_PAYROLL_CUTOVER_OWNER_CERTIFY',
            'COMPANY_PAYROLL_CUTOVER_APPROVE'
        )
        WHERE r.code IN ('OWNER', 'ADMIN') AND r.archived_at IS NULL
        ON CONFLICT (role_id, permission_id) DO NOTHING
    """).bindparams(at=occurred_at)
    )
    op.create_table(
        "payroll_cutover_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("lifecycle", sa.String(40), nullable=False),
        sa.Column("proposed_legacy_period_end", sa.Date()),
        sa.Column("proposed_acp_period_start", sa.Date()),
        sa.Column("opening_ytd_effective_date", sa.Date()),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "approved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_payroll_cutover_review_version"),
        sa.CheckConstraint(
            "lifecycle IN ('draft','ready_for_certification','certification_in_progress','ready_for_cutover_approval','approved')",
            name="ck_payroll_cutover_review_lifecycle",
        ),
        sa.CheckConstraint(
            "proposed_acp_period_start IS NULL OR proposed_legacy_period_end IS NULL OR proposed_acp_period_start > proposed_legacy_period_end",
            name="ck_payroll_cutover_review_boundary",
        ),
        sa.UniqueConstraint(
            "company_id", "version", name="uq_payroll_cutover_review_version"
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_payroll_cutover_review_company_id"
        ),
    )
    op.create_table(
        "payroll_cutover_fact_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True)),
        sa.Column("fact_key", sa.String(120), nullable=False),
        sa.Column("candidate_reference", postgresql.JSONB(), nullable=False),
        sa.Column("candidate_classification", sa.String(64), nullable=False),
        sa.Column("protected_envelope_id", postgresql.UUID(as_uuid=True)),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("certification_state", sa.String(24), nullable=False),
        sa.Column("certifier_role", sa.String(16), nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("certified_at", sa.DateTime(timezone=True)),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "supersedes_revision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("payroll_cutover_fact_revisions.id", ondelete="RESTRICT"),
        ),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "review_id"],
            ["payroll_cutover_reviews.company_id", "payroll_cutover_reviews.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "protected_envelope_id"],
            [
                "payroll_protected_input_envelopes.company_id",
                "payroll_protected_input_envelopes.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_payroll_cutover_fact_revision"),
        sa.CheckConstraint(
            "action IN ('confirm','correct','provide','not_applicable')",
            name="ck_payroll_cutover_fact_action",
        ),
        sa.CheckConstraint(
            "certification_state IN ('draft','certified','superseded')",
            name="ck_payroll_cutover_fact_state",
        ),
        sa.CheckConstraint(
            "certifier_role IN ('owner','accountant')",
            name="ck_payroll_cutover_fact_role",
        ),
        sa.UniqueConstraint(
            "company_id",
            "review_id",
            "employee_id",
            "fact_key",
            "revision",
            name="uq_payroll_cutover_fact_revision",
        ),
        sa.UniqueConstraint(
            "company_id",
            "actor_user_id",
            "idempotency_key",
            name="uq_payroll_cutover_fact_idempotency",
        ),
        sa.UniqueConstraint(
            "supersedes_revision_id", name="uq_payroll_cutover_fact_successor"
        ),
    )
    op.create_table(
        "payroll_cutover_bridge_periods",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("pay_date", sa.Date(), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("certification_state", sa.String(32), nullable=False),
        sa.Column("source_reference", sa.String(240), nullable=False),
        sa.Column("coverage_complete", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "owner_certified_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("owner_certified_at", sa.DateTime(timezone=True)),
        sa.Column(
            "accountant_certified_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("accountant_certified_at", sa.DateTime(timezone=True)),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "period_end >= period_start", name="ck_payroll_cutover_bridge_dates"
        ),
        sa.CheckConstraint(
            "pay_date >= period_end", name="ck_payroll_cutover_bridge_paydate"
        ),
        sa.CheckConstraint(
            "source_type IN ('manual_paper_check','legacy_provider','other_certified_external')",
            name="ck_payroll_cutover_bridge_source",
        ),
        sa.CheckConstraint(
            "certification_state IN ('draft','owner_certified','accountant_certified','certified','superseded')",
            name="ck_payroll_cutover_bridge_state",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "review_id"],
            ["payroll_cutover_reviews.company_id", "payroll_cutover_reviews.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "company_id",
            "review_id",
            "period_start",
            "period_end",
            "source_type",
            name="uq_payroll_cutover_bridge_period",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_payroll_cutover_bridge_company_id"
        ),
        sa.UniqueConstraint(
            "company_id",
            "actor_user_id",
            "idempotency_key",
            name="uq_payroll_cutover_bridge_idempotency",
        ),
    )
    op.create_table(
        "payroll_cutover_bridge_employee_fact_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bridge_period_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True)),
        sa.Column("source_employee_reference", sa.String(240)),
        sa.Column("fact_key", sa.String(120), nullable=False),
        sa.Column(
            "protected_envelope_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("certification_state", sa.String(24), nullable=False),
        sa.Column("certifier_role", sa.String(16), nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "bridge_period_id"],
            [
                "payroll_cutover_bridge_periods.company_id",
                "payroll_cutover_bridge_periods.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "protected_envelope_id"],
            [
                "payroll_protected_input_envelopes.company_id",
                "payroll_protected_input_envelopes.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "revision >= 1", name="ck_payroll_cutover_bridge_fact_revision"
        ),
        sa.CheckConstraint(
            "certification_state IN ('draft','certified','superseded')",
            name="ck_payroll_cutover_bridge_fact_state",
        ),
        sa.UniqueConstraint(
            "company_id",
            "bridge_period_id",
            "employee_id",
            "source_employee_reference",
            "fact_key",
            "revision",
            name="uq_payroll_cutover_bridge_fact_revision",
        ),
        sa.UniqueConstraint(
            "company_id",
            "actor_user_id",
            "idempotency_key",
            name="uq_payroll_cutover_bridge_fact_idempotency",
        ),
    )


def downgrade() -> None:
    op.drop_table("payroll_cutover_bridge_employee_fact_revisions")
    op.drop_table("payroll_cutover_bridge_periods")
    op.drop_table("payroll_cutover_fact_revisions")
    op.drop_table("payroll_cutover_reviews")
    op.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code IN :codes)"
        ).bindparams(
            sa.bindparam(
                "codes", expanding=True, value=tuple(code for _, code, _ in PERMISSIONS)
            )
        )
    )
    op.execute(
        sa.text("DELETE FROM permissions WHERE code IN :codes").bindparams(
            sa.bindparam(
                "codes", expanding=True, value=tuple(code for _, code, _ in PERMISSIONS)
            )
        )
    )
