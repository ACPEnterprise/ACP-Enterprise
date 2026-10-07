"""Grant Field Manager read-only equipment attention authority.

Revision ID: yp8r0t2v4x6z
Revises: yo7q9m1o3r5t
"""

from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision: str = "yp8r0t2v4x6z"
down_revision: str | Sequence[str] | None = "yo7q9m1o3r5t"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION_CODE = "COMPANY_ASSET_READ"


def upgrade() -> None:
    now = datetime.now(timezone.utc)
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
            )::uuid, r.id, p.id, :at, r.updated_by_user_id
            FROM roles r
            JOIN permissions p
              ON p.code = :permission_code
             AND p.status = 'active'
            WHERE r.code = 'FIELD_MANAGER'
              AND r.is_system IS TRUE
              AND r.archived_at IS NULL
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ).bindparams(at=now, permission_code=PERMISSION_CODE)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM role_permissions rp
            USING roles r, permissions p
            WHERE rp.role_id = r.id
              AND rp.permission_id = p.id
              AND r.code = 'FIELD_MANAGER'
              AND p.code = :permission_code
              AND rp.id = (
                  substr(md5(r.id::text || p.id::text), 1, 8) || '-' ||
                  substr(md5(r.id::text || p.id::text), 9, 4) || '-' ||
                  substr(md5(r.id::text || p.id::text), 13, 4) || '-' ||
                  substr(md5(r.id::text || p.id::text), 17, 4) || '-' ||
                  substr(md5(r.id::text || p.id::text), 21, 12)
              )::uuid
            """
        ).bindparams(permission_code=PERMISSION_CODE)
    )
