"""Add assignment-scoped immutable field artifact custody.

Revision ID: m9n7q05f2s8t
Revises: l8m6p94e1r7s
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "m9n7q05f2s8t"
down_revision = "l8m6p94e1r7s"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "field_artifact_intents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("dispatch_assignments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("artifact_class", sa.String(40), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("expected_size", sa.Integer(), nullable=False),
        sa.Column("expected_digest", sa.String(64), nullable=False),
        sa.Column("opaque_upload_reference", sa.String(160), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id", "branch_id", "job_id"], ["jobs.company_id", "jobs.branch_id", "jobs.id"], name="fk_field_artifact_intent_job", ondelete="RESTRICT"),
        sa.CheckConstraint("artifact_class IN ('photo','field_document','equipment_evidence')", name="ck_field_artifact_intent_class"),
        sa.CheckConstraint("expected_size > 0", name="ck_field_artifact_intent_size"),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_field_artifact_intent_command"),
    )
    op.create_table(
        "field_artifact_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("dispatch_assignments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("intent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("field_artifact_intents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("artifact_class", sa.String(40), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("opaque_storage_reference", sa.String(160), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("recorded_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id", "branch_id", "job_id"], ["jobs.company_id", "jobs.branch_id", "jobs.id"], name="fk_field_artifact_evidence_job", ondelete="RESTRICT"),
        sa.UniqueConstraint("company_id", "intent_id", name="uq_field_artifact_intent"),
        sa.UniqueConstraint("company_id", "job_id", "content_digest", name="uq_field_artifact_digest"),
    )
    op.execute("""
        CREATE FUNCTION reject_field_artifact_evidence_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'field artifact evidence is immutable' USING ERRCODE = '23000';
        END $$
    """)
    op.execute("""
        CREATE TRIGGER trg_field_artifact_evidence_immutable
        BEFORE UPDATE OR DELETE ON field_artifact_evidence
        FOR EACH ROW EXECUTE FUNCTION reject_field_artifact_evidence_mutation()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_field_artifact_evidence_immutable ON field_artifact_evidence")
    op.execute("DROP FUNCTION IF EXISTS reject_field_artifact_evidence_mutation()")
    op.drop_table("field_artifact_evidence")
    op.drop_table("field_artifact_intents")
