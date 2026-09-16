import argparse
import asyncio
import json
import os
from uuid import UUID

from app.database.session import AsyncSessionFactory, engine
from app.platform.permissions.role_sync import canonical_role_sync_service


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--company-id", type=UUID, required=True)
    value.add_argument("--actor-user-id", type=UUID, required=True)
    value.add_argument("--expected-role-id", type=UUID, required=True)
    value.add_argument("--role-code", required=True)
    value.add_argument("--expected-permission-digest", required=True)
    value.add_argument("--confirm-preview-repair", action="store_true")
    return value


async def run(arguments: argparse.Namespace) -> dict[str, object]:
    if (
        os.getenv("ENVIRONMENT") != "preview"
        or os.getenv("TARGET_ENVIRONMENT") != "preview"
        or not arguments.confirm_preview_repair
    ):
        raise RuntimeError("Preview role-collision repair gates were not satisfied.")
    async with AsyncSessionFactory() as session:
        result = await canonical_role_sync_service.promote_legacy_collision(
            session,
            company_id=arguments.company_id,
            actor_user_id=arguments.actor_user_id,
            expected_role_id=arguments.expected_role_id,
            role_code=arguments.role_code,
            expected_permission_digest=arguments.expected_permission_digest,
        )
    return {
        "role_id": str(result.role_id),
        "role_code": result.role_code,
        "promoted": result.promoted,
        "permissions_added": list(result.permissions_added),
        "permissions_removed": list(result.permissions_removed),
        "authorization_users_advanced": result.authorization_users_advanced,
    }


def main() -> None:
    arguments = parser().parse_args()
    try:
        print(json.dumps(asyncio.run(run(arguments)), sort_keys=True))
    finally:
        asyncio.run(engine.dispose())


if __name__ == "__main__":
    main()
