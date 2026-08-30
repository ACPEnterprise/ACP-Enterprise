from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.company.membership_models import Membership
from app.platform.launch_controls import COMPANY_ADMINISTRATOR_OWNER_READ_PERMISSIONS
from app.platform.permissions.models import (
    MembershipRole,
    Permission,
    Role,
    RolePermission,
)
from app.platform.users.models import User

OWNER_READ_POLICY_LOCK_ID = 4_701_871_310_042_023


@dataclass(frozen=True, slots=True)
class OwnerReadPolicyResult:
    company_id: UUID
    added_codes: tuple[str, ...]
    affected_user_ids: tuple[UUID, ...]


class OwnerReadPolicyService:
    """Idempotently reconcile the approved Company Administrator read policy."""

    async def synchronize(
        self, session: AsyncSession
    ) -> tuple[OwnerReadPolicyResult, ...]:
        async with session.begin():
            await session.execute(
                select(func.pg_advisory_xact_lock(OWNER_READ_POLICY_LOCK_ID))
            )
            roles = tuple(
                (
                    await session.scalars(
                        select(Role)
                        .where(
                            Role.code == "COMPANY_ADMINISTRATOR",
                            Role.status == "active",
                        )
                        .order_by(Role.company_id)
                        .with_for_update()
                    )
                ).all()
            )
            permissions = {
                item.code: item
                for item in (
                    await session.scalars(
                        select(Permission).where(
                            Permission.code.in_(
                                COMPANY_ADMINISTRATOR_OWNER_READ_PERMISSIONS
                            ),
                            Permission.status == "active",
                            Permission.retired_at.is_(None),
                        )
                    )
                ).all()
            }
            missing_catalog = (
                COMPANY_ADMINISTRATOR_OWNER_READ_PERMISSIONS - permissions.keys()
            )
            if missing_catalog:
                raise RuntimeError(
                    "Canonical owner-read permissions are not synchronized: "
                    + ", ".join(sorted(missing_catalog))
                )
            now = datetime.now(timezone.utc)
            results: list[OwnerReadPolicyResult] = []
            for role in roles:
                existing = frozenset(
                    (
                        await session.scalars(
                            select(Permission.code)
                            .join(
                                RolePermission,
                                RolePermission.permission_id == Permission.id,
                            )
                            .where(RolePermission.role_id == role.id)
                        )
                    ).all()
                )
                added_codes = tuple(
                    sorted(COMPANY_ADMINISTRATOR_OWNER_READ_PERMISSIONS - existing)
                )
                user_ids = tuple(
                    sorted(
                        (
                            await session.scalars(
                                select(Membership.user_id)
                                .join(
                                    MembershipRole,
                                    MembershipRole.membership_id == Membership.id,
                                )
                                .where(
                                    Membership.company_id == role.company_id,
                                    Membership.status == "active",
                                    MembershipRole.role_id == role.id,
                                    MembershipRole.revoked_at.is_(None),
                                )
                                .distinct()
                            )
                        ).all(),
                        key=str,
                    )
                )
                if added_codes:
                    actor_id = role.updated_by_user_id or role.created_by_user_id
                    session.add_all(
                        RolePermission(
                            role_id=role.id,
                            permission_id=permissions[code].id,
                            assigned_at=now,
                            assigned_by_user_id=actor_id,
                        )
                        for code in added_codes
                    )
                    users = tuple(
                        (
                            await session.scalars(
                                select(User)
                                .where(User.id.in_(user_ids))
                                .with_for_update()
                            )
                        ).all()
                    )
                    for user in users:
                        user.authorization_version += 1
                results.append(
                    OwnerReadPolicyResult(role.company_id, added_codes, user_ids)
                )
        return tuple(results)


owner_read_policy_service = OwnerReadPolicyService()
