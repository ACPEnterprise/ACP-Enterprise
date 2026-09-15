"""Seed cutover review grants for existing Company Administrator roles.

Revision ID: j0l2n4p6r8t0
Revises: i9k1m3o5q7s9
"""

from datetime import datetime, timezone
from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "j0l2n4p6r8t0"
down_revision: str | Sequence[str] | None = "i9k1m3o5q7s9"
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
            JOIN permissions p ON p.code IN (
                'COMPANY_PAYROLL_CUTOVER_READ',
                'COMPANY_PAYROLL_CUTOVER_OWNER_CERTIFY',
                'COMPANY_PAYROLL_CUTOVER_APPROVE'
            )
            WHERE r.code = 'COMPANY_ADMINISTRATOR' AND r.archived_at IS NULL
            ON CONFLICT (role_id, permission_id) DO NOTHING
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
              AND p.code IN (
                  'COMPANY_PAYROLL_CUTOVER_READ',
                  'COMPANY_PAYROLL_CUTOVER_OWNER_CERTIFY',
                  'COMPANY_PAYROLL_CUTOVER_APPROVE'
              )
            """
        )
    )
