from __future__ import annotations

import argparse
import asyncio
import json
from uuid import UUID

from app.database.session import AsyncSessionFactory, engine
from app.platform.factory_control.authority import (
    grant_factory_controller_authority,
    grant_platform_factory_reader,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Governed Factory Control activation")
    subcommands = result.add_subparsers(dest="command", required=True)
    reader = subcommands.add_parser("grant-reader")
    reader.add_argument("--user-id", type=UUID, required=True)
    reader.add_argument("--exact-display-name", required=True)
    reader.add_argument("--granted-by-user-id", type=UUID, required=True)
    reader.add_argument("--reason", required=True)
    controller = subcommands.add_parser("grant-controller")
    controller.add_argument("--worker-identity-id", type=UUID, required=True)
    controller.add_argument("--granted-by-user-id", type=UUID, required=True)
    controller.add_argument("--reason", required=True)
    return result


async def run(arguments: argparse.Namespace) -> None:
    async with AsyncSessionFactory() as session, session.begin():
        if arguments.command == "grant-reader":
            grant, created = await grant_platform_factory_reader(
                session,
                user_id=arguments.user_id,
                exact_display_name=arguments.exact_display_name,
                granted_by_user_id=arguments.granted_by_user_id,
                reason=arguments.reason,
            )
            result = {
                "principal_type": grant.principal_type,
                "principal_id": str(grant.user_id),
                "permission": grant.permission_code,
                "created": created,
            }
        else:
            grants = await grant_factory_controller_authority(
                session,
                worker_identity_id=arguments.worker_identity_id,
                granted_by_user_id=arguments.granted_by_user_id,
                reason=arguments.reason,
            )
            result = {
                "principal_type": "WORKER_IDENTITY",
                "principal_id": str(arguments.worker_identity_id),
                "permissions": [grant.permission_code for grant, _ in grants],
                "created": [created for _, created in grants],
            }
    print(json.dumps(result, sort_keys=True))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run(parser().parse_args()))
