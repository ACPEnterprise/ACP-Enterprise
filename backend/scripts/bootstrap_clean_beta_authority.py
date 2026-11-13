"""Provision the exact HCP Preview authority chain on clean Beta only."""

from __future__ import annotations

import argparse
import asyncio
import json

from app.core.config import settings
from app.database.session import AsyncSessionFactory, engine
from app.operational_migration.clean_beta_authority import (
    reconcile_clean_beta_authority,
)
from app.platform.auth.passwords import PasswordService


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", choices=("preview",), required=True)
    args = parser.parse_args()
    if args.environment != "preview" or settings.environment not in {"preview", "test"}:
        raise SystemExit("clean Beta authority requires Preview environment")
    async with AsyncSessionFactory() as session:
        result = await reconcile_clean_beta_authority(
            session,
            password_service=PasswordService(settings),
        )
    await engine.dispose()
    print(json.dumps({
        "status": "PASS",
        "action": result.action,
        "company_id": str(result.company_id),
        "branch_id": str(result.branch_id),
        "actor_id": str(result.actor_id),
        "membership_id": str(result.membership_id),
        "role_id": str(result.role_id),
        "rows_created": result.rows_created,
        "rows_reused": result.rows_reused,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
