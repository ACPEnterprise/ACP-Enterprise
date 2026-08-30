"""Bind Identity Onboarding requests to tenant Branch and Employee objects."""

from collections.abc import Sequence

from alembic import op

revision: str = "j8h7f26e3c9a"
down_revision: str | None = "i7g6e15d2b8f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "identity_onboarding_requests_branch_id_fkey",
        "identity_onboarding_requests",
        type_="foreignkey",
    )
    op.drop_constraint(
        "identity_onboarding_requests_employee_id_fkey",
        "identity_onboarding_requests",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_identity_onboarding_request_company_branch",
        "identity_onboarding_requests",
        "branches",
        ["company_id", "branch_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_identity_onboarding_request_company_employee",
        "identity_onboarding_requests",
        "employees",
        ["company_id", "employee_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_identity_onboarding_request_company_employee",
        "identity_onboarding_requests",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_identity_onboarding_request_company_branch",
        "identity_onboarding_requests",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "identity_onboarding_requests_employee_id_fkey",
        "identity_onboarding_requests",
        "employees",
        ["employee_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "identity_onboarding_requests_branch_id_fkey",
        "identity_onboarding_requests",
        "branches",
        ["branch_id"],
        ["id"],
        ondelete="RESTRICT",
    )
