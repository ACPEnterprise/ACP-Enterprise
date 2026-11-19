"""Verify a sealed Customer acceptance cohort against a live database, read-only."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from uuid import UUID

from app import main as application_model_registry  # noqa: F401
from app.customer_migration.live_acceptance_cohort import (
    load_private_acceptance_cohort,
    verify_live_acceptance_cohort,
)
from app.database.session import AsyncSessionFactory


def _write_restricted(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as target:
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    os.chmod(path, 0o600)


async def verify(args: argparse.Namespace) -> int:
    artifact = load_private_acceptance_cohort(
        args.artifact,
        expected_source_sha256=args.expected_source_sha256,
        expected_migration_release_sha=args.expected_migration_release_sha,
    )
    async with AsyncSessionFactory() as session:
        report = await verify_live_acceptance_cohort(
            session,
            artifact=artifact,
            company_id=args.company_id,
            branch_id=args.branch_id,
        )
    payload = (
        json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    _write_restricted(args.output, payload)
    return 0 if report["result"] == "PASS" else 1


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--artifact", type=Path, required=True)
    result.add_argument("--expected-source-sha256", required=True)
    result.add_argument("--expected-migration-release-sha", required=True)
    result.add_argument("--company-id", type=UUID, required=True)
    result.add_argument("--branch-id", type=UUID, required=True)
    result.add_argument("--output", type=Path, required=True)
    return result


def main() -> None:
    raise SystemExit(asyncio.run(verify(parser().parse_args())))


if __name__ == "__main__":
    main()
