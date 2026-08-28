"""expand economics policy authority

Revision ID: d5u7q9s1v386
Revises: c4t6p8r0u275
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d5u7q9s1v386"
down_revision: str | Sequence[str] | None = "c4t6p8r0u275"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "economics_company_policy_versions",
        sa.Column(
            "disposition", sa.String(20), nullable=False, server_default="selected"
        ),
    )
    op.alter_column(
        "economics_company_policy_versions", "disposition", server_default=None
    )
    op.alter_column(
        "economics_company_policy_versions",
        "strategy_key",
        existing_type=sa.String(100),
        nullable=True,
    )
    op.create_check_constraint(
        "ck_eco_policy_disposition",
        "economics_company_policy_versions",
        "disposition IN ('selected','deferred')",
    )
    op.add_column(
        "economics_policy_snapshots",
        sa.Column(
            "deferred_family_keys",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.alter_column(
        "economics_policy_snapshots", "deferred_family_keys", server_default=None
    )
    op.create_table(
        "economics_company_policy_parameters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("family_key", sa.String(100), nullable=False),
        sa.Column("parameter_key", sa.String(100), nullable=False),
        sa.Column("parameter_version", sa.Integer(), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("effective_start", sa.Date(), nullable=False),
        sa.Column("effective_end", sa.Date()),
        sa.Column("definition_version", sa.String(80), nullable=False),
        sa.Column("parameter_digest", sa.String(64), nullable=False),
        sa.Column(
            "approved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("parameter_version >= 1", name="ck_eco_parameter_version"),
        sa.CheckConstraint(
            "branch_id IS NULL", name="ck_eco_parameter_company_scope_v1"
        ),
        sa.CheckConstraint(
            "effective_end IS NULL OR effective_end > effective_start",
            name="ck_eco_parameter_interval",
        ),
        sa.UniqueConstraint(
            "company_id",
            "family_key",
            "parameter_key",
            "parameter_version",
            name="uq_eco_parameter_version",
        ),
    )
    op.create_index(
        "ix_eco_parameter_resolution",
        "economics_company_policy_parameters",
        ["company_id", "family_key", "parameter_key", "effective_start"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_eco_parameter_resolution", table_name="economics_company_policy_parameters"
    )
    op.drop_table("economics_company_policy_parameters")
    op.drop_column("economics_policy_snapshots", "deferred_family_keys")
    op.drop_constraint(
        "ck_eco_policy_disposition", "economics_company_policy_versions", type_="check"
    )
    op.alter_column(
        "economics_company_policy_versions",
        "strategy_key",
        existing_type=sa.String(100),
        nullable=False,
    )
    op.drop_column("economics_company_policy_versions", "disposition")
