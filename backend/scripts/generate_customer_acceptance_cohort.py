"""Generate a restricted, non-PII Customer acceptance cohort artifact."""

from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path

from app.customer_migration.acceptance_cohort import (
    generate_customer_acceptance_cohort,
)


def _read_regular_file(path: Path) -> bytes:
    details = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(details.st_mode):
        raise ValueError("source must be a regular file")
    return path.read_bytes()


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


def generate(args: argparse.Namespace) -> int:
    artifact = generate_customer_acceptance_cohort(
        _read_regular_file(args.source),
        expected_source_sha256=args.expected_source_sha256,
        migration_release_sha=args.migration_release_sha,
        mandatory_source_ids=args.mandatory_source_id,
        limit=args.limit,
        source_system=args.source_system,
    )
    payload = (
        json.dumps(
            artifact.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    _write_restricted(args.output, payload)
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--source", type=Path, required=True)
    result.add_argument("--expected-source-sha256", required=True)
    result.add_argument("--migration-release-sha", required=True)
    result.add_argument(
        "--mandatory-source-id",
        action="append",
        required=True,
        help="Exact provider source ID; repeat for additional mandatory anchors.",
    )
    result.add_argument("--limit", type=int, default=25)
    result.add_argument("--source-system", default="housecall-pro")
    result.add_argument("--output", type=Path, required=True)
    return result


def main() -> None:
    raise SystemExit(generate(parser().parse_args()))


if __name__ == "__main__":
    main()
