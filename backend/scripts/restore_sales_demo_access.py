"""Inspect or restore the preserved Sales Demo tenant without changing credentials.

The identity email is read from a mode-0600 protected file and is never printed.
The command is read-only unless ``--apply`` is supplied by the authorized hosted
operator.  It refuses any identity with access-bearing non-Demo memberships.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from app import main as application_model_registry  # noqa: F401
from app.access_agreements.models import AccessAgreementDocument
from app.access_agreements.service import SALES_DEMO_AGREEMENT_CODE
from app.database.session import AsyncSessionFactory, engine
from app.demo.enrichment import demo_enrichment_service
from app.demo.models import DemoEnvironment
from app.demo.service import PRESERVED_DEMO_COMPANY_ID, sales_demo_service
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.users.models import User, UserCredential
from sqlalchemy import select


def _protected_email(path: Path) -> str:
    resolved = path.resolve(strict=True)
    mode = resolved.stat().st_mode & 0o777
    if mode & 0o077:
        raise ValueError("identity file permissions must be mode 0600 or stricter")
    email = resolved.read_text(encoding="utf-8").strip().lower()
    if not email or "@" not in email or len(email) > 320:
        raise ValueError("identity file does not contain a valid login email")
    return email


async def execute(args: argparse.Namespace) -> dict[str, object]:
    email = _protected_email(args.identity_file)
    async with AsyncSessionFactory() as session:
        user = await session.scalar(
            select(User).where(
                User.normalized_email == email,
                User.status == "active",
                User.archived_at.is_(None),
            )
        )
        if user is None:
            raise ValueError("existing active Sales Demo identity was not found")
        credential = await session.scalar(
            select(UserCredential).where(UserCredential.user_id == user.id)
        )
        if credential is None:
            raise ValueError("existing Sales Demo credential was not found")
        memberships = (
            await session.scalars(
                select(Membership).where(Membership.user_id == user.id)
            )
        ).all()
        access_bearing_non_demo = [
            row
            for row in memberships
            if row.company_id != PRESERVED_DEMO_COMPANY_ID
            and row.status in {"invited", "active", "suspended"}
        ]
        company = await session.get(Company, PRESERVED_DEMO_COMPANY_ID)
        environment = await session.scalar(
            select(DemoEnvironment).where(DemoEnvironment.owner_user_id == user.id)
        )
        agreement = await session.scalar(
            select(AccessAgreementDocument).where(
                AccessAgreementDocument.code == SALES_DEMO_AGREEMENT_CODE,
                AccessAgreementDocument.status == "published",
                AccessAgreementDocument.mandatory.is_(True),
            )
        )
        receipt: dict[str, object] = {
            "status": "READY" if not access_bearing_non_demo else "BLOCKED",
            "mode": "inspect",
            "identity_id": str(user.id),
            "credential_preserved": True,
            "credential_version": credential.credential_version,
            "demo_company_id": str(PRESERVED_DEMO_COMPANY_ID),
            "demo_company_present": company is not None,
            "demo_environment_present": environment is not None,
            "non_demo_access_memberships": len(access_bearing_non_demo),
            "agreement_published": agreement is not None,
            "external_actions": "apply is guarded by Sales Demo runtime safety checks",
        }
        if access_bearing_non_demo:
            return receipt
        if not args.apply:
            return receipt

        before_hash = credential.password_hash
        before_version = credential.credential_version
        context = SimpleNamespace(user=SimpleNamespace(id=user.id))
        result = await sales_demo_service.restore_preserved_company(
            session, context=context
        )
        enrichment = await demo_enrichment_service.enrich(
            session, company_id=result.company_id, actor_id=user.id
        )
        await session.flush()
        refreshed_credential = await session.scalar(
            select(UserCredential).where(UserCredential.user_id == user.id)
        )
        if (
            refreshed_credential is None
            or refreshed_credential.password_hash != before_hash
            or refreshed_credential.credential_version != before_version
        ):
            raise ValueError("credential preservation check failed")
        await session.commit()
        receipt.update(
            {
                "status": "PASS",
                "mode": "apply",
                "action": result.action,
                "branch_id": str(result.branch_id),
                "base_counts": result.counts,
                "enrichment_version": enrichment.version,
                "enrichment_created": enrichment.created,
                "enrichment_existing": enrichment.existing,
            }
        )
        return receipt


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--identity-file", required=True, type=Path)
    result.add_argument(
        "--apply",
        action="store_true",
        help="Authorized hosted operator only: commit the isolated restoration.",
    )
    return result


async def main() -> None:
    try:
        args = parser().parse_args()
        print(json.dumps(await execute(args), sort_keys=True))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
