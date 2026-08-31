"""Bind Field Service evidence to exact assignment and invoice scope.

Revision ID: t8r7s26o3m9k
Revises: s7q6r15n2l8j
"""

from collections.abc import Sequence

from alembic import op

revision: str = "t8r7s26o3m9k"
down_revision: str | Sequence[str] | None = "s7q6r15n2l8j"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ASSIGNMENT_TABLES = (
    ("field_work_notes", "field_work_notes_assignment_id_fkey", "fk_field_notes_assignment_scope"),
    (
        "field_customer_approvals",
        "field_customer_approvals_assignment_id_fkey",
        "fk_field_approvals_assignment_scope",
    ),
    (
        "field_invoice_handoffs",
        "field_invoice_handoffs_assignment_id_fkey",
        "fk_field_handoffs_assignment_scope",
    ),
    (
        "field_completion_requirement_snapshots",
        "field_completion_requirement_snapshots_assignment_id_fkey",
        "fk_field_requirement_snapshots_assignment_scope",
    ),
    (
        "field_non_billable_dispositions",
        "field_non_billable_dispositions_assignment_id_fkey",
        "fk_field_non_billable_assignment_scope",
    ),
)


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_dispatch_assignments_field_scope",
        "dispatch_assignments",
        ["company_id", "branch_id", "job_id", "id"],
    )
    op.create_unique_constraint(
        "uq_invoices_field_scope",
        "invoices",
        ["company_id", "branch_id", "job_id", "id"],
    )
    op.create_unique_constraint(
        "uq_field_requirement_snapshots_evidence_scope",
        "field_completion_requirement_snapshots",
        ["company_id", "branch_id", "job_id", "id"],
    )

    for table, old_name, new_name in ASSIGNMENT_TABLES:
        op.drop_constraint(old_name, table, type_="foreignkey")
        op.create_foreign_key(
            new_name,
            table,
            "dispatch_assignments",
            ["company_id", "branch_id", "job_id", "assignment_id"],
            ["company_id", "branch_id", "job_id", "id"],
            ondelete="RESTRICT",
        )

    op.drop_constraint(
        "field_invoice_handoffs_invoice_id_fkey",
        "field_invoice_handoffs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_field_handoffs_invoice_scope",
        "field_invoice_handoffs",
        "invoices",
        ["company_id", "branch_id", "job_id", "invoice_id"],
        ["company_id", "branch_id", "job_id", "id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "field_completion_evidence_snapshot_id_fkey",
        "field_completion_evidence",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_field_completion_evidence_snapshot_scope",
        "field_completion_evidence",
        "field_completion_requirement_snapshots",
        ["company_id", "branch_id", "job_id", "snapshot_id"],
        ["company_id", "branch_id", "job_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_field_completion_evidence_snapshot_scope",
        "field_completion_evidence",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "field_completion_evidence_snapshot_id_fkey",
        "field_completion_evidence",
        "field_completion_requirement_snapshots",
        ["snapshot_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "fk_field_handoffs_invoice_scope",
        "field_invoice_handoffs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "field_invoice_handoffs_invoice_id_fkey",
        "field_invoice_handoffs",
        "invoices",
        ["invoice_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    for table, old_name, new_name in reversed(ASSIGNMENT_TABLES):
        op.drop_constraint(new_name, table, type_="foreignkey")
        op.create_foreign_key(
            old_name,
            table,
            "dispatch_assignments",
            ["assignment_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    op.drop_constraint(
        "uq_field_requirement_snapshots_evidence_scope",
        "field_completion_requirement_snapshots",
        type_="unique",
    )
    op.drop_constraint("uq_invoices_field_scope", "invoices", type_="unique")
    op.drop_constraint(
        "uq_dispatch_assignments_field_scope",
        "dispatch_assignments",
        type_="unique",
    )
