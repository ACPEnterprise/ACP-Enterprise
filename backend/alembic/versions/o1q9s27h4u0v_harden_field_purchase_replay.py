"""Harden field-purchase duplicate and extraction-revision authority."""

from collections.abc import Sequence

from alembic import op

revision: str = "o1q9s27h4u0v"
down_revision: str | Sequence[str] | None = "q3s1t29j6w2x"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_field_purchase_receipt_digest",
        "field_purchases",
        ["company_id", "receipt_digest"],
    )
    op.drop_constraint(
        "uq_field_purchase_line_number", "field_purchase_lines", type_="unique"
    )
    op.create_unique_constraint(
        "uq_field_purchase_line_number",
        "field_purchase_lines",
        ["company_id", "extraction_id", "line_number"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_field_purchase_line_number", "field_purchase_lines", type_="unique"
    )
    op.create_unique_constraint(
        "uq_field_purchase_line_number",
        "field_purchase_lines",
        ["company_id", "field_purchase_id", "line_number"],
    )
    op.drop_constraint(
        "uq_field_purchase_receipt_digest", "field_purchases", type_="unique"
    )
