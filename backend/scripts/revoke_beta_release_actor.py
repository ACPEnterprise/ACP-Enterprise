"""Revoke the Beta-only Release actor and every active actor session."""

from __future__ import annotations

import argparse
import asyncio
import json
from uuid import UUID

from app import main as application_model_registry  # noqa: F401
from app.database.session import AsyncSessionFactory, engine
from app.platform.service_principals.release_actor import release_actor_service


async def run(args: argparse.Namespace) -> dict[str, object]:
    async with AsyncSessionFactory() as session, session.begin():
        principal_id = await release_actor_service.revoke(
            session, company_id=args.company_id
        )
    return {
        "principal_id": str(principal_id),
        "state": "revoked",
        "sessions_revoked": True,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--company-id", required=True, type=UUID)
    return result


async def main() -> None:
    try:
        print(json.dumps(await run(parser().parse_args()), sort_keys=True))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
