"""create customer management tables

Revision ID: 8f3c2d1a9b47
Revises: 218775b8a49c
Create Date: 2026-07-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8f3c2d1a9b47"
down_revision: Union[str, Sequence[str], None] = "218775b8a49c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=True),
        sa.Column("customer_type", sa.String(length=20), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("business_name", sa.String(length=200), nullable=True),
        sa.Column("normalized_name", sa.String(length=300), nullable=False),
        sa.Column("primary_phone", sa.String(length=30), nullable=False),
        sa.Column("normalized_primary_phone", sa.String(length=20), nullable=False),
        sa.Column("secondary_phone", sa.String(length=30), nullable=True),
        sa.Column("normalized_secondary_phone", sa.String(length=20), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("normalized_email", sa.String(length=320), nullable=True),
        sa.Column("preferred_contact_method", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("is_vip", sa.Boolean(), nullable=False),
        sa.Column("internal_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "customer_type IN ('individual', 'business')",
            name="ck_customers_customer_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive', 'do_not_service')",
            name="ck_customers_status",
        ),
        sa.CheckConstraint(
            "preferred_contact_method IN ('phone', 'sms', 'email')",
            name="ck_customers_preferred_contact_method",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customers_archived_at", "customers", ["archived_at"])
    op.create_index("ix_customers_company_id", "customers", ["company_id"])
    op.create_index("ix_customers_normalized_email", "customers", ["normalized_email"])
    op.create_index("ix_customers_normalized_name", "customers", ["normalized_name"])
    op.create_index(
        "ix_customers_normalized_primary_phone",
        "customers",
        ["normalized_primary_phone"],
    )
    op.create_index(
        "ix_customers_normalized_secondary_phone",
        "customers",
        ["normalized_secondary_phone"],
    )
    op.create_index(
        "ix_customers_active_updated",
        "customers",
        ["updated_at", "id"],
        postgresql_where=sa.text("archived_at IS NULL"),
    )

    op.create_table(
        "customer_properties",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("address_line_1", sa.String(length=200), nullable=False),
        sa.Column("address_line_2", sa.String(length=200), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=2), nullable=False),
        sa.Column("postal_code", sa.String(length=10), nullable=False),
        sa.Column("normalized_address", sa.String(length=500), nullable=False),
        sa.Column("property_type", sa.String(length=30), nullable=False),
        sa.Column("gate_access_instructions", sa.Text(), nullable=True),
        sa.Column("water_shutoff_location", sa.Text(), nullable=True),
        sa.Column("sewer_septic", sa.String(length=20), nullable=True),
        sa.Column("property_notes", sa.Text(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "property_type IN ('single_family', 'multi_family', 'commercial', "
            "'condo', 'townhome', 'mobile_home', 'other')",
            name="ck_customer_properties_property_type",
        ),
        sa.CheckConstraint(
            "sewer_septic IS NULL OR sewer_septic IN ('sewer', 'septic', 'unknown')",
            name="ck_customer_properties_sewer_septic",
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_customer_properties_archived_at", "customer_properties", ["archived_at"]
    )
    op.create_index(
        "ix_customer_properties_customer_id", "customer_properties", ["customer_id"]
    )
    op.create_index(
        "ix_customer_properties_normalized_address",
        "customer_properties",
        ["normalized_address"],
    )
    op.create_index(
        "uq_customer_properties_active_primary",
        "customer_properties",
        ["customer_id"],
        unique=True,
        postgresql_where=sa.text("is_primary AND archived_at IS NULL"),
    )

    op.create_table(
        "customer_contacts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("relationship_or_role", sa.String(length=100), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("normalized_phone", sa.String(length=20), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("normalized_email", sa.String(length=320), nullable=True),
        sa.Column("is_preferred", sa.Boolean(), nullable=False),
        sa.Column("can_approve_work", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_customer_contacts_archived_at", "customer_contacts", ["archived_at"]
    )
    op.create_index(
        "ix_customer_contacts_customer_id", "customer_contacts", ["customer_id"]
    )
    op.create_index(
        "ix_customer_contacts_normalized_email",
        "customer_contacts",
        ["normalized_email"],
    )
    op.create_index(
        "ix_customer_contacts_normalized_phone",
        "customer_contacts",
        ["normalized_phone"],
    )
    op.create_index(
        "uq_customer_contacts_active_preferred",
        "customer_contacts",
        ["customer_id"],
        unique=True,
        postgresql_where=sa.text("is_preferred AND archived_at IS NULL"),
    )

    op.create_table(
        "customer_notes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("author_user_id", sa.UUID(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_customer_notes_author_user_id", "customer_notes", ["author_user_id"]
    )
    op.create_index("ix_customer_notes_created_at", "customer_notes", ["created_at"])
    op.create_index("ix_customer_notes_customer_id", "customer_notes", ["customer_id"])


def downgrade() -> None:
    op.drop_index("ix_customer_notes_customer_id", table_name="customer_notes")
    op.drop_index("ix_customer_notes_created_at", table_name="customer_notes")
    op.drop_index("ix_customer_notes_author_user_id", table_name="customer_notes")
    op.drop_table("customer_notes")
    op.drop_index(
        "uq_customer_contacts_active_preferred", table_name="customer_contacts"
    )
    op.drop_index(
        "ix_customer_contacts_normalized_phone", table_name="customer_contacts"
    )
    op.drop_index(
        "ix_customer_contacts_normalized_email", table_name="customer_contacts"
    )
    op.drop_index("ix_customer_contacts_customer_id", table_name="customer_contacts")
    op.drop_index("ix_customer_contacts_archived_at", table_name="customer_contacts")
    op.drop_table("customer_contacts")
    op.drop_index(
        "uq_customer_properties_active_primary", table_name="customer_properties"
    )
    op.drop_index(
        "ix_customer_properties_normalized_address", table_name="customer_properties"
    )
    op.drop_index(
        "ix_customer_properties_customer_id", table_name="customer_properties"
    )
    op.drop_index(
        "ix_customer_properties_archived_at", table_name="customer_properties"
    )
    op.drop_table("customer_properties")
    op.drop_index("ix_customers_active_updated", table_name="customers")
    op.drop_index("ix_customers_normalized_secondary_phone", table_name="customers")
    op.drop_index("ix_customers_normalized_primary_phone", table_name="customers")
    op.drop_index("ix_customers_normalized_name", table_name="customers")
    op.drop_index("ix_customers_normalized_email", table_name="customers")
    op.drop_index("ix_customers_company_id", table_name="customers")
    op.drop_index("ix_customers_archived_at", table_name="customers")
    op.drop_table("customers")
