"""Bind Business Event and audit root authority identities.

Revision ID: g7f5e83z0x6v
Revises: f6e4d72y9w5u
"""

from collections.abc import Sequence

from alembic import op

revision: str = "g7f5e83z0x6v"
down_revision: str | Sequence[str] | None = "f6e4d72y9w5u"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name, table, column, parent in (
        ("fk_business_events_company", "business_events", "company_id", "companies"),
        ("fk_business_events_user", "business_events", "user_id", "users"),
        (
            "fk_business_event_evidence_actor",
            "business_event_delivery_evidence",
            "actor_user_id",
            "users",
        ),
        ("fk_audit_records_company", "audit_records", "company_id", "companies"),
        ("fk_audit_records_actor", "audit_records", "actor_user_id", "users"),
    ):
        op.create_foreign_key(
            name,
            table,
            parent,
            [column],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    for name, table in (
        ("fk_audit_records_actor", "audit_records"),
        ("fk_audit_records_company", "audit_records"),
        ("fk_business_event_evidence_actor", "business_event_delivery_evidence"),
        ("fk_business_events_user", "business_events"),
        ("fk_business_events_company", "business_events"),
    ):
        op.drop_constraint(name, table, type_="foreignkey")
