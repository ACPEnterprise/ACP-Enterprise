"""CLI for read-only SOURCE.4 authority-successor exact replay verification."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import text

from app.core.config import settings
from app.database.session import AsyncSessionFactory
from app.operational_migration.hcp_current_overlay_native import (
    HcpCurrentOverlayNativeServices,
)
from app.operational_migration.hcp_migration2_command import resolve_rehearsal_context
from app.operational_migration.hcp_source4_authority_successor_replay import (
    ReplaySuccessorAuthority,
    schema_semantic_digest,
    verify_exact_replay,
)
from app.platform.permissions.codes import MigrationPermission


async def run(path: Path):
    authority = ReplaySuccessorAuthority.load(path)
    overlay = authority.verify_files()
    repository_sha = subprocess.run(  # noqa: ASYNC221
        ("git", "rev-parse", "HEAD"), check=True, capture_output=True, text=True
    ).stdout.strip()
    if (
        repository_sha != authority.successor_protected_sha
        or os.getenv("TARGET_ENVIRONMENT") != "preview"
        or os.getenv("PREVIEW_ACCESS_ENABLED") != "true"
        or os.getenv("PRODUCTION_ACCESS_ENABLED", "false") != "false"
    ):
        raise ValueError("replay successor protected Preview boundary mismatch")
    if (
        urlparse(settings.database_url).path.removeprefix("/")
        != authority.expected_database
    ):
        raise ValueError("replay successor Preview database mismatch")
    async with AsyncSessionFactory() as session:
        context = await resolve_rehearsal_context(session, authority, credentialed=True)  # type: ignore[arg-type]
        await session.rollback()
        if (
            context.company.id != authority.company_id
            or context.active_branch is None
            or context.active_branch.id != authority.branch_id
            or not context.has_permission(MigrationPermission.EXECUTE_REHEARSAL)
        ):
            raise ValueError("replay successor scope or permission mismatch")
        heads = tuple(
            (
                await session.scalars(text("SELECT version_num FROM alembic_version"))
            ).all()
        )
        if heads != (authority.current_schema_head,):
            raise ValueError("replay successor schema is not current at one head")
        await session.rollback()
        services = HcpCurrentOverlayNativeServices(
            context=context,
            master_run_id=UUID(int=0),
            customer_run_id=UUID(int=0),
            operational_run_id=UUID(int=0),
            package_digest=authority.source4_package_digest,
            base_source_digests={
                record.key: record.source_digest for record in overlay.manifest.records
            },
            qualified_targets=overlay.qualified_targets,
        )
        await session.execute(text("SET TRANSACTION READ ONLY"))
        result = await verify_exact_replay(
            session, authority=authority, overlay=overlay, services=services
        )
        await session.rollback()
        return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority-file", required=True, type=Path)
    parser.add_argument("--verify-exact-replay", action="store_true")
    args = parser.parse_args()
    if not args.verify_exact_replay:
        raise SystemExit("explicit exact replay verification is required")
    result = asyncio.run(run(args.authority_file))
    print(
        json.dumps(
            {
                "result": result.result,
                "receipt_digest": result.receipt_digest,
                "master_run_id": str(result.master_run_id),
                "record_count": result.record_count,
                "mutation_count": result.mutation_count,
                "report_digest": result.report_digest,
                "schema_semantic_digest": schema_semantic_digest(),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
