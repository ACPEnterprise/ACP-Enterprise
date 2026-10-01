"""Revoke an acceptance reader and all of its active sessions."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from uuid import UUID

from app import main as application_model_registry  # noqa: F401
from app.database.session import AsyncSessionFactory, engine
from app.platform.auth.services import access_token_service, authentication_service
from app.platform.permissions.authorization import authorization_service
from app.platform.service_principals.service import acceptance_service_principal_service


async def run(args: argparse.Namespace) -> dict[str, object]:
    actor_token = os.environ.get("ACP_RELEASE_ACTOR_TOKEN")
    if not actor_token:
        raise RuntimeError("ACP_RELEASE_ACTOR_TOKEN is required.")
    claims = access_token_service.decode(actor_token)
    async with AsyncSessionFactory() as session:
        authenticated = await authentication_service.validate_access_context(
            session, claims
        )
        context = await authorization_service.resolve(
            session,
            authenticated=authenticated,
            company_id=args.company_id,
            branch_id=None,
        )
        await session.rollback()
        async with session.begin():
            await acceptance_service_principal_service.revoke(
                session,
                context=context,
                principal_id=args.principal_id,
            )
    return {
        "principal_id": str(args.principal_id),
        "state": "revoked",
        "sessions_revoked": True,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--company-id", required=True, type=UUID)
    result.add_argument("--principal-id", required=True, type=UUID)
    return result


async def main() -> None:
    try:
        print(json.dumps(await run(parser().parse_args()), sort_keys=True))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
