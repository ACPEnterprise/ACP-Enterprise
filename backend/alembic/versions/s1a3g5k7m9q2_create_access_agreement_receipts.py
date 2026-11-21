"""Create immutable electronic access agreements and acceptance receipts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "s1a3g5k7m9q2"
down_revision: str | Sequence[str] | None = "r4s6u8w0y2a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "access_agreement_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("mandatory", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code", "version", name="uq_access_agreement_document_version"),
        sa.CheckConstraint("status IN ('draft','published','retired')", name="ck_access_agreement_document_status"),
        sa.CheckConstraint("length(btrim(content)) > 0", name="ck_access_agreement_document_content"),
    )
    op.create_index("ix_access_agreement_documents_current", "access_agreement_documents", ["code", "status", "version"])
    op.create_table(
        "access_agreement_acceptances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("agreement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("access_agreement_documents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("agreement_version", sa.Integer(), nullable=False),
        sa.Column("agreement_sha256", sa.String(64), nullable=False),
        sa.Column("recipient_name", sa.String(200), nullable=False),
        sa.Column("recipient_email", sa.String(320), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("electronic_signature_consent", sa.Boolean(), nullable=False),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("user_agent", sa.Text()),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.UniqueConstraint("user_id", "company_id", "agreement_id", name="uq_access_agreement_acceptance_identity"),
    )
    op.create_index("ix_access_agreement_acceptances_user_company", "access_agreement_acceptances", ["user_id", "company_id", "accepted_at"])


def downgrade() -> None:
    op.drop_index("ix_access_agreement_acceptances_user_company", table_name="access_agreement_acceptances")
    op.drop_table("access_agreement_acceptances")
    op.drop_index("ix_access_agreement_documents_current", table_name="access_agreement_documents")
    op.drop_table("access_agreement_documents")
