"""align purchase order disposition constraint name

Revision ID: t1k3g5i7l942
Revises: s0j2f4h6k831
"""

from collections.abc import Sequence

from alembic import op

revision: str = "t1k3g5i7l942"
down_revision: str | Sequence[str] | None = "s0j2f4h6k831"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE purchasing_po_disposition_evidence "
        "RENAME CONSTRAINT purchasing_po_disposition_evidence_disposition_check "
        "TO ck_purchasing_disposition_kind"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE purchasing_po_disposition_evidence "
        "RENAME CONSTRAINT ck_purchasing_disposition_kind "
        "TO purchasing_po_disposition_evidence_disposition_check"
    )
