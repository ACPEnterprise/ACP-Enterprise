from __future__ import annotations

import argparse
import asyncio
import json
from uuid import UUID

from app.database.session import AsyncSessionFactory, engine
from app.platform.owner_authority import reconcile_canonical_platform_owner


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Reconcile an owner-confirmed existing authentication principal"
    )
    result.add_argument("--user-id", type=UUID, required=True)
    result.add_argument("--membership-id", type=UUID, required=True)
    result.add_argument("--company-id", type=UUID, required=True)
    result.add_argument("--expected-existing-display-name", required=True)
    result.add_argument("--canonical-first-name", required=True)
    result.add_argument("--canonical-last-name", required=True)
    result.add_argument("--reason", required=True)
    return result


async def run(arguments: argparse.Namespace) -> None:
    # Standalone administration commands do not import the FastAPI application,
    # so load its model registry before flushing cross-domain audit/authority rows.
    # The normal web process has already performed this registration.
    from app import main as _application  # noqa: F401, PLC0415

    async with AsyncSessionFactory() as session, session.begin():
        result = await reconcile_canonical_platform_owner(
            session,
            user_id=arguments.user_id,
            membership_id=arguments.membership_id,
            company_id=arguments.company_id,
            expected_existing_display_name=arguments.expected_existing_display_name,
            canonical_first_name=arguments.canonical_first_name,
            canonical_last_name=arguments.canonical_last_name,
            reason=arguments.reason,
        )
    print(
        json.dumps(
            {
                "user_id": str(result.user_id),
                "membership_id": str(result.membership_id),
                "owner_role_id": str(result.owner_role_id),
                "owner_role_created": result.owner_role_created,
                "platform_owner_created": result.platform_owner_created,
                "identity_reconciled": result.identity_reconciled,
                "authorization_version": result.authorization_version,
            },
            sort_keys=True,
        )
    )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run(parser().parse_args()))
