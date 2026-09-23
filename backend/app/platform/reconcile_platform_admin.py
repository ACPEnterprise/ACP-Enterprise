from __future__ import annotations

import argparse
import asyncio
import json
from uuid import UUID

from app.database.session import AsyncSessionFactory, engine
from app.platform.owner_authority import reconcile_canonical_platform_administrator


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Reconcile an exact existing platform administrator"
    )
    result.add_argument("--user-id", type=UUID, required=True)
    result.add_argument("--membership-id", type=UUID, required=True)
    result.add_argument("--company-id", type=UUID, required=True)
    result.add_argument("--exact-display-name", required=True)
    result.add_argument("--granted-by-user-id", type=UUID, required=True)
    result.add_argument("--reason", required=True)
    return result


async def run(arguments: argparse.Namespace) -> None:
    # Standalone administration commands do not import the FastAPI application,
    # so load its model registry before flushing cross-domain audit/authority rows.
    # The normal web process has already performed this registration.
    from app import main as _application  # noqa: F401

    async with AsyncSessionFactory() as session, session.begin():
        result = await reconcile_canonical_platform_administrator(
            session,
            user_id=arguments.user_id,
            membership_id=arguments.membership_id,
            company_id=arguments.company_id,
            exact_display_name=arguments.exact_display_name,
            granted_by_user_id=arguments.granted_by_user_id,
            reason=arguments.reason,
        )
    print(
        json.dumps(
            {
                "user_id": str(result.user_id),
                "membership_id": str(result.membership_id),
                "admin_role_id": str(result.admin_role_id),
                "admin_role_created": result.admin_role_created,
                "authorization_version": result.authorization_version,
            },
            sort_keys=True,
        )
    )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run(parser().parse_args()))
