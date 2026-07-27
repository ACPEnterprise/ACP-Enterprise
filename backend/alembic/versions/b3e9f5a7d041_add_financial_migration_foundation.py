"""Add provider-neutral financial migration foundation.

Revision ID: b3e9f5a7d041
Revises: a2d8e4f6c930
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b3e9f5a7d041"
down_revision: str | Sequence[str] | None = "a2d8e4f6c930"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _document_columns(kind: str) -> list[sa.Column]:
    timestamp_name = "presented_at" if kind == "estimate" else "issued_at"
    date_name = "expires_on" if kind == "estimate" else "due_on"
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(f"{kind}_number", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("subtotal_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column(timestamp_name, sa.DateTime(timezone=True), nullable=True),
        sa.Column(date_name, sa.Date(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _create_document_table(kind: str, statuses: str) -> None:
    plural = f"{kind}s"
    op.create_table(
        plural,
        *_document_columns(kind),
        sa.CheckConstraint(f"status IN ({statuses})", name=f"ck_{plural}_status"),
        sa.CheckConstraint(
            "subtotal_amount >= 0 AND tax_amount >= 0 AND total_amount >= 0 "
            "AND total_amount = subtotal_amount + tax_amount",
            name=f"ck_{plural}_amounts",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name=f"fk_{plural}_job_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["service_location_id"], ["service_locations.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "branch_id",
            "id",
            "customer_id",
            "service_location_id",
            name=f"uq_{plural}_migration_scope",
        ),
        sa.UniqueConstraint("company_id", f"{kind}_number", name=f"uq_{kind}_number"),
        sa.UniqueConstraint("company_id", "id", name=f"uq_{plural}_company_id"),
        *(
            [
                sa.UniqueConstraint(
                    "company_id",
                    "branch_id",
                    "id",
                    "customer_id",
                    name="uq_invoices_payment_scope",
                )
            ]
            if kind == "invoice"
            else []
        ),
    )


def _create_line_items(kind: str) -> None:
    plural = f"{kind}s"
    table = f"{kind}_line_items"
    op.create_table(
        table,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(f"{kind}_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        sa.CheckConstraint("position > 0", name=f"ck_{table}_position"),
        sa.CheckConstraint(
            "quantity > 0 AND unit_price >= 0 AND total_amount >= 0",
            name=f"ck_{table}_amounts",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", f"{kind}_id"],
            [f"{plural}.company_id", f"{plural}.id"],
            name=f"fk_{table}_{kind}_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            f"{kind}_id",
            "id",
            name=f"uq_{table}_migration_scope",
        ),
        sa.UniqueConstraint(
            "company_id",
            f"{kind}_id",
            "position",
            name=f"uq_{table}_position",
        ),
    )


def _create_document_identity(kind: str) -> None:
    plural = f"{kind}s"
    op.create_table(
        f"operational_migration_{kind}_source_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(f"{kind}_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "job_source_identity_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(length=80), nullable=False),
        sa.Column(f"source_{kind}_id", sa.String(length=191), nullable=False),
        sa.Column("source_status", sa.String(length=40), nullable=False),
        sa.Column(
            "external_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("first_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            [
                "company_id",
                "branch_id",
                f"{kind}_id",
                "customer_id",
                "service_location_id",
            ],
            [
                f"{plural}.company_id",
                f"{plural}.branch_id",
                f"{plural}.id",
                f"{plural}.customer_id",
                f"{plural}.service_location_id",
            ],
            name=f"fk_{kind}_source_identity_{kind}_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["first_run_id"],
            ["operational_migration_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "job_source_identity_id",
                "company_id",
                "branch_id",
                "job_id",
                "customer_id",
                "service_location_id",
            ],
            [
                "operational_migration_job_source_identities.id",
                "operational_migration_job_source_identities.company_id",
                "operational_migration_job_source_identities.branch_id",
                "operational_migration_job_source_identities.job_id",
                "operational_migration_job_source_identities.customer_id",
                "operational_migration_job_source_identities.service_location_id",
            ],
            name=f"fk_{kind}_source_identity_job_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            f"{kind}_id",
            name=f"uq_{kind}_source_target",
        ),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            f"source_{kind}_id",
            name=f"uq_{kind}_source_identity",
        ),
        sa.UniqueConstraint(
            "id",
            "company_id",
            *(["branch_id"] if kind == "invoice" else []),
            f"{kind}_id",
            *(["customer_id"] if kind == "invoice" else []),
            name=f"uq_{kind}_source_parent_scope",
        ),
        *(
            [
                sa.UniqueConstraint(
                    "id",
                    "company_id",
                    "invoice_id",
                    name="uq_invoice_source_line_item_scope",
                )
            ]
            if kind == "invoice"
            else []
        ),
    )


def _create_line_item_identity(kind: str) -> None:
    table = f"operational_migration_{kind}_line_item_source_identities"
    parent = f"operational_migration_{kind}_source_identities"
    target = f"{kind}_line_items"
    op.create_table(
        table,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            f"{kind}_source_identity_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(f"{kind}_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            f"{kind}_line_item_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("source_system", sa.String(length=80), nullable=False),
        sa.Column("source_line_item_id", sa.String(length=191), nullable=False),
        sa.Column("first_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", f"{kind}_id", f"{kind}_line_item_id"],
            [f"{target}.company_id", f"{target}.{kind}_id", f"{target}.id"],
            name=f"fk_{kind}_item_source_target",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [f"{kind}_source_identity_id", "company_id", f"{kind}_id"],
            [f"{parent}.id", f"{parent}.company_id", f"{parent}.{kind}_id"],
            name=f"fk_{kind}_item_source_parent",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["first_run_id"],
            ["operational_migration_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            f"{kind}_line_item_id",
            name=f"uq_{kind}_item_source_target",
        ),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "source_line_item_id",
            name=f"uq_{kind}_item_source_identity",
        ),
    )


def upgrade() -> None:
    op.drop_constraint(
        "ck_operational_migration_progress_entity",
        "operational_migration_progress",
        type_="check",
    )
    op.create_check_constraint(
        "ck_operational_migration_progress_entity",
        "operational_migration_progress",
        "entity_type IN ('job', 'appointment', 'estimate', 'invoice', 'payment')",
    )
    op.drop_constraint(
        "ck_operational_migration_exceptions_entity",
        "operational_migration_exceptions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_operational_migration_exceptions_entity",
        "operational_migration_exceptions",
        "entity_type IN ('job', 'appointment', 'estimate', 'invoice', 'payment')",
    )
    _create_document_table(
        "estimate", "'draft', 'presented', 'approved', 'declined', 'expired'"
    )
    _create_document_table(
        "invoice", "'draft', 'issued', 'partially_paid', 'paid', 'void'"
    )
    _create_line_items("estimate")
    _create_line_items("invoice")
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("method", sa.String(length=40), nullable=True),
        sa.Column("reference", sa.String(length=191), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_payments_amount"),
        sa.CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed', 'refunded')",
            name="ck_payments_status",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "invoice_id", "customer_id"],
            [
                "invoices.company_id",
                "invoices.branch_id",
                "invoices.id",
                "invoices.customer_id",
            ],
            name="fk_payments_invoice_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "branch_id",
            "id",
            "invoice_id",
            "customer_id",
            name="uq_payments_migration_scope",
        ),
    )
    _create_document_identity("estimate")
    _create_document_identity("invoice")
    _create_line_item_identity("estimate")
    _create_line_item_identity("invoice")
    op.create_table(
        "operational_migration_payment_source_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "invoice_source_identity_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(length=80), nullable=False),
        sa.Column("source_payment_id", sa.String(length=191), nullable=False),
        sa.Column("source_status", sa.String(length=40), nullable=False),
        sa.Column(
            "external_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("first_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "payment_id", "invoice_id", "customer_id"],
            [
                "payments.company_id",
                "payments.branch_id",
                "payments.id",
                "payments.invoice_id",
                "payments.customer_id",
            ],
            name="fk_payment_source_identity_payment_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["first_run_id"],
            ["operational_migration_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "invoice_source_identity_id",
                "company_id",
                "branch_id",
                "invoice_id",
                "customer_id",
            ],
            [
                "operational_migration_invoice_source_identities.id",
                "operational_migration_invoice_source_identities.company_id",
                "operational_migration_invoice_source_identities.branch_id",
                "operational_migration_invoice_source_identities.invoice_id",
                "operational_migration_invoice_source_identities.customer_id",
            ],
            name="fk_payment_source_identity_invoice_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "payment_id",
            name="uq_payment_source_target",
        ),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "source_payment_id",
            name="uq_payment_source_identity",
        ),
    )


def downgrade() -> None:
    op.drop_table("operational_migration_payment_source_identities")
    op.drop_table("operational_migration_invoice_line_item_source_identities")
    op.drop_table("operational_migration_estimate_line_item_source_identities")
    op.drop_table("operational_migration_invoice_source_identities")
    op.drop_table("operational_migration_estimate_source_identities")
    op.drop_table("payments")
    op.drop_table("invoice_line_items")
    op.drop_table("estimate_line_items")
    op.drop_table("invoices")
    op.drop_table("estimates")
    op.drop_constraint(
        "ck_operational_migration_exceptions_entity",
        "operational_migration_exceptions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_operational_migration_exceptions_entity",
        "operational_migration_exceptions",
        "entity_type IN ('job', 'appointment')",
    )
    op.drop_constraint(
        "ck_operational_migration_progress_entity",
        "operational_migration_progress",
        type_="check",
    )
    op.create_check_constraint(
        "ck_operational_migration_progress_entity",
        "operational_migration_progress",
        "entity_type IN ('job', 'appointment')",
    )
