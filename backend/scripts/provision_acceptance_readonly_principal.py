"""Provision a scoped acceptance reader and seal its short-lived token locally."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import timedelta
from pathlib import Path
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
            principal = await acceptance_service_principal_service.provision(
                session, context=context
            )
            issued = await acceptance_service_principal_service.issue_session(
                session,
                context=context,
                principal_id=principal.principal_id,
                lifetime=timedelta(minutes=args.minutes),
            )
    output = Path(args.token_output).resolve()
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(output.parent, 0o700)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(descriptor, issued.access_token.encode("utf-8"))
    finally:
        os.close(descriptor)
    os.chmod(output, 0o600)
    return {
        "principal_id": str(principal.principal_id),
        "session_id": str(issued.session_id),
        "expires_at": issued.expires_at.isoformat(),
        "created": principal.created,
        "token_output": str(output),
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--company-id", required=True, type=UUID)
    result.add_argument(
        "--minutes", type=int, default=60, choices=range(5, 61), metavar="5..60"
    )
    result.add_argument("--token-output", required=True)
    return result


async def main() -> None:
    try:
        print(json.dumps(await run(parser().parse_args()), sort_keys=True))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
