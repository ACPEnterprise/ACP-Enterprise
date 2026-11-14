"""Issue a short-lived owner session for direct Clean Beta acceptance only.

This is a trusted runtime provisioner. It does not change the owner password,
roles, memberships, or permissions; it only validates the immutable Clean Beta
authority chain and issues one short-lived application access session.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app import main as application_model_registry  # noqa: F401
from app.core.config import settings
from app.database.session import AsyncSessionFactory, engine
from app.platform.audit.service import AuditEntry, audit_service
from app.platform.auth.models import AuthenticationSession
from app.platform.auth.services import access_token_service
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership, MembershipRole
from app.platform.company.models import Company
from app.platform.permissions.models import Role
from app.platform.service_principals.models import (
    AcceptanceServicePrincipal,
    ReleaseServicePrincipal,
)
from app.platform.users.models import User, UserCredential

COMPANY_ID = UUID("3ddf07ce-0f44-4b67-a40f-fb0ec41bb7cd")
BRANCH_ID = UUID("887f413a-70dc-4ab1-98aa-8e84f4e7efd0")
ACTOR_ID = UUID("c427ebd1-7583-4c0d-9c54-55a0c1214174")
ROLE_CODE = "COMPANY_ADMINISTRATOR"
AUTHENTICATION_METHOD = "beta_owner_acceptance"
MAX_MINUTES = 15


def _write_token(path: Path, token: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(descriptor, token.encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(path, 0o600)


async def issue(args: argparse.Namespace) -> dict[str, object]:
    if settings.environment.strip().lower() not in {"preview", "beta", "test"}:
        raise ValueError("owner acceptance sessions are forbidden outside Beta/Preview")
    if args.company_id != COMPANY_ID or args.branch_id != BRANCH_ID:
        raise ValueError("clean Beta Company/Branch binding mismatch")
    output = Path(args.token_output).resolve()
    if str(output) != "/run/secrets/beta_owner_session_token":
        raise ValueError("owner session token must use canonical secret custody path")

    now = datetime.now(timezone.utc)
    lifetime = timedelta(minutes=args.minutes)
    async with AsyncSessionFactory() as session:
        async with session.begin():
            company = await session.scalar(
                select(Company).where(
                    Company.id == COMPANY_ID, Company.status == "active"
                )
            )
            branch = await session.scalar(
                select(Branch).where(
                    Branch.id == BRANCH_ID,
                    Branch.company_id == COMPANY_ID,
                    Branch.status == "active",
                )
            )
            user = await session.scalar(
                select(User).where(
                    User.id == ACTOR_ID,
                    User.status == "active",
                    User.archived_at.is_(None),
                )
            )
            membership = await session.scalar(
                select(Membership).where(
                    Membership.user_id == ACTOR_ID,
                    Membership.company_id == COMPANY_ID,
                    Membership.status == "active",
                    Membership.default_branch_id == BRANCH_ID,
                    Membership.has_all_branch_access.is_(True),
                )
            )
            credential = await session.scalar(
                select(UserCredential).where(UserCredential.user_id == ACTOR_ID)
            )
            role = await session.scalar(
                select(Role).where(
                    Role.company_id == COMPANY_ID,
                    Role.code == ROLE_CODE,
                    Role.status == "active",
                    Role.archived_at.is_(None),
                    Role.is_system.is_(True),
                )
            )
            assignment = None
            if membership is not None and role is not None:
                assignment = await session.scalar(
                    select(MembershipRole).where(
                        MembershipRole.company_id == COMPANY_ID,
                        MembershipRole.membership_id == membership.id,
                        MembershipRole.role_id == role.id,
                        MembershipRole.revoked_at.is_(None),
                    )
                )
            if any(
                item is None
                for item in (company, branch, user, membership, credential, role, assignment)
            ):
                raise ValueError("clean Beta owner authority chain is incomplete")
            if await session.scalar(
                select(AcceptanceServicePrincipal.id).where(
                    AcceptanceServicePrincipal.user_id == ACTOR_ID,
                    AcceptanceServicePrincipal.state == "active",
                )
            ) is not None or await session.scalar(
                select(ReleaseServicePrincipal.id).where(
                    ReleaseServicePrincipal.user_id == ACTOR_ID,
                    ReleaseServicePrincipal.state == "active",
                )
            ) is not None:
                raise ValueError("owner actor is also bound to a non-human principal")

            await session.execute(
                AuthenticationSession.__table__.update()
                .where(
                    AuthenticationSession.user_id == ACTOR_ID,
                    AuthenticationSession.status == "active",
                )
                .values(
                    status="revoked",
                    revoked_at=now,
                    revocation_reason="beta_owner_acceptance_rotated",
                    revoked_by_user_id=ACTOR_ID,
                )
            )
            auth_session = AuthenticationSession(
                user_id=ACTOR_ID,
                status="active",
                created_at=now,
                last_seen_at=now,
                absolute_expires_at=now + lifetime,
                idle_expires_at=None,
                authentication_method=AUTHENTICATION_METHOD,
                credential_version=credential.credential_version,
                authorization_version=user.authorization_version,
                device_label="clean-beta-owner-acceptance",
            )
            session.add(auth_session)
            await session.flush()
            token, token_expiry = access_token_service.issue(
                user_id=ACTOR_ID,
                session_id=auth_session.id,
                credential_version=credential.credential_version,
                authorization_version=user.authorization_version,
                now=now,
            )
            expires_at = min(token_expiry, auth_session.absolute_expires_at)
            audit_service.stage(
                session,
                AuditEntry(
                    action="platform.beta_owner_acceptance_session_issued",
                    resource_type="authentication_session",
                    resource_id=auth_session.id,
                    actor_user_id=ACTOR_ID,
                    company_id=COMPANY_ID,
                    details={
                        "branch_id": str(BRANCH_ID),
                        "expires_at": expires_at.isoformat(),
                        "authentication_method": AUTHENTICATION_METHOD,
                    },
                ),
            )
        _write_token(output, token)
    return {
        "status": "PASS",
        "company_id": str(COMPANY_ID),
        "branch_id": str(BRANCH_ID),
        "actor_id": str(ACTOR_ID),
        "session_id": str(auth_session.id),
        "expires_at": expires_at.isoformat(),
        "token_reference": str(output),
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--environment", choices=("preview",), required=True)
    result.add_argument("--company-id", required=True, type=UUID)
    result.add_argument("--branch-id", required=True, type=UUID)
    result.add_argument("--minutes", type=int, default=10, choices=range(5, MAX_MINUTES + 1))
    result.add_argument(
        "--token-output", default="/run/secrets/beta_owner_session_token"
    )
    return result


async def main() -> None:
    args = parser().parse_args()
    if args.environment != "preview":
        raise SystemExit("clean Beta owner session requires Preview")
    try:
        print(json.dumps(await issue(args), sort_keys=True))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
