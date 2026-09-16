"""Reconcile the Office Manager normal operating boundary.

Revision ID: m3n5p7r9t1v3
Revises: l2n4o6q8s0u2
"""

from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa

from alembic import op

revision: str = "m3n5p7r9t1v3"
down_revision: str | Sequence[str] | None = "l2n4o6q8s0u2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ADDED_PERMISSION_CODES = (
    "COMPANY_BRANCH_ACCESS_MANAGE",
    "COMPANY_COMMUNICATIONS_MANAGE",
    "COMPANY_COMMUNICATIONS_READ",
    "COMPANY_IDENTITY_ONBOARDING_MANAGE",
    "COMPANY_INVOICE_ISSUE",
    "COMPANY_INVOICE_MANAGE",
    "COMPANY_INVOICE_READ",
    "COMPANY_ESTIMATE_MANAGE",
    "COMPANY_ESTIMATE_READ",
    "COMPANY_MEMBERSHIP_MANAGE",
    "COMPANY_MEMBERSHIP_READ",
    "COMPANY_PAYMENT_READ",
    "COMPANY_ROLE_READ",
    "COMPANY_TIMEKEEPING_ADMIN_READ",
    "COMPANY_WORKFORCE_AVAILABILITY_MANAGE",
    "COMPANY_WORKFORCE_CAPABILITY_MANAGE",
    "COMPANY_WORKFORCE_MANAGE",
    "COMPANY_WORKFORCE_READ",
)


def _insert_permissions(codes: tuple[str, ...]) -> None:
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
            JOIN permissions p ON p.code IN :codes
            WHERE r.code = 'OFFICE_MANAGER'
              AND r.is_system IS TRUE
              AND r.archived_at IS NULL
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ).bindparams(
            sa.bindparam("codes", expanding=True),
            at=datetime.now(timezone.utc),
            codes=codes,
        )
    )


def _advance_affected_users() -> None:
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
                WHERE r.code = 'OFFICE_MANAGER'
                  AND r.is_system IS TRUE
                  AND r.archived_at IS NULL
                  AND mr.revoked_at IS NULL
                  AND m.status = 'active'
            )
            """
        ).bindparams(at=datetime.now(timezone.utc))
    )


def upgrade() -> None:
    _insert_permissions(ADDED_PERMISSION_CODES)
    op.execute(
        sa.text(
            """
            DELETE FROM role_permissions rp
            USING roles r, permissions p
            WHERE rp.role_id = r.id
              AND rp.permission_id = p.id
              AND r.code = 'OFFICE_MANAGER'
              AND r.is_system IS TRUE
              AND p.code = 'COMPANY_PRICE_BOOK_ACTIVATE'
            """
        )
    )
    _advance_affected_users()


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
              AND r.code = 'OFFICE_MANAGER'
              AND r.is_system IS TRUE
              AND p.code IN :codes
            """
        ).bindparams(sa.bindparam("codes", expanding=True), codes=ADDED_PERMISSION_CODES)
    )
    _insert_permissions(("COMPANY_PRICE_BOOK_ACTIVATE",))
    _advance_affected_users()
