import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID

from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.audit.service import AuditEntry, audit_service
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.canonical_roles import (
    CANONICAL_ROLE_DEFINITIONS,
    validate_canonical_roles,
)
from app.platform.permissions.catalog import permission_catalog
from app.platform.permissions.codes import AdministrationPermission
from app.platform.permissions.models import (
    MembershipRole,
    Permission,
    Role,
    RolePermission,
)
from app.platform.users.models import User


class RoleSyncClassification(StrEnum):
    ALREADY_CONFORMING = "ALREADY_CONFORMING"
    MISSING_CANONICAL_ROLE = "MISSING_CANONICAL_ROLE"
    MISSING_CANONICAL_PERMISSION = "MISSING_CANONICAL_PERMISSION"
    CONFLICT_REQUIRES_REVIEW = "CONFLICT_REQUIRES_REVIEW"
    UNSAFE_IDENTITY_COLLISION = "UNSAFE_IDENTITY_COLLISION"


@dataclass(frozen=True, slots=True)
class RoleSyncItem:
    code: str
    classification: RoleSyncClassification
    missing_permissions: tuple[str, ...] = ()
    metadata_update_required: bool = False


@dataclass(frozen=True, slots=True)
class RoleSyncPlan:
    company_id: UUID
    items: tuple[RoleSyncItem, ...]

    @property
    def safe_to_apply(self) -> bool:
        blocked = {
            RoleSyncClassification.CONFLICT_REQUIRES_REVIEW,
            RoleSyncClassification.UNSAFE_IDENTITY_COLLISION,
        }
        return not any(item.classification in blocked for item in self.items)

    @property
    def digest(self) -> str:
        content = {
            "company_id": str(self.company_id),
            "items": [
                {
                    "code": item.code,
                    "classification": item.classification.value,
                    "missing_permissions": list(item.missing_permissions),
                    "metadata_update_required": item.metadata_update_required,
                }
                for item in self.items
            ],
        }
        return hashlib.sha256(
            json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class RoleSyncResult:
    plan: RoleSyncPlan
    roles_created: tuple[str, ...]
    permissions_added: tuple[str, ...]
    metadata_restored: tuple[str, ...]
    authorization_users_advanced: int


class CanonicalRoleSyncConflict(ValueError):
    pass


class CanonicalRoleSyncService:
    async def plan(
        self, session: AsyncSession, *, company_id: UUID
    ) -> RoleSyncPlan:
        canonical_permissions = frozenset(
            definition.code for definition in permission_catalog.definitions
        )
        validate_canonical_roles(canonical_permissions)
        roles = tuple(
            (
                await session.scalars(
                    select(Role)
                    .where(
                        Role.company_id == company_id,
                        Role.code.in_(role.code for role in CANONICAL_ROLE_DEFINITIONS),
                    )
                    .order_by(Role.code, Role.created_at, Role.id)
                )
            ).all()
        )
        by_code: dict[str, list[Role]] = {}
        for role in roles:
            by_code.setdefault(role.code, []).append(role)
        permission_rows = {
            item.code: item
            for item in (
                await session.scalars(
                    select(Permission).where(Permission.code.in_(canonical_permissions))
                )
            ).all()
        }
        items: list[RoleSyncItem] = []
        for definition in CANONICAL_ROLE_DEFINITIONS:
            matches = by_code.get(definition.code, [])
            if any(not role.is_system for role in matches):
                items.append(
                    RoleSyncItem(
                        definition.code,
                        RoleSyncClassification.UNSAFE_IDENTITY_COLLISION,
                    )
                )
                continue
            if len(matches) > 1:
                items.append(
                    RoleSyncItem(
                        definition.code,
                        RoleSyncClassification.CONFLICT_REQUIRES_REVIEW,
                    )
                )
                continue
            if not matches:
                items.append(
                    RoleSyncItem(
                        definition.code,
                        RoleSyncClassification.MISSING_CANONICAL_ROLE,
                        tuple(sorted(definition.permission_codes)),
                    )
                )
                continue
            role = matches[0]
            assigned = frozenset(
                await session.scalars(
                    select(Permission.code)
                    .join(RolePermission, RolePermission.permission_id == Permission.id)
                    .where(RolePermission.role_id == role.id)
                )
            )
            missing = tuple(sorted(definition.permission_codes - assigned))
            missing_catalog = tuple(
                code for code in missing if code not in permission_rows
            )
            if missing_catalog:
                items.append(
                    RoleSyncItem(
                        definition.code,
                        RoleSyncClassification.CONFLICT_REQUIRES_REVIEW,
                        missing_catalog,
                    )
                )
                continue
            metadata = (
                role.name != definition.name
                or role.description != definition.purpose
                or role.status != "active"
                or role.archived_at is not None
            )
            items.append(
                RoleSyncItem(
                    definition.code,
                    (
                        RoleSyncClassification.MISSING_CANONICAL_PERMISSION
                        if missing
                        else RoleSyncClassification.ALREADY_CONFORMING
                    ),
                    missing,
                    metadata,
                )
            )
        return RoleSyncPlan(company_id=company_id, items=tuple(items))

    async def apply(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        expected_plan_digest: str | None = None,
    ) -> RoleSyncResult:
        if not context.has_permission(AdministrationPermission.PERMISSION_MANAGE):
            raise CanonicalRoleSyncConflict("Permission management authority is required.")
        created: list[str] = []
        added: list[str] = []
        restored: list[str] = []
        affected_users: set[UUID] = set()
        async with session.begin():
            company = await session.scalar(
                select(Company)
                .where(Company.id == context.company.id)
                .with_for_update()
            )
            if company is None:
                raise CanonicalRoleSyncConflict("Company was not found.")
            plan = await self.plan(session, company_id=company.id)
            if (
                expected_plan_digest is not None
                and expected_plan_digest != plan.digest
                and any(
                    item.classification
                    is not RoleSyncClassification.ALREADY_CONFORMING
                    or item.metadata_update_required
                    for item in plan.items
                )
            ):
                raise CanonicalRoleSyncConflict("Canonical role plan changed before apply.")
            if not plan.safe_to_apply:
                raise CanonicalRoleSyncConflict("Canonical role conflicts require review.")
            permissions = {
                value.code: value
                for value in (
                    await session.scalars(
                        select(Permission).where(Permission.status == "active")
                    )
                ).all()
            }
            existing_roles = {
                role.code: role
                for role in (
                    await session.scalars(
                        select(Role).where(
                            Role.company_id == company.id,
                            Role.is_system.is_(True),
                            Role.code.in_(item.code for item in CANONICAL_ROLE_DEFINITIONS),
                        )
                    )
                ).all()
            }
            now = datetime.now(timezone.utc)
            for definition in CANONICAL_ROLE_DEFINITIONS:
                role = existing_roles.get(definition.code)
                if role is None:
                    role = Role(
                        company_id=company.id,
                        code=definition.code,
                        name=definition.name,
                        description=definition.purpose,
                        status="active",
                        is_system=True,
                        created_by_user_id=context.user.id,
                        updated_by_user_id=context.user.id,
                    )
                    session.add(role)
                    await session.flush()
                    existing_roles[role.code] = role
                    created.append(role.code)
                elif (
                    role.name != definition.name
                    or role.description != definition.purpose
                    or role.status != "active"
                    or role.archived_at is not None
                ):
                    role.name = definition.name
                    role.description = definition.purpose
                    role.status = "active"
                    role.archived_at = None
                    role.updated_at = now
                    role.updated_by_user_id = context.user.id
                    restored.append(role.code)
                assigned = frozenset(
                    await session.scalars(
                        select(Permission.code)
                        .join(RolePermission, RolePermission.permission_id == Permission.id)
                        .where(RolePermission.role_id == role.id)
                    )
                )
                for code in sorted(definition.permission_codes - assigned):
                    permission = permissions.get(code)
                    if permission is None:
                        raise CanonicalRoleSyncConflict(
                            "Canonical Permission catalog is incomplete."
                        )
                    session.add(
                        RolePermission(
                            role_id=role.id,
                            permission_id=permission.id,
                            assigned_at=now,
                            assigned_by_user_id=context.user.id,
                        )
                    )
                    added.append(f"{role.code}:{code}")
                    affected_users.update(
                        await session.scalars(
                            select(distinct(Membership.user_id))
                            .join(
                                MembershipRole,
                                MembershipRole.membership_id == Membership.id,
                            )
                            .where(
                                Membership.company_id == company.id,
                                Membership.status == "active",
                                MembershipRole.company_id == company.id,
                                MembershipRole.role_id == role.id,
                                MembershipRole.revoked_at.is_(None),
                            )
                        )
                    )
            users = tuple(
                (
                    await session.scalars(
                        select(User)
                        .where(User.id.in_(affected_users))
                        .with_for_update()
                    )
                ).all()
            )
            for user in users:
                user.authorization_version += 1
            result = RoleSyncResult(
                plan=plan,
                roles_created=tuple(created),
                permissions_added=tuple(added),
                metadata_restored=tuple(restored),
                authorization_users_advanced=len(users),
            )
            audit_service.stage(
                session,
                AuditEntry(
                    action="company.canonical_roles_reconciled",
                    resource_type="access_policy",
                    resource_id=company.id,
                    actor_user_id=context.user.id,
                    company_id=company.id,
                    branch_id=context.active_branch.id if context.active_branch else None,
                    details={
                        "plan_digest": plan.digest,
                        "expected_plan_digest": expected_plan_digest,
                        "authority": "canonical_role_sync",
                        "roles_created": list(result.roles_created),
                        "permissions_added": list(result.permissions_added),
                        "metadata_restored": list(result.metadata_restored),
                        "authorization_users_advanced": result.authorization_users_advanced,
                        "classification_before": [
                            {"code": item.code, "classification": item.classification.value}
                            for item in plan.items
                        ],
                    },
                ),
            )
        return result


canonical_role_sync_service = CanonicalRoleSyncService()
