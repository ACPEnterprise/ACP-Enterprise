"""Add the canonical bounded FIELD_MANAGER access profile.

Revision ID: uk1m3o5q7s9u
Revises: uj0l2n4p6r8t
"""

from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa

from alembic import op

revision: str = "uk1m3o5q7s9u"
down_revision: str | Sequence[str] | None = "uj0l2n4p6r8t"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROFILE_PERMISSIONS = (
    "COMPANY_CUSTOMER_READ",
    "COMPANY_PIPELINE_READ",
    "COMPANY_PIPELINE_LEAD_UPDATE",
    "COMPANY_PIPELINE_LEAD_ASSIGN",
    "COMPANY_SCHEDULING_READ",
    "COMPANY_SCHEDULING_MANAGE",
    "COMPANY_JOB_READ",
    "COMPANY_JOB_MANAGE",
    "COMPANY_JOB_EXECUTE",
    "COMPANY_DISPATCH_READ",
    "COMPANY_DISPATCH_MANAGE",
    "COMPANY_WORKFORCE_READ",
    "COMPANY_TIMEKEEPING_OWN_READ",
    "COMPANY_TIMEKEEPING_OWN_PUNCH",
    "COMPANY_EMPLOYEE_OPERATIONS_OWN_DAY_READ",
    "COMPANY_EMPLOYEE_OPERATIONS_OWN_LIA_READ",
    "COMPANY_PRICE_BOOK_READ",
    "COMPANY_INVENTORY_READ",
    "COMPANY_INVENTORY_RESERVE",
)


def _profile_permissions() -> None:
    now = datetime.now(timezone.utc)
    op.execute(
        sa.text(
            """
            INSERT INTO roles
                (id, company_id, code, name, description, status, is_system,
                 created_at, updated_at)
            SELECT (
                substr(md5(c.id::text || 'FIELD_MANAGER'), 1, 8) || '-' ||
                substr(md5(c.id::text || 'FIELD_MANAGER'), 9, 4) || '-' ||
                substr(md5(c.id::text || 'FIELD_MANAGER'), 13, 4) || '-' ||
                substr(md5(c.id::text || 'FIELD_MANAGER'), 17, 4) || '-' ||
                substr(md5(c.id::text || 'FIELD_MANAGER'), 21, 12)
            )::uuid, c.id, 'FIELD_MANAGER', 'Field Manager',
            'Bounded field execution and Service Board supervision.', 'active', true,
            :at, :at
            FROM companies c
            WHERE NOT EXISTS (
                SELECT 1 FROM roles existing
                WHERE existing.company_id = c.id
                  AND existing.code = 'FIELD_MANAGER'
                  AND existing.archived_at IS NULL
            )
            """
        ).bindparams(at=now)
    )
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
            JOIN permissions p ON p.code IN :codes AND p.status = 'active'
            WHERE r.code = 'FIELD_MANAGER'
              AND r.is_system IS TRUE
              AND r.archived_at IS NULL
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ).bindparams(sa.bindparam("codes", expanding=True), at=now, codes=PROFILE_PERMISSIONS)
    )


def upgrade() -> None:
    _profile_permissions()


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM role_permissions rp
            USING roles r
            WHERE rp.role_id = r.id AND r.code = 'FIELD_MANAGER'
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM roles r
            WHERE r.code = 'FIELD_MANAGER'
              AND NOT EXISTS (
                SELECT 1 FROM membership_roles mr WHERE mr.role_id = r.id
              )
            """
        )
    )
