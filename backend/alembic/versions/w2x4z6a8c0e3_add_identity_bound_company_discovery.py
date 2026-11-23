"""Allow authenticated users to discover their own active companies under RLS."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "w2x4z6a8c0e3"
down_revision: str | Sequence[str] | None = "u1v3x5z7b9d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION acp_rls_user_id()
            RETURNS uuid
            LANGUAGE sql
            STABLE
            AS $$
              SELECT CASE
                WHEN current_setting('app.user_id', true) ~
                  '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
                THEN current_setting('app.user_id', true)::uuid
                ELSE NULL
              END
            $$
            """
        )
    )
    # SELECT-only discovery policies. Tenant-scoped writes remain governed by
    # the existing company/branch policy and authorization dependencies.
    connection.execute(
        sa.text(
            """
            DROP POLICY IF EXISTS acp_membership_discovery ON memberships;
            CREATE POLICY acp_membership_discovery ON memberships
              FOR SELECT
              USING (
                user_id = acp_rls_user_id()
                AND status = 'active'
              );
            DROP POLICY IF EXISTS acp_branch_discovery ON branches;
            CREATE POLICY acp_branch_discovery ON branches
              FOR SELECT
              USING (
                EXISTS (
                  SELECT 1
                    FROM memberships discovery_membership
                   WHERE discovery_membership.company_id = branches.company_id
                     AND discovery_membership.user_id = acp_rls_user_id()
                     AND discovery_membership.status = 'active'
                )
              );
            """
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("DROP POLICY IF EXISTS acp_branch_discovery ON branches"))
    connection.execute(
        sa.text("DROP POLICY IF EXISTS acp_membership_discovery ON memberships")
    )
    connection.execute(sa.text("DROP FUNCTION IF EXISTS acp_rls_user_id()"))
