"""Protect Business Event and audit tenant scope.

Revision ID: m1k0i59h6f2d
Revises: h6f8j0l2n497
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "m1k0i59h6f2d"
down_revision: str | Sequence[str] | None = "h6f8j0l2n497"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _scope_check(table: str, name: str) -> None:
    op.create_check_constraint(name, table, "branch_id IS NULL OR company_id IS NOT NULL")


def upgrade() -> None:
    _scope_check("business_events", "ck_business_events_branch_requires_company")
    op.create_unique_constraint(
        "uq_business_events_company_id", "business_events", ["company_id", "id"]
    )
    op.create_unique_constraint(
        "uq_business_events_id_branch", "business_events", ["id", "branch_id"]
    )
    op.create_foreign_key(
        "fk_business_events_company_branch",
        "business_events",
        "branches",
        ["company_id", "branch_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
        postgresql_not_valid=True,
    )
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "IF NOT EXISTS (SELECT 1 FROM business_events e "
            "LEFT JOIN branches b ON b.company_id = e.company_id "
            "AND b.id = e.branch_id "
            "WHERE e.branch_id IS NOT NULL AND b.id IS NULL) THEN "
            "ALTER TABLE business_events VALIDATE CONSTRAINT "
            "fk_business_events_company_branch; "
            "END IF; END $$"
        )
    )

    _scope_check("audit_records", "ck_audit_records_branch_requires_company")
    op.create_foreign_key(
        "fk_audit_records_company_branch",
        "audit_records",
        "branches",
        ["company_id", "branch_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )

    _scope_check(
        "business_event_deliveries",
        "ck_business_event_delivery_branch_requires_company",
    )
    op.create_unique_constraint(
        "uq_business_event_delivery_company_id",
        "business_event_deliveries",
        ["company_id", "id"],
    )
    op.create_unique_constraint(
        "uq_business_event_delivery_id_event",
        "business_event_deliveries",
        ["id", "event_id"],
    )
    op.create_unique_constraint(
        "uq_business_event_delivery_id_branch",
        "business_event_deliveries",
        ["id", "branch_id"],
    )
    op.create_unique_constraint(
        "uq_business_event_delivery_id_consumer",
        "business_event_deliveries",
        ["id", "consumer_name"],
    )
    op.create_foreign_key(
        "fk_business_event_delivery_company_event",
        "business_event_deliveries",
        "business_events",
        ["company_id", "event_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_business_event_delivery_event_branch",
        "business_event_deliveries",
        "business_events",
        ["event_id", "branch_id"],
        ["id", "branch_id"],
        ondelete="RESTRICT",
    )

    _scope_check(
        "business_event_delivery_evidence",
        "ck_business_event_evidence_branch_requires_company",
    )
    for name, local, remote in (
        ("fk_business_event_evidence_company_delivery", ["company_id", "delivery_id"], ["company_id", "id"]),
        ("fk_business_event_evidence_delivery_event", ["delivery_id", "event_id"], ["id", "event_id"]),
        ("fk_business_event_evidence_delivery_branch", ["delivery_id", "branch_id"], ["id", "branch_id"]),
        ("fk_business_event_evidence_delivery_consumer", ["delivery_id", "consumer_name"], ["id", "consumer_name"]),
    ):
        op.create_foreign_key(
            name,
            "business_event_delivery_evidence",
            "business_event_deliveries",
            local,
            remote,
            ondelete="RESTRICT",
        )

    _scope_check(
        "business_event_consumer_receipts",
        "ck_business_event_receipt_branch_requires_company",
    )
    op.create_foreign_key(
        "fk_business_event_receipt_company_event",
        "business_event_consumer_receipts",
        "business_events",
        ["company_id", "event_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_business_event_receipt_event_branch",
        "business_event_consumer_receipts",
        "business_events",
        ["event_id", "branch_id"],
        ["id", "branch_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_business_event_cursor_company_event",
        "business_event_consumer_cursors",
        "business_events",
        ["company_id", "last_event_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    for table, name in (
        ("business_event_consumer_cursors", "fk_business_event_cursor_company_event"),
        ("business_event_consumer_receipts", "fk_business_event_receipt_event_branch"),
        ("business_event_consumer_receipts", "fk_business_event_receipt_company_event"),
    ):
        op.drop_constraint(name, table, type_="foreignkey")
    op.drop_constraint(
        "ck_business_event_receipt_branch_requires_company",
        "business_event_consumer_receipts",
        type_="check",
    )
    for name in (
        "fk_business_event_evidence_delivery_consumer",
        "fk_business_event_evidence_delivery_branch",
        "fk_business_event_evidence_delivery_event",
        "fk_business_event_evidence_company_delivery",
    ):
        op.drop_constraint(name, "business_event_delivery_evidence", type_="foreignkey")
    op.drop_constraint(
        "ck_business_event_evidence_branch_requires_company",
        "business_event_delivery_evidence",
        type_="check",
    )
    for name in (
        "fk_business_event_delivery_event_branch",
        "fk_business_event_delivery_company_event",
    ):
        op.drop_constraint(name, "business_event_deliveries", type_="foreignkey")
    for name in (
        "uq_business_event_delivery_id_consumer",
        "uq_business_event_delivery_id_branch",
        "uq_business_event_delivery_id_event",
        "uq_business_event_delivery_company_id",
    ):
        op.drop_constraint(name, "business_event_deliveries", type_="unique")
    op.drop_constraint(
        "ck_business_event_delivery_branch_requires_company",
        "business_event_deliveries",
        type_="check",
    )
    op.drop_constraint("fk_audit_records_company_branch", "audit_records", type_="foreignkey")
    op.drop_constraint("ck_audit_records_branch_requires_company", "audit_records", type_="check")
    op.drop_constraint("fk_business_events_company_branch", "business_events", type_="foreignkey")
    op.drop_constraint("uq_business_events_id_branch", "business_events", type_="unique")
    op.drop_constraint("uq_business_events_company_id", "business_events", type_="unique")
    op.drop_constraint("ck_business_events_branch_requires_company", "business_events", type_="check")
