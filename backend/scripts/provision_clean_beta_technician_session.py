"""Issue a short-lived technician session for direct Clean Beta acceptance only.

This trusted runtime provisioner validates the existing Beta authority chain for
one active employee and issues a session for that employee's existing user. It
does not change passwords, roles, memberships, employee records, or permissions.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from app import main as application_model_registry  # noqa: F401
from app.core.config import settings
from app.database.session import AsyncSessionFactory, engine
from app.platform.audit.service import AuditEntry, audit_service
from app.platform.auth.models import AuthenticationSession
from app.platform.auth.services import access_token_service
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.employees.models import Employee
from app.platform.users.models import User, UserCredential
from sqlalchemy import select, update

COMPANY_ID = UUID("3ddf07ce-0f44-4b67-a40f-fb0ec41bb7cd")
BRANCH_ID = UUID("887f413a-70dc-4ab1-98aa-8e84f4e7efd0")
AUTHENTICATION_METHOD = "beta_technician_acceptance"
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
        raise ValueError(
            "technician acceptance sessions are forbidden outside Beta/Preview"
        )
    if args.company_id != COMPANY_ID or args.branch_id != BRANCH_ID:
        raise ValueError("clean Beta Company/Branch binding mismatch")
    output = Path(args.token_output).resolve()
    if str(output) != "/run/secrets/beta_technician_session_token":
        raise ValueError(
            "technician session token must use canonical secret custody path"
        )

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
            employee = await session.scalar(
                select(Employee).where(
                    Employee.id == args.employee_id,
                    Employee.company_id == COMPANY_ID,
                    Employee.home_branch_id == BRANCH_ID,
                    Employee.status == "active",
                    Employee.archived_at.is_(None),
                )
            )
            membership = None
            user = None
            credential = None
            if employee is not None and employee.membership_id is not None:
                membership = await session.scalar(
                    select(Membership).where(
                        Membership.id == employee.membership_id,
                        Membership.company_id == COMPANY_ID,
                        Membership.status == "active",
                        Membership.default_branch_id == BRANCH_ID,
                    )
                )
                if membership is not None:
                    user = await session.scalar(
                        select(User).where(
                            User.id == membership.user_id,
                            User.status == "active",
                            User.archived_at.is_(None),
                        )
                    )
                    credential = await session.scalar(
                        select(UserCredential).where(
                            UserCredential.user_id == membership.user_id
                        )
                    )
            if (
                company is None
                or branch is None
                or employee is None
                or membership is None
                or user is None
                or credential is None
            ):
                raise ValueError("clean Beta technician authority chain is incomplete")

            user_id = user.id
            await session.execute(
                update(AuthenticationSession)
                .where(
                    AuthenticationSession.user_id == user_id,
                    AuthenticationSession.status == "active",
                )
                .values(
                    status="revoked",
                    revoked_at=now,
                    revocation_reason="beta_technician_acceptance_rotated",
                    revoked_by_user_id=user_id,
                )
            )
            auth_session = AuthenticationSession(
                user_id=user_id,
                status="active",
                created_at=now,
                last_seen_at=now,
                absolute_expires_at=now + lifetime,
                idle_expires_at=None,
                authentication_method=AUTHENTICATION_METHOD,
                credential_version=credential.credential_version,
                authorization_version=user.authorization_version,
                device_label="clean-beta-technician-acceptance",
            )
            session.add(auth_session)
            await session.flush()
            token, token_expiry = access_token_service.issue(
                user_id=user_id,
                session_id=auth_session.id,
                credential_version=credential.credential_version,
                authorization_version=user.authorization_version,
                now=now,
            )
            expires_at = min(token_expiry, auth_session.absolute_expires_at)
            audit_service.stage(
                session,
                AuditEntry(
                    action="platform.beta_technician_acceptance_session_issued",
                    resource_type="authentication_session",
                    resource_id=auth_session.id,
                    actor_user_id=user_id,
                    company_id=COMPANY_ID,
                    details={
                        "branch_id": str(BRANCH_ID),
                        "employee_id": str(employee.id),
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
        "employee_id": str(args.employee_id),
        "session_id": str(auth_session.id),
        "expires_at": expires_at.isoformat(),
        "token_reference": str(output),
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--environment", choices=("preview",), required=True)
    result.add_argument("--company-id", required=True, type=UUID)
    result.add_argument("--branch-id", required=True, type=UUID)
    result.add_argument("--employee-id", required=True, type=UUID)
    result.add_argument(
        "--minutes", type=int, default=10, choices=range(5, MAX_MINUTES + 1)
    )
    result.add_argument(
        "--token-output", default="/run/secrets/beta_technician_session_token"
    )
    return result


async def main() -> None:
    args = parser().parse_args()
    if args.environment != "preview":
        raise SystemExit("clean Beta technician session requires Preview")
    try:
        print(json.dumps(await issue(args), sort_keys=True))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
