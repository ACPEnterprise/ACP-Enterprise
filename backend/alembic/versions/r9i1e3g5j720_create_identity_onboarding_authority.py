"""create protected identity onboarding authority

Revision ID: r9i1e3g5j720
Revises: r9h1d3f5j720
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "r9i1e3g5j720"
down_revision: str | None = "r9h1d3f5j720"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("uq_employees_active_company_employee_number", table_name="employees")
    op.create_index(
        "uq_employees_company_employee_number_permanent",
        "employees",
        ["company_id", "employee_number"],
        unique=True,
    )
    op.create_table(
        "employee_number_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("prefix", sa.String(20), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("next_value", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("next_value >= 1", name="ck_employee_number_next_positive"),
        sa.CheckConstraint("width BETWEEN 1 AND 20", name="ck_employee_number_width"),
        sa.UniqueConstraint("company_id", name="uq_employee_number_policy_company"),
    )
    op.create_table(
        "identity_onboarding_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "branch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("branches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("masked_login", sa.String(320), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "initiated_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('pending','invited','activated','revoked')",
            name="ck_identity_onboarding_request_status",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "membership_id"],
            ["memberships.company_id", "memberships.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "company_id", "request_key", name="uq_identity_onboarding_request_key"
        ),
        sa.UniqueConstraint("employee_id", name="uq_identity_onboarding_employee"),
    )
    op.create_table(
        "identity_onboarding_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "onboarding_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_onboarding_requests.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "issued_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "superseded_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_onboarding_invitations.id", ondelete="RESTRICT"),
        ),
        sa.Column("safe_digest", sa.String(64), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','consumed','expired','revoked','superseded')",
            name="ck_identity_onboarding_invitation_status",
        ),
        sa.UniqueConstraint(
            "token_hash", name="uq_identity_onboarding_invitation_hash"
        ),
    )
    op.create_index(
        "ix_identity_onboarding_invitation_request",
        "identity_onboarding_invitations",
        ["onboarding_request_id", "created_at"],
    )
    op.create_table(
        "protected_invitation_delivery_envelopes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "invitation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_onboarding_invitations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("key_id", sa.String(100), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("destroyed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('pending','claimed','delivered','destroyed')",
            name="ck_protected_invitation_envelope_status",
        ),
        sa.UniqueConstraint(
            "invitation_id", name="uq_protected_invitation_envelope_invitation"
        ),
    )


def downgrade() -> None:
    op.drop_table("protected_invitation_delivery_envelopes")
    op.drop_index(
        "ix_identity_onboarding_invitation_request",
        table_name="identity_onboarding_invitations",
    )
    op.drop_table("identity_onboarding_invitations")
    op.drop_table("identity_onboarding_requests")
    op.drop_table("employee_number_policies")
    op.drop_index(
        "uq_employees_company_employee_number_permanent", table_name="employees"
    )
    op.create_index(
        "uq_employees_active_company_employee_number",
        "employees",
        ["company_id", "employee_number"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )
