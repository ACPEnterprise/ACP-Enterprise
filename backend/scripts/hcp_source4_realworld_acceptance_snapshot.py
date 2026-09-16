"""Export a transaction-read-only SOURCE.4 real-world acceptance snapshot."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from uuid import UUID

from app.database.session import AsyncSessionFactory
from app.operational_migration.hcp_realworld_acceptance_snapshot import (
    build_realworld_snapshot,
)


async def _run(args: argparse.Namespace) -> None:
    observed_at = datetime.fromisoformat(args.observed_at)
    if observed_at.tzinfo is None:
        raise SystemExit("observed-at must include a timezone")
    async with AsyncSessionFactory() as session, session.begin():
        result = await build_realworld_snapshot(
            session,
            company_id=UUID(args.company_id),
            branch_id=UUID(args.branch_id),
            observed_at=observed_at,
        )
        await session.rollback()
    content = (json.dumps(result, sort_keys=True, indent=2) + "\n").encode()
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company-id", required=True)
    parser.add_argument("--branch-id", required=True)
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    asyncio.run(_run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
