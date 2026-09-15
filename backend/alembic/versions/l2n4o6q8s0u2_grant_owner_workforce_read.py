"""Grant explicit Workforce read authority to existing owner roles.

Revision ID: l2n4o6q8s0u2
Revises: k1m3o5q7s9u1
"""

from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa

from alembic import op

revision: str = "l2n4o6q8s0u2"
down_revision: str | Sequence[str] | None = "k1m3o5q7s9u1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
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
            JOIN permissions p ON p.code = 'COMPANY_WORKFORCE_READ'
            WHERE r.code IN ('OWNER', 'ADMIN', 'COMPANY_ADMINISTRATOR')
              AND r.archived_at IS NULL
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ).bindparams(at=datetime.now(timezone.utc))
    )
    op.execute(
        sa.text(
            """
            UPDATE users u
            SET authorization_version = u.authorization_version + 1,
                updated_at = :at
            WHERE u.id IN (
                SELECT DISTINCT m.user_id
                FROM memberships m
                JOIN membership_roles mr ON mr.membership_id = m.id
                JOIN roles r ON r.id = mr.role_id
                WHERE r.code IN ('OWNER', 'ADMIN', 'COMPANY_ADMINISTRATOR')
                  AND r.archived_at IS NULL
                  AND m.status = 'active'
            )
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
              AND rp.id = (
                substr(md5(r.id::text || p.id::text), 1, 8) || '-' ||
                substr(md5(r.id::text || p.id::text), 9, 4) || '-' ||
                substr(md5(r.id::text || p.id::text), 13, 4) || '-' ||
                substr(md5(r.id::text || p.id::text), 17, 4) || '-' ||
                substr(md5(r.id::text || p.id::text), 21, 12)
              )::uuid
              AND r.code IN ('OWNER', 'ADMIN', 'COMPANY_ADMINISTRATOR')
              AND p.code = 'COMPANY_WORKFORCE_READ'
            """
        )
    )
