"""Bind provider receipt, attempt, and session evidence to exact parent lineage.

Revision ID: k1j9i27d4b0z
Revises: j0i8h16c3a9y
"""

from collections.abc import Sequence

from alembic import op

revision: str = "k1j9i27d4b0z"
down_revision: str | Sequence[str] | None = "j0i8h16c3a9y"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_execution_compositions_attempt_authority",
        "engineering_execution_compositions",
        ["company_id", "id", "worker_id", "lease_id", "provider_identifier"],
    )
    op.create_unique_constraint(
        "uq_execution_compositions_receipt_authority",
        "engineering_execution_compositions",
        [
            "company_id", "id", "execution_id", "worker_id", "lease_id",
            "provider_identifier", "instruction_digest", "request_digest",
            "composition_digest", "expires_at",
        ],
    )
    op.drop_constraint(
        "fk_composition_receipts_composition",
        "engineering_composition_receipts",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_composition_receipts_exact_composition",
        "engineering_composition_receipts",
        "engineering_execution_compositions",
        [
            "company_id", "composition_id", "execution_id", "worker_id",
            "lease_id", "provider_identifier", "instruction_digest",
            "request_digest", "composition_digest", "expires_at",
        ],
        [
            "company_id", "id", "execution_id", "worker_id", "lease_id",
            "provider_identifier", "instruction_digest", "request_digest",
            "composition_digest", "expires_at",
        ],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "fk_provider_attempts_composition",
        "engineering_provider_execution_attempts",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_provider_attempts_exact_composition",
        "engineering_provider_execution_attempts",
        "engineering_execution_compositions",
        ["company_id", "composition_id", "worker_id", "lease_id", "provider_identifier"],
        ["company_id", "id", "worker_id", "lease_id", "provider_identifier"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_provider_attempts_session_authority",
        "engineering_provider_execution_attempts",
        [
            "company_id", "id", "composition_id", "worker_id", "lease_id",
            "provider_identifier",
        ],
    )
    op.create_unique_constraint(
        "uq_live_client_supervisors_session_authority",
        "engineering_live_client_supervisors",
        ["company_id", "id", "worker_id"],
    )
    for name in (
        "engineering_provider_sessions_company_id_supervisor_id_fkey",
        "engineering_provider_sessions_company_id_composition_id_fkey",
        "engineering_provider_sessions_company_id_attempt_id_fkey",
    ):
        op.drop_constraint(name, "engineering_provider_sessions", type_="foreignkey")
    op.create_foreign_key(
        "fk_provider_sessions_exact_supervisor",
        "engineering_provider_sessions",
        "engineering_live_client_supervisors",
        ["company_id", "supervisor_id", "worker_id"],
        ["company_id", "id", "worker_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_provider_sessions_exact_attempt",
        "engineering_provider_sessions",
        "engineering_provider_execution_attempts",
        [
            "company_id", "attempt_id", "composition_id", "worker_id",
            "lease_id", "provider_identifier",
        ],
        [
            "company_id", "id", "composition_id", "worker_id", "lease_id",
            "provider_identifier",
        ],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_provider_sessions_exact_attempt", "engineering_provider_sessions", type_="foreignkey")
    op.drop_constraint("fk_provider_sessions_exact_supervisor", "engineering_provider_sessions", type_="foreignkey")
    for name, columns, remote_table in (
        ("engineering_provider_sessions_company_id_attempt_id_fkey", ["company_id", "attempt_id"], "engineering_provider_execution_attempts"),
        ("engineering_provider_sessions_company_id_composition_id_fkey", ["company_id", "composition_id"], "engineering_execution_compositions"),
        ("engineering_provider_sessions_company_id_supervisor_id_fkey", ["company_id", "supervisor_id"], "engineering_live_client_supervisors"),
    ):
        op.create_foreign_key(name, "engineering_provider_sessions", remote_table, columns, ["company_id", "id"], ondelete="RESTRICT")
    op.drop_constraint("uq_live_client_supervisors_session_authority", "engineering_live_client_supervisors", type_="unique")
    op.drop_constraint("uq_provider_attempts_session_authority", "engineering_provider_execution_attempts", type_="unique")
    op.drop_constraint("fk_provider_attempts_exact_composition", "engineering_provider_execution_attempts", type_="foreignkey")
    op.create_foreign_key("fk_provider_attempts_composition", "engineering_provider_execution_attempts", "engineering_execution_compositions", ["company_id", "composition_id"], ["company_id", "id"], ondelete="RESTRICT")
    op.drop_constraint("fk_composition_receipts_exact_composition", "engineering_composition_receipts", type_="foreignkey")
    op.create_foreign_key("fk_composition_receipts_composition", "engineering_composition_receipts", "engineering_execution_compositions", ["company_id", "composition_id"], ["company_id", "id"], ondelete="RESTRICT")
    op.drop_constraint("uq_execution_compositions_receipt_authority", "engineering_execution_compositions", type_="unique")
    op.drop_constraint("uq_execution_compositions_attempt_authority", "engineering_execution_compositions", type_="unique")
