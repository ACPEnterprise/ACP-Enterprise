"""Grant Luminary read to existing Company Administrator roles.

Revision ID: k1m3o5q7s9u1
Revises: j0l2n4p6r8t0
"""

from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision: str = "k1m3o5q7s9u1"
down_revision: str | Sequence[str] | None = "j0l2n4p6r8t0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            WITH inserted AS (
                INSERT INTO role_permissions
                    (id, role_id, permission_id, assigned_at, assigned_by_user_id)
                SELECT (
                    substr(md5(r.id::text || p.id::text), 1, 8) || '-' ||
                    substr(md5(r.id::text || p.id::text), 9, 4) || '-' ||
                    substr(md5(r.id::text || p.id::text), 13, 4) || '-' ||
                    substr(md5(r.id::text || p.id::text), 17, 4) || '-' ||
                    substr(md5(r.id::text || p.id::text), 21, 12)
                )::uuid, r.id, p.id, :at, NULL
                FROM roles r
                JOIN permissions p ON p.code = 'COMPANY_LUMINARY_READ'
                WHERE r.code = 'COMPANY_ADMINISTRATOR'
                  AND r.archived_at IS NULL
                  AND p.status = 'active'
                  AND p.retired_at IS NULL
                ON CONFLICT (role_id, permission_id) DO NOTHING
                RETURNING role_id
            ), affected_users AS (
                SELECT DISTINCT m.user_id
                FROM inserted i
                JOIN membership_roles mr
                  ON mr.role_id = i.role_id AND mr.revoked_at IS NULL
                JOIN memberships m
                  ON m.id = mr.membership_id
                 AND m.company_id = mr.company_id
                 AND m.status = 'active'
            )
            UPDATE users u
            SET authorization_version = u.authorization_version + 1,
                updated_at = :at
            FROM affected_users a
            WHERE u.id = a.user_id
            """
        ).bindparams(at=datetime.now(timezone.utc))
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM role_permissions rp
            USING roles r, permissions p
            WHERE rp.role_id = r.id
              AND rp.permission_id = p.id
              AND r.code = 'COMPANY_ADMINISTRATOR'
              AND p.code = 'COMPANY_LUMINARY_READ'
            """
        )
    )
