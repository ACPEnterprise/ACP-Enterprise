"""Stage sealed HCP Employee authority for owner Workforce certification."""

from __future__ import annotations

import argparse
import asyncio
import json
from uuid import UUID

from app import main as application_model_registry  # noqa: F401
from app.database.session import AsyncSessionFactory, engine
from app.operational_migration.hcp_workforce_source_staging import (
    WorkforceSourcePacket,
    workforce_source_staging_service,
)
from app.platform.auth.services import access_token_service, authentication_service
from app.platform.permissions.authorization import authorization_service


async def run(args: argparse.Namespace) -> dict[str, object]:
    claims = access_token_service.decode(args.access_token)
    async with AsyncSessionFactory() as session:
        authenticated = await authentication_service.validate_access_context(
            session, claims
        )
        context = await authorization_service.resolve(
            session,
            authenticated=authenticated,
            company_id=args.company_id,
            branch_id=args.branch_id,
        )
        await session.rollback()
        async with session.begin():
            result = await workforce_source_staging_service.stage(
                session,
                context=context,
                master_run_id=args.master_run_id,
                packet=WorkforceSourcePacket.load(),
            )
    return {
        "classification": "HCP_WORKFORCE_SOURCE_AUTHORITY_STAGED",
        "packet_digest": result.packet_digest,
        "staged": result.staged,
        "created_candidates": result.created_candidates,
        "terminated": result.terminated,
        "owner_decisions": result.owner_decisions,
        "replayed": result.replayed,
        "invitations_sent": 0,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--company-id", type=UUID, required=True)
    result.add_argument("--branch-id", type=UUID, required=True)
    result.add_argument("--master-run-id", type=UUID, required=True)
    result.add_argument("--access-token", required=True)
    return result


async def main() -> None:
    try:
        print(json.dumps(await run(parser().parse_args()), sort_keys=True))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
