"""Run a qualified HCP runtime packet against the database selected by env."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.database.session import AsyncSessionFactory
from app.operational_migration.hcp_november_bundle import NovemberQualificationAuthority
from app.operational_migration.hcp_november_executor import run_november_execution


async def main() -> None:
    authority = NovemberQualificationAuthority.load(
        Path(
            "/var/lib/acp-qbo-production-evidence/hcp-runtime-2307/quarantine/runtime-binding-quarantined-authority.json"
        )
    )
    result = await run_november_execution(authority, factory=AsyncSessionFactory)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
