from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.audit.service import AuditEntry, audit_service
from app.platform.auth.models import AuthenticationSession
from app.platform.company.membership_models import Membership
from app.platform.factory_control.models import PlatformAuthorityAssignment
from app.platform.permissions.codes import LaunchPlatformPermission
from app.platform.permissions.models import MembershipRole, Role
from app.platform.users.models import User, UserCredential


@dataclass(frozen=True, slots=True)
class OwnerAuthorityResult:
    user_id: UUID
    membership_id: UUID
    owner_role_id: UUID
    owner_role_created: bool
    platform_owner_created: bool
    identity_reconciled: bool
    authorization_version: int


@dataclass(frozen=True, slots=True)
class PlatformAdministratorResult:
    user_id: UUID
    membership_id: UUID
    admin_role_id: UUID
    admin_role_created: bool
    authorization_version: int


async def reconcile_canonical_platform_owner(
    session: AsyncSession,
    *,
    user_id: UUID,
    membership_id: UUID,
    company_id: UUID,
    expected_existing_display_name: str,
    canonical_first_name: str,
    canonical_last_name: str,
    reason: str,
) -> OwnerAuthorityResult:
    """Reconcile an owner-confirmed, already-authenticated principal in place.

    This deliberately accepts UUID authority plus the exact pre-reconciliation
    display name. It never accepts an email/name search as binding authority and
    never creates a User, Membership, credential, or Employee.
    """

    values = (
        expected_existing_display_name.strip(),
        canonical_first_name.strip(),
        canonical_last_name.strip(),
        reason.strip(),
    )
    if not all(values):
        raise ValueError("Owner reconciliation requires exact identity and reason.")

    now = datetime.now(timezone.utc)
    user = await session.scalar(
        select(User)
        .where(
            User.id == user_id,
            User.status == "active",
            User.archived_at.is_(None),
        )
        .with_for_update()
    )
    if user is None or user.display_name not in {
        expected_existing_display_name.strip(),
        f"{canonical_first_name.strip()} {canonical_last_name.strip()}",
    }:
        raise ValueError("Exact active owner authentication principal was not found.")

    membership = await session.scalar(
        select(Membership)
        .where(
            Membership.id == membership_id,
            Membership.user_id == user.id,
            Membership.company_id == company_id,
            Membership.status == "active",
        )
        .with_for_update()
    )
    credential = await session.scalar(
        select(UserCredential).where(UserCredential.user_id == user.id)
    )
    successful_session_count = await session.scalar(
        select(func.count())
        .select_from(AuthenticationSession)
        .where(
            AuthenticationSession.user_id == user.id,
            AuthenticationSession.status == "active",
        )
    )
    if membership is None or credential is None or not successful_session_count:
        raise ValueError(
            "Owner principal lacks active membership or authentication evidence."
        )

    canonical_display_name = (
        f"{canonical_first_name.strip()} {canonical_last_name.strip()}"
    )
    duplicate = await session.scalar(
        select(User.id).where(
            User.id != user.id,
            func.lower(User.display_name) == canonical_display_name.lower(),
            User.archived_at.is_(None),
        )
    )
    if duplicate is not None:
        raise ValueError("Another canonical owner identity already exists.")

    owner_role = await session.scalar(
        select(Role).where(
            Role.company_id == company_id,
            Role.code == "OWNER",
            Role.status == "active",
            Role.archived_at.is_(None),
            Role.is_system.is_(True),
        )
    )
    if owner_role is None:
        raise ValueError("Canonical OWNER role is not reconciled and active.")

    changed = False
    identity_reconciled = user.display_name != canonical_display_name
    if identity_reconciled:
        user.first_name = canonical_first_name.strip()
        user.last_name = canonical_last_name.strip()
        user.display_name = canonical_display_name
        changed = True

    owner_assignment = await session.scalar(
        select(MembershipRole).where(
            MembershipRole.company_id == company_id,
            MembershipRole.membership_id == membership.id,
            MembershipRole.role_id == owner_role.id,
            MembershipRole.revoked_at.is_(None),
        )
    )
    owner_role_created = owner_assignment is None
    if owner_assignment is None:
        owner_assignment = MembershipRole(
            company_id=company_id,
            membership_id=membership.id,
            role_id=owner_role.id,
            assigned_at=now,
            assigned_by_user_id=user.id,
        )
        session.add(owner_assignment)
        changed = True

    platform_assignment = await session.scalar(
        select(PlatformAuthorityAssignment).where(
            PlatformAuthorityAssignment.principal_type == "USER",
            PlatformAuthorityAssignment.user_id == user.id,
            PlatformAuthorityAssignment.permission_code
            == LaunchPlatformPermission.FACTORY_CONTROL_READ,
            PlatformAuthorityAssignment.status == "active",
        )
    )
    platform_owner_created = platform_assignment is None
    if platform_assignment is None:
        session.add(
            PlatformAuthorityAssignment(
                principal_type="USER",
                user_id=user.id,
                authority_code="PLATFORM_OWNER",
                permission_code=LaunchPlatformPermission.FACTORY_CONTROL_READ,
                status="active",
                grant_reason=reason.strip(),
                granted_by_user_id=user.id,
                granted_at=now,
                version=1,
            )
        )
        changed = True
    elif platform_assignment.authority_code != "PLATFORM_OWNER":
        raise ValueError("Owner principal has conflicting active platform authority.")

    if changed:
        user.authorization_version += 1
        user.updated_at = now
        audit_service.stage(
            session,
            AuditEntry(
                action="platform.owner_authority.reconciled",
                resource_type="user",
                resource_id=user.id,
                actor_user_id=user.id,
                company_id=company_id,
                reason_code="OWNER_CONFIRMED_EXISTING_PRINCIPAL",
                details={
                    "membership_id": str(membership.id),
                    "owner_role_id": str(owner_role.id),
                    "identity_reconciled": identity_reconciled,
                    "owner_role_created": owner_role_created,
                    "platform_owner_created": platform_owner_created,
                },
            ),
        )
    await session.flush()
    return OwnerAuthorityResult(
        user_id=user.id,
        membership_id=membership.id,
        owner_role_id=owner_role.id,
        owner_role_created=owner_role_created,
        platform_owner_created=platform_owner_created,
        identity_reconciled=identity_reconciled,
        authorization_version=user.authorization_version,
    )


async def reconcile_canonical_platform_administrator(
    session: AsyncSession,
    *,
    user_id: UUID,
    membership_id: UUID,
    company_id: UUID,
    exact_display_name: str,
    granted_by_user_id: UUID,
    reason: str,
) -> PlatformAdministratorResult:
    """Bind a proven PLATFORM_ADMIN human to the canonical normal ADMIN role."""

    if not exact_display_name.strip() or not reason.strip():
        raise ValueError(
            "Platform administrator reconciliation requires exact identity."
        )
    user = await session.scalar(
        select(User)
        .where(
            User.id == user_id,
            User.display_name == exact_display_name.strip(),
            User.status == "active",
            User.archived_at.is_(None),
        )
        .with_for_update()
    )
    membership = await session.scalar(
        select(Membership)
        .where(
            Membership.id == membership_id,
            Membership.user_id == user_id,
            Membership.company_id == company_id,
            Membership.status == "active",
        )
        .with_for_update()
    )
    platform_admin = await session.scalar(
        select(PlatformAuthorityAssignment).where(
            PlatformAuthorityAssignment.principal_type == "USER",
            PlatformAuthorityAssignment.user_id == user_id,
            PlatformAuthorityAssignment.authority_code == "PLATFORM_ADMIN",
            PlatformAuthorityAssignment.permission_code
            == LaunchPlatformPermission.FACTORY_CONTROL_READ,
            PlatformAuthorityAssignment.status == "active",
        )
    )
    if user is None or membership is None or platform_admin is None:
        raise ValueError("Exact active platform administrator authority was not found.")
    grantor_membership = await session.scalar(
        select(Membership).where(
            Membership.user_id == granted_by_user_id,
            Membership.company_id == company_id,
            Membership.status == "active",
        )
    )
    if grantor_membership is None:
        raise ValueError("Grantor lacks active Company authority.")
    admin_role = await session.scalar(
        select(Role).where(
            Role.company_id == company_id,
            Role.code == "ADMIN",
            Role.status == "active",
            Role.archived_at.is_(None),
            Role.is_system.is_(True),
        )
    )
    if admin_role is None:
        raise ValueError("Canonical ADMIN role is not reconciled and active.")
    assignment = await session.scalar(
        select(MembershipRole).where(
            MembershipRole.company_id == company_id,
            MembershipRole.membership_id == membership_id,
            MembershipRole.role_id == admin_role.id,
            MembershipRole.revoked_at.is_(None),
        )
    )
    created = assignment is None
    if created:
        now = datetime.now(timezone.utc)
        session.add(
            MembershipRole(
                company_id=company_id,
                membership_id=membership_id,
                role_id=admin_role.id,
                assigned_at=now,
                assigned_by_user_id=granted_by_user_id,
            )
        )
        user.authorization_version += 1
        user.updated_at = now
        audit_service.stage(
            session,
            AuditEntry(
                action="platform.administrator_authority.reconciled",
                resource_type="membership",
                resource_id=membership_id,
                actor_user_id=granted_by_user_id,
                company_id=company_id,
                reason_code="EXISTING_PLATFORM_ADMIN_NORMAL_AUTHORITY",
                details={"admin_role_id": str(admin_role.id), "user_id": str(user.id)},
            ),
        )
    await session.flush()
    return PlatformAdministratorResult(
        user_id=user.id,
        membership_id=membership.id,
        admin_role_id=admin_role.id,
        admin_role_created=created,
        authorization_version=user.authorization_version,
    )
