"""add customer search and timeline indexes

Revision ID: d9f4b6c8e173
Revises: c8e3a5b7d062
Create Date: 2026-07-18
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "d9f4b6c8e173"
down_revision: str | None = "c8e3a5b7d062"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    trigram_indexes = (
        ("ix_customers_customer_number_trgm", "customers", "customer_number"),
        ("ix_customers_display_name_trgm", "customers", "display_name"),
        ("ix_customers_legal_name_trgm", "customers", "legal_name"),
        ("ix_customer_contacts_first_name_trgm", "customer_contacts", "first_name"),
        ("ix_customer_contacts_last_name_trgm", "customer_contacts", "last_name"),
        (
            "ix_customer_contacts_normalized_email_trgm",
            "customer_contacts",
            "normalized_email",
        ),
        (
            "ix_customer_contacts_normalized_phone_trgm",
            "customer_contacts",
            "normalized_phone",
        ),
        (
            "ix_customer_contacts_normalized_office_phone_trgm",
            "customer_contacts",
            "normalized_office_phone",
        ),
        (
            "ix_service_locations_address_line_1_trgm",
            "service_locations",
            "address_line_1",
        ),
        ("ix_service_locations_city_trgm", "service_locations", "city"),
        (
            "ix_service_locations_postal_code_trgm",
            "service_locations",
            "postal_code",
        ),
    )
    for index_name, table_name, column_name in trigram_indexes:
        op.create_index(
            index_name,
            table_name,
            [column_name],
            postgresql_using="gin",
            postgresql_ops={column_name: "gin_trgm_ops"},
        )

    op.create_index(
        "ix_business_events_customer_timeline_entity",
        "business_events",
        ["company_id", "entity_type", "entity_id", "occurred_at", "id"],
    )
    op.create_index(
        "ix_business_events_customer_timeline_payload",
        "business_events",
        [
            "company_id",
            sa.text("(payload ->> 'customer_id')"),
            "occurred_at",
            "id",
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_business_events_customer_timeline_payload", table_name="business_events"
    )
    op.drop_index(
        "ix_business_events_customer_timeline_entity", table_name="business_events"
    )
    for index_name, table_name in (
        ("ix_service_locations_postal_code_trgm", "service_locations"),
        ("ix_service_locations_city_trgm", "service_locations"),
        ("ix_service_locations_address_line_1_trgm", "service_locations"),
        (
            "ix_customer_contacts_normalized_office_phone_trgm",
            "customer_contacts",
        ),
        ("ix_customer_contacts_normalized_phone_trgm", "customer_contacts"),
        ("ix_customer_contacts_normalized_email_trgm", "customer_contacts"),
        ("ix_customer_contacts_last_name_trgm", "customer_contacts"),
        ("ix_customer_contacts_first_name_trgm", "customer_contacts"),
        ("ix_customers_legal_name_trgm", "customers"),
        ("ix_customers_display_name_trgm", "customers"),
        ("ix_customers_customer_number_trgm", "customers"),
    ):
        op.drop_index(index_name, table_name=table_name)
