"""create protected pay statement experience authority

Revision ID: 14d9f34539f3
Revises: 13c8f23428e2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "14d9f34539f3"
down_revision: str | Sequence[str] | None = "13c8f23428e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_payroll_pay_statement_company_id",
        "payroll_pay_statements",
        ["company_id", "id"],
    )
    op.create_table(
        "payroll_pay_statement_artifacts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("statement_id", sa.UUID(), nullable=False),
        sa.Column("statement_digest", sa.String(64), nullable=False),
        sa.Column("render_contract_version", sa.String(80), nullable=False),
        sa.Column("template_version", sa.String(80), nullable=False),
        sa.Column("renderer_version", sa.String(80), nullable=False),
        sa.Column("media_type", sa.String(80), nullable=False),
        sa.Column("artifact_digest", sa.String(64), nullable=False),
        sa.Column("artifact_identity", sa.String(128), nullable=False),
        sa.Column("storage_reference", sa.String(128), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("lifecycle", sa.String(16), nullable=False),
        sa.Column("retention_state", sa.String(24), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "lifecycle IN ('generated','retained','superseded','voided')",
            name="ck_payroll_pay_statement_artifact_lifecycle",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "statement_id"],
            ["payroll_pay_statements.company_id", "payroll_pay_statements.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "artifact_identity",
            name="uq_payroll_pay_statement_artifact_identity",
        ),
        sa.UniqueConstraint(
            "company_id",
            "storage_reference",
            name="uq_payroll_pay_statement_artifact_storage",
        ),
    )
    op.create_index(
        "ix_payroll_pay_statement_artifact_statement",
        "payroll_pay_statement_artifacts",
        ["company_id", "statement_id", "created_at"],
    )
    op.create_table(
        "payroll_pay_statement_deliveries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("statement_id", sa.UUID(), nullable=False),
        sa.Column("statement_digest", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("link_target", sa.String(256), nullable=False),
        sa.Column("provider_identity", sa.String(80), nullable=False),
        sa.Column("provider_version", sa.String(40), nullable=False),
        sa.Column("delivery_identity", sa.String(128), nullable=False),
        sa.Column("delivery_digest", sa.String(64), nullable=False),
        sa.Column("lifecycle", sa.String(16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "channel IN ('authenticated_web','authenticated_app','email_link','push_link')",
            name="ck_payroll_pay_statement_delivery_channel",
        ),
        sa.CheckConstraint(
            "lifecycle IN ('prepared','acknowledged','failed','revoked')",
            name="ck_payroll_pay_statement_delivery_lifecycle",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "statement_id"],
            ["payroll_pay_statements.company_id", "payroll_pay_statements.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "delivery_identity",
            name="uq_payroll_pay_statement_delivery_identity",
        ),
    )
    op.create_index(
        "ix_payroll_pay_statement_delivery_statement",
        "payroll_pay_statement_deliveries",
        ["company_id", "statement_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payroll_pay_statement_delivery_statement",
        table_name="payroll_pay_statement_deliveries",
    )
    op.drop_table("payroll_pay_statement_deliveries")
    op.drop_index(
        "ix_payroll_pay_statement_artifact_statement",
        table_name="payroll_pay_statement_artifacts",
    )
    op.drop_table("payroll_pay_statement_artifacts")
    op.drop_constraint(
        "uq_payroll_pay_statement_company_id", "payroll_pay_statements", type_="unique"
    )
