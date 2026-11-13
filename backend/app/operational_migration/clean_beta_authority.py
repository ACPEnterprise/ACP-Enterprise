"""Idempotent authority seed for the isolated HCP Preview target."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.permissions.codes import MigrationPermission
from app.platform.permissions.models import MembershipRole, Permission, Role, RolePermission
from app.platform.launch_controls import COMPANY_ADMINISTRATOR_OWNER_READ_PERMISSIONS
from app.platform.users.models import User, UserCredential
from app.platform.auth.passwords import PasswordService


COMPANY_ID = UUID("3ddf07ce-0f44-4b67-a40f-fb0ec41bb7cd")
BRANCH_ID = UUID("887f413a-70dc-4ab1-98aa-8e84f4e7efd0")
ACTOR_ID = UUID("c427ebd1-7583-4c0d-9c54-55a0c1214174")
AUTHORITY_LOCK_ID = 7_692_551_201_488_231
ROLE_CODE = "COMPANY_ADMINISTRATOR"
MICHAEL_EMAIL = "allcountyleak@gmail.com"


class CleanBetaAuthorityError(RuntimeError):
    pass


@dataclass(frozen=True)
class CleanBetaAuthorityResult:
    action: str
    company_id: UUID
    branch_id: UUID
    actor_id: UUID
    membership_id: UUID
    role_id: UUID
    rows_created: int
    rows_reused: int


def _require_same(label: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise CleanBetaAuthorityError(f"clean_beta_authority_conflict:{label}")


async def reconcile_clean_beta_authority(
    session: AsyncSession,
    *,
    password_service: PasswordService,
) -> CleanBetaAuthorityResult:
    """Create/reuse only the exact Preview authority chain.

    This deliberately does not invoke the generic first-install bootstrap:
    that bootstrap generates IDs and is intended for an empty product install.
    The HCP authority already has immutable IDs and must bind to those IDs.
    """
    async with session.begin():
        await session.execute(select(func.pg_advisory_xact_lock(AUTHORITY_LOCK_ID)))
        now = datetime.now(timezone.utc)
        created = 0
        reused = 0

        company = await session.get(Company, COMPANY_ID)
        if company is None:
            company = Company(
                id=COMPANY_ID,
                name="All County Plumbing & Leak",
                code="ALL_COUNTY",
                status="active",
                timezone="America/New_York",
            )
            session.add(company)
            await session.flush()
            created += 1
        else:
            reused += 1
            _require_same("company.status", company.status, "active")

        branch = await session.get(Branch, BRANCH_ID)
        if branch is None:
            branch = Branch(
                id=BRANCH_ID,
                company_id=COMPANY_ID,
                name="MAIN",
                code="MAIN",
                status="active",
                timezone="America/New_York",
                is_primary=True,
            )
            session.add(branch)
            await session.flush()
            created += 1
        else:
            reused += 1
            _require_same("branch.company_id", branch.company_id, COMPANY_ID)
            _require_same("branch.status", branch.status, "active")

        user = await session.get(User, ACTOR_ID)
        if user is None:
            user = User(
                id=ACTOR_ID,
                normalized_email=MICHAEL_EMAIL,
                first_name="Michael",
                last_name="Fouse",
                display_name="Michael Fouse",
                status="active",
                authorization_version=1,
                email_verified_at=now,
            )
            session.add(user)
            await session.flush()
            session.add(
                UserCredential(
                    user_id=ACTOR_ID,
                    password_hash=password_service.hash_password(
                        secrets.token_urlsafe(32)
                    ),
                    password_changed_at=now,
                    failed_login_count=0,
                    credential_version=1,
                )
            )
            created += 2
        else:
            reused += 1
            _require_same("actor.status", user.status, "active")
            _require_same("actor.normalized_email", user.normalized_email, MICHAEL_EMAIL)
            credential = await session.scalar(
                select(UserCredential).where(UserCredential.user_id == ACTOR_ID)
            )
            if credential is None:
                session.add(
                    UserCredential(
                        user_id=ACTOR_ID,
                        password_hash=password_service.hash_password(
                            secrets.token_urlsafe(32)
                        ),
                        password_changed_at=now,
                        failed_login_count=0,
                        credential_version=1,
                    )
                )
                created += 1
            else:
                reused += 1

        membership = await session.scalar(
            select(Membership).where(
                Membership.user_id == ACTOR_ID,
                Membership.company_id == COMPANY_ID,
            )
        )
        if membership is None:
            membership = Membership(
                user_id=ACTOR_ID,
                company_id=COMPANY_ID,
                status="active",
                default_branch_id=BRANCH_ID,
                has_all_branch_access=True,
                invited_at=now,
                accepted_at=now,
            )
            session.add(membership)
            await session.flush()
            created += 1
        else:
            reused += 1
            _require_same("membership.status", membership.status, "active")
            _require_same("membership.default_branch_id", membership.default_branch_id, BRANCH_ID)
            _require_same("membership.has_all_branch_access", membership.has_all_branch_access, True)

        role = await session.scalar(
            select(Role).where(Role.company_id == COMPANY_ID, Role.code == ROLE_CODE)
        )
        if role is None:
            role = Role(
                company_id=COMPANY_ID,
                code=ROLE_CODE,
                name="Company Administrator",
                description="Canonical owner/admin Preview authority.",
                status="active",
                is_system=True,
                created_by_user_id=ACTOR_ID,
                updated_by_user_id=ACTOR_ID,
            )
            session.add(role)
            await session.flush()
            created += 1
        else:
            reused += 1
            _require_same("role.status", role.status, "active")

        required_codes = set(COMPANY_ADMINISTRATOR_OWNER_READ_PERMISSIONS)
        required_codes.add(MigrationPermission.EXECUTE_REHEARSAL)
        permissions = {
            permission.code: permission
            for permission in (
                await session.scalars(
                    select(Permission).where(Permission.code.in_(required_codes))
                )
            ).all()
        }
        missing = required_codes - permissions.keys()
        if missing:
            raise CleanBetaAuthorityError("clean_beta_authority_missing_permission")
        for code in sorted(required_codes):
            exists = await session.scalar(
                select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == permissions[code].id,
                )
            )
            if exists is None:
                session.add(
                    RolePermission(
                        role_id=role.id,
                        permission_id=permissions[code].id,
                        assigned_at=now,
                        assigned_by_user_id=ACTOR_ID,
                    )
                )
                created += 1
            else:
                reused += 1

        membership_role = await session.scalar(
            select(MembershipRole).where(
                MembershipRole.company_id == COMPANY_ID,
                MembershipRole.membership_id == membership.id,
                MembershipRole.role_id == role.id,
                MembershipRole.revoked_at.is_(None),
            )
        )
        if membership_role is None:
            session.add(
                MembershipRole(
                    company_id=COMPANY_ID,
                    membership_id=membership.id,
                    role_id=role.id,
                    assigned_at=now,
                    assigned_by_user_id=ACTOR_ID,
                    grant_reason="clean_beta_hcp_cutover_authority",
                )
            )
            created += 1
        else:
            reused += 1

        await session.flush()
        return CleanBetaAuthorityResult(
            action="created" if created else "reused",
            company_id=COMPANY_ID,
            branch_id=BRANCH_ID,
            actor_id=ACTOR_ID,
            membership_id=membership.id,
            role_id=role.id,
            rows_created=created,
            rows_reused=reused,
        )
