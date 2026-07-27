"""Add Customer migration child identity and progress controls.

Revision ID: f1c7d9e3b825
Revises: e8b4c6d2a917
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f1c7d9e3b825"
down_revision: str | Sequence[str] | None = "e8b4c6d2a917"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "customer_migration_exceptions",
        sa.Column(
            "entity_type",
            sa.String(length=30),
            nullable=False,
            server_default="customer",
        ),
    )
    op.create_check_constraint(
        "ck_customer_migration_exceptions_entity_type",
        "customer_migration_exceptions",
        "entity_type IN ('customer', 'contact', 'service_location')",
    )
    op.alter_column("customer_migration_exceptions", "entity_type", server_default=None)
    op.create_unique_constraint(
        "uq_customer_source_identities_id_company",
        "customer_source_identities",
        ["id", "company_id"],
    )
    op.create_unique_constraint(
        "uq_customer_source_identities_parent_scope",
        "customer_source_identities",
        ["id", "company_id", "customer_id"],
    )
    op.create_unique_constraint(
        "uq_service_locations_id_customer_id",
        "service_locations",
        ["id", "customer_id"],
    )
    op.create_table(
        "customer_contact_source_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "customer_source_identity_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("source_contact_id", sa.String(length=191), nullable=False),
        sa.Column("first_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["contact_id", "customer_id"],
            ["customer_contacts.id", "customer_contacts.customer_id"],
            name="fk_contact_source_identity_contact_customer",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_source_identity_id", "company_id", "customer_id"],
            [
                "customer_source_identities.id",
                "customer_source_identities.company_id",
                "customer_source_identities.customer_id",
            ],
            name="fk_contact_source_identity_customer_company",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["first_run_id"], ["customer_migration_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "source_contact_id",
            name="uq_customer_contact_source_identity",
        ),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "contact_id",
            name="uq_customer_contact_source_target",
        ),
    )
    op.create_table(
        "service_location_source_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "customer_source_identity_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("service_location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("source_location_id", sa.String(length=191), nullable=False),
        sa.Column("first_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["customer_source_identity_id", "company_id", "customer_id"],
            [
                "customer_source_identities.id",
                "customer_source_identities.company_id",
                "customer_source_identities.customer_id",
            ],
            name="fk_location_source_identity_customer_company",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["first_run_id"], ["customer_migration_runs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["service_location_id", "customer_id"],
            ["service_locations.id", "service_locations.customer_id"],
            name="fk_location_source_identity_location_customer",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "source_location_id",
            name="uq_service_location_source_identity",
        ),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "service_location_id",
            name="uq_service_location_source_target",
        ),
    )
    op.create_table(
        "customer_migration_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=30), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("processed_count", sa.Integer(), nullable=False),
        sa.Column("accepted_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("unresolved_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('customer', 'contact', 'service_location')",
            name="ck_customer_migration_progress_entity_type",
        ),
        sa.CheckConstraint(
            "source_count >= 0 AND processed_count >= 0 "
            "AND accepted_count >= 0 AND rejected_count >= 0 "
            "AND duplicate_count >= 0 AND unresolved_count >= 0",
            name="ck_customer_migration_progress_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "processed_count = accepted_count + rejected_count + duplicate_count "
            "+ unresolved_count AND processed_count <= source_count",
            name="ck_customer_migration_progress_counts_reconcile",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["customer_migration_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id", "entity_type", name="uq_customer_migration_progress_entity"
        ),
    )


def downgrade() -> None:
    op.drop_table("customer_migration_progress")
    op.drop_table("service_location_source_identities")
    op.drop_table("customer_contact_source_identities")
    op.drop_constraint(
        "uq_service_locations_id_customer_id",
        "service_locations",
        type_="unique",
    )
    op.drop_constraint(
        "uq_customer_source_identities_parent_scope",
        "customer_source_identities",
        type_="unique",
    )
    op.drop_constraint(
        "uq_customer_source_identities_id_company",
        "customer_source_identities",
        type_="unique",
    )
    op.drop_constraint(
        "ck_customer_migration_exceptions_entity_type",
        "customer_migration_exceptions",
        type_="check",
    )
    op.drop_column("customer_migration_exceptions", "entity_type")
