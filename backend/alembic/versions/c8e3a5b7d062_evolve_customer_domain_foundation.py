"""evolve customer domain foundation

Revision ID: c8e3a5b7d062
Revises: b7d2f4a6c951
Create Date: 2026-07-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c8e3a5b7d062"
down_revision: Union[str, Sequence[str], None] = "b7d2f4a6c951"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM customers WHERE company_id IS NULL) THEN
                RAISE EXCEPTION
                    'Customer Company ownership must be backfilled before Sprint 6 migration';
            END IF;
        END $$
        """
    )

    op.create_table(
        "customer_number_sequences",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_value", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "last_value >= 0", name="ck_customer_number_sequences_last_value"
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_customer_number_sequences_company_id_companies",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("company_id", name="pk_customer_number_sequences"),
    )

    op.drop_constraint("ck_customers_customer_type", "customers", type_="check")
    op.drop_constraint("ck_customers_status", "customers", type_="check")
    op.execute(
        "UPDATE customers SET customer_type = CASE "
        "WHEN customer_type = 'individual' THEN 'residential' ELSE 'commercial' END"
    )
    op.execute(
        "UPDATE customers SET status = 'inactive' WHERE status = 'do_not_service'"
    )
    op.alter_column(
        "customers",
        "customer_type",
        existing_type=sa.String(length=20),
        type_=sa.String(length=30),
        existing_nullable=False,
    )
    op.add_column("customers", sa.Column("customer_number", sa.String(20)))
    op.add_column("customers", sa.Column("display_name", sa.String(300)))
    op.add_column("customers", sa.Column("legal_name", sa.String(300)))
    op.add_column(
        "customers", sa.Column("primary_contact_id", postgresql.UUID(as_uuid=True))
    )
    op.add_column(
        "customers",
        sa.Column(
            "tax_exempt", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.execute(
        """
        UPDATE customers
        SET display_name = COALESCE(
            NULLIF(btrim(business_name), ''),
            NULLIF(btrim(concat_ws(' ', first_name, last_name)), ''),
            'Legacy Customer'
        ),
        legal_name = NULLIF(btrim(business_name), '')
        """
    )
    op.execute(
        """
        WITH numbered AS (
            SELECT id, row_number() OVER (
                PARTITION BY company_id ORDER BY created_at, id
            ) AS sequence_value
            FROM customers
        )
        UPDATE customers AS customer
        SET customer_number = 'CUS-' || lpad(numbered.sequence_value::text, 6, '0')
        FROM numbered
        WHERE customer.id = numbered.id
        """
    )
    op.execute(
        """
        INSERT INTO customer_number_sequences (company_id, last_value, updated_at)
        SELECT company_id, count(*), now()
        FROM customers
        GROUP BY company_id
        """
    )
    op.alter_column(
        "customers", "company_id", existing_type=postgresql.UUID(), nullable=False
    )
    op.alter_column(
        "customers", "customer_number", existing_type=sa.String(20), nullable=False
    )
    op.alter_column(
        "customers", "display_name", existing_type=sa.String(300), nullable=False
    )
    op.alter_column(
        "customers", "primary_phone", existing_type=sa.String(30), nullable=True
    )
    op.alter_column(
        "customers",
        "normalized_primary_phone",
        existing_type=sa.String(20),
        nullable=True,
    )
    op.alter_column(
        "customers",
        "source",
        existing_type=sa.String(50),
        type_=sa.String(100),
        nullable=True,
    )
    op.create_foreign_key(
        "fk_customers_company_id_companies",
        "customers",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_customers_primary_contact_id_customer_contacts",
        "customers",
        "customer_contacts",
        ["primary_contact_id"],
        ["id"],
        ondelete="RESTRICT",
        use_alter=True,
    )
    op.create_check_constraint(
        "ck_customers_customer_type",
        "customers",
        "customer_type IN ('residential', 'commercial', 'municipal', 'hoa', "
        "'property_management')",
    )
    op.create_check_constraint(
        "ck_customers_status",
        "customers",
        "status IN ('prospect', 'active', 'inactive')",
    )
    op.create_check_constraint(
        "ck_customers_customer_number_format",
        "customers",
        "customer_number ~ '^CUS-[0-9]{6,}$'",
    )
    op.create_check_constraint(
        "ck_customers_display_name_not_blank",
        "customers",
        "length(btrim(display_name)) > 0",
    )
    op.create_unique_constraint(
        "uq_customers_company_id_customer_number",
        "customers",
        ["company_id", "customer_number"],
    )
    for index_name in (
        "ix_customers_company_id",
        "ix_customers_archived_at",
        "ix_customers_normalized_email",
        "ix_customers_normalized_name",
        "ix_customers_normalized_primary_phone",
        "ix_customers_normalized_secondary_phone",
        "ix_customers_active_updated",
    ):
        op.drop_index(index_name, table_name="customers")
    op.create_index(
        "ix_customers_company_id_status", "customers", ["company_id", "status"]
    )
    op.create_index(
        "ix_customers_company_id_display_name",
        "customers",
        ["company_id", "display_name"],
    )
    op.create_index(
        "ix_customers_active_updated",
        "customers",
        ["company_id", "updated_at", "id"],
        postgresql_where=sa.text("archived_at IS NULL"),
    )

    op.add_column("customer_contacts", sa.Column("title", sa.String(150)))
    op.add_column("customer_contacts", sa.Column("office_phone", sa.String(30)))
    op.add_column(
        "customer_contacts", sa.Column("normalized_office_phone", sa.String(20))
    )
    op.add_column(
        "customer_contacts",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("customer_contacts", sa.Column("notes", sa.Text()))
    op.execute("UPDATE customer_contacts SET last_name = '' WHERE last_name IS NULL")
    op.alter_column(
        "customer_contacts", "last_name", existing_type=sa.String(100), nullable=False
    )
    op.drop_constraint(
        "customer_contacts_customer_id_fkey", "customer_contacts", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_customer_contacts_customer_id_customers",
        "customer_contacts",
        "customers",
        ["customer_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_customer_contacts_id_customer_id",
        "customer_contacts",
        ["id", "customer_id"],
    )
    op.drop_index("ix_customer_contacts_archived_at", table_name="customer_contacts")
    op.drop_index("ix_customer_contacts_customer_id", table_name="customer_contacts")
    op.execute(
        "ALTER INDEX ix_customer_contacts_normalized_phone "
        "RENAME TO ix_customer_contacts_normalized_mobile_phone"
    )
    op.drop_index(
        "uq_customer_contacts_active_preferred", table_name="customer_contacts"
    )
    op.create_index(
        "ix_customer_contacts_customer_id_active",
        "customer_contacts",
        ["customer_id", "active"],
    )
    op.create_index(
        "ix_customer_contacts_normalized_office_phone",
        "customer_contacts",
        ["normalized_office_phone"],
    )
    op.create_index(
        "uq_customer_contacts_active_preferred",
        "customer_contacts",
        ["customer_id"],
        unique=True,
        postgresql_where=sa.text("is_preferred AND active AND archived_at IS NULL"),
    )

    op.rename_table("customer_properties", "service_locations")
    op.drop_constraint(
        "customer_properties_customer_id_fkey", "service_locations", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_service_locations_customer_id_customers",
        "service_locations",
        "customers",
        ["customer_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "ck_customer_properties_property_type", "service_locations", type_="check"
    )
    op.drop_constraint(
        "ck_customer_properties_sewer_septic", "service_locations", type_="check"
    )
    op.add_column("service_locations", sa.Column("nickname", sa.String(150)))
    op.add_column(
        "service_locations",
        sa.Column("country", sa.String(2), nullable=False, server_default="US"),
    )
    op.add_column("service_locations", sa.Column("gps_latitude", sa.Numeric(9, 6)))
    op.add_column("service_locations", sa.Column("gps_longitude", sa.Numeric(10, 6)))
    op.add_column(
        "service_locations",
        sa.Column(
            "billing_address_override",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column("service_locations", sa.Column("gate_code", sa.String(200)))
    op.add_column(
        "service_locations",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column(
        "service_locations",
        "state",
        existing_type=sa.String(2),
        type_=sa.String(100),
        existing_nullable=False,
    )
    op.alter_column(
        "service_locations",
        "postal_code",
        existing_type=sa.String(10),
        type_=sa.String(20),
        existing_nullable=False,
    )
    op.alter_column(
        "service_locations",
        "property_type",
        existing_type=sa.String(30),
        nullable=True,
    )
    op.create_check_constraint(
        "ck_service_locations_country_upper",
        "service_locations",
        "country = upper(country)",
    )
    op.create_check_constraint(
        "ck_service_locations_latitude",
        "service_locations",
        "gps_latitude IS NULL OR gps_latitude BETWEEN -90 AND 90",
    )
    op.create_check_constraint(
        "ck_service_locations_longitude",
        "service_locations",
        "gps_longitude IS NULL OR gps_longitude BETWEEN -180 AND 180",
    )
    for index_name in (
        "ix_customer_properties_archived_at",
        "ix_customer_properties_customer_id",
        "ix_customer_properties_normalized_address",
        "uq_customer_properties_active_primary",
    ):
        op.drop_index(index_name, table_name="service_locations")
    op.create_index(
        "ix_service_locations_customer_id_active",
        "service_locations",
        ["customer_id", "active"],
    )
    op.create_index(
        "ix_service_locations_normalized_address",
        "service_locations",
        ["normalized_address"],
    )

    op.execute(
        """
        CREATE FUNCTION validate_customer_primary_contact() RETURNS trigger AS $$
        BEGIN
            IF NEW.primary_contact_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM customer_contacts
                WHERE id = NEW.primary_contact_id
                  AND customer_id = NEW.id
                  AND active
                  AND is_preferred
            ) THEN
                RAISE EXCEPTION 'primary contact must be an active preferred Contact for the Customer';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_customers_primary_contact
        BEFORE INSERT OR UPDATE OF primary_contact_id ON customers
        FOR EACH ROW EXECUTE FUNCTION validate_customer_primary_contact()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_customers_primary_contact ON customers")
    op.execute("DROP FUNCTION IF EXISTS validate_customer_primary_contact()")
    op.drop_index(
        "ix_service_locations_normalized_address", table_name="service_locations"
    )
    op.drop_index(
        "ix_service_locations_customer_id_active", table_name="service_locations"
    )
    op.drop_constraint(
        "ck_service_locations_longitude", "service_locations", type_="check"
    )
    op.drop_constraint(
        "ck_service_locations_latitude", "service_locations", type_="check"
    )
    op.drop_constraint(
        "ck_service_locations_country_upper", "service_locations", type_="check"
    )
    op.alter_column(
        "service_locations",
        "property_type",
        existing_type=sa.String(30),
        nullable=False,
    )
    op.alter_column(
        "service_locations",
        "postal_code",
        existing_type=sa.String(20),
        type_=sa.String(10),
    )
    op.alter_column(
        "service_locations", "state", existing_type=sa.String(100), type_=sa.String(2)
    )
    for column in (
        "active",
        "gate_code",
        "billing_address_override",
        "gps_longitude",
        "gps_latitude",
        "country",
        "nickname",
    ):
        op.drop_column("service_locations", column)
    op.drop_constraint(
        "fk_service_locations_customer_id_customers",
        "service_locations",
        type_="foreignkey",
    )
    op.rename_table("service_locations", "customer_properties")
    op.create_foreign_key(
        "customer_properties_customer_id_fkey",
        "customer_properties",
        "customers",
        ["customer_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_customer_properties_property_type",
        "customer_properties",
        "property_type IN ('single_family', 'multi_family', 'commercial', 'condo', "
        "'townhome', 'mobile_home', 'other')",
    )
    op.create_check_constraint(
        "ck_customer_properties_sewer_septic",
        "customer_properties",
        "sewer_septic IS NULL OR sewer_septic IN ('sewer', 'septic', 'unknown')",
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

    op.drop_index(
        "uq_customer_contacts_active_preferred", table_name="customer_contacts"
    )
    op.drop_index(
        "ix_customer_contacts_normalized_office_phone", table_name="customer_contacts"
    )
    op.drop_index(
        "ix_customer_contacts_customer_id_active", table_name="customer_contacts"
    )
    op.execute(
        "ALTER INDEX ix_customer_contacts_normalized_mobile_phone "
        "RENAME TO ix_customer_contacts_normalized_phone"
    )
    op.create_index(
        "ix_customer_contacts_archived_at", "customer_contacts", ["archived_at"]
    )
    op.create_index(
        "ix_customer_contacts_customer_id", "customer_contacts", ["customer_id"]
    )
    op.create_index(
        "uq_customer_contacts_active_preferred",
        "customer_contacts",
        ["customer_id"],
        unique=True,
        postgresql_where=sa.text("is_preferred AND archived_at IS NULL"),
    )
    op.drop_constraint(
        "uq_customer_contacts_id_customer_id", "customer_contacts", type_="unique"
    )
    op.drop_constraint(
        "fk_customer_contacts_customer_id_customers",
        "customer_contacts",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "customer_contacts_customer_id_fkey",
        "customer_contacts",
        "customers",
        ["customer_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.alter_column(
        "customer_contacts", "last_name", existing_type=sa.String(100), nullable=True
    )
    for column in (
        "notes",
        "active",
        "normalized_office_phone",
        "office_phone",
        "title",
    ):
        op.drop_column("customer_contacts", column)

    op.drop_index("ix_customers_active_updated", table_name="customers")
    op.drop_index("ix_customers_company_id_display_name", table_name="customers")
    op.drop_index("ix_customers_company_id_status", table_name="customers")
    op.drop_constraint(
        "uq_customers_company_id_customer_number", "customers", type_="unique"
    )
    op.drop_constraint(
        "ck_customers_display_name_not_blank", "customers", type_="check"
    )
    op.drop_constraint(
        "ck_customers_customer_number_format", "customers", type_="check"
    )
    op.drop_constraint("ck_customers_status", "customers", type_="check")
    op.drop_constraint("ck_customers_customer_type", "customers", type_="check")
    op.drop_constraint(
        "fk_customers_primary_contact_id_customer_contacts",
        "customers",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_customers_company_id_companies", "customers", type_="foreignkey"
    )
    op.alter_column(
        "customers",
        "source",
        existing_type=sa.String(100),
        type_=sa.String(50),
        nullable=False,
    )
    op.alter_column(
        "customers",
        "normalized_primary_phone",
        existing_type=sa.String(20),
        nullable=False,
    )
    op.alter_column(
        "customers", "primary_phone", existing_type=sa.String(30), nullable=False
    )
    op.alter_column(
        "customers", "company_id", existing_type=postgresql.UUID(), nullable=True
    )
    for column in (
        "tax_exempt",
        "primary_contact_id",
        "legal_name",
        "display_name",
        "customer_number",
    ):
        op.drop_column("customers", column)
    op.execute(
        "UPDATE customers SET customer_type = CASE WHEN customer_type = 'residential' "
        "THEN 'individual' ELSE 'business' END"
    )
    op.execute("UPDATE customers SET status = 'active' WHERE status = 'prospect'")
    op.alter_column(
        "customers", "customer_type", existing_type=sa.String(30), type_=sa.String(20)
    )
    op.create_check_constraint(
        "ck_customers_customer_type",
        "customers",
        "customer_type IN ('individual', 'business')",
    )
    op.create_check_constraint(
        "ck_customers_status",
        "customers",
        "status IN ('active', 'inactive', 'do_not_service')",
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
    op.drop_table("customer_number_sequences")
