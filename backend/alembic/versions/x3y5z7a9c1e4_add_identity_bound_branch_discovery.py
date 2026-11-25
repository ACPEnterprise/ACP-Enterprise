"""Allow authenticated users to discover explicitly granted branches under RLS."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "x3y5z7a9c1e4"
down_revision: str | Sequence[str] | None = "w2x4z6a8c0e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            DROP POLICY IF EXISTS acp_membership_branch_discovery
              ON membership_branch_access;
            CREATE POLICY acp_membership_branch_discovery
              ON membership_branch_access
              FOR SELECT
              USING (
                EXISTS (
                  SELECT 1
                    FROM memberships discovery_membership
                   WHERE discovery_membership.id = membership_branch_access.membership_id
                     AND discovery_membership.user_id = acp_rls_user_id()
                     AND discovery_membership.status = 'active'
                )
              );
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DROP POLICY IF EXISTS acp_membership_branch_discovery "
            "ON membership_branch_access"
        )
    )
