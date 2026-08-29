"""Generate a restricted non-PII JOB.SOURCE.2 readiness package."""

from __future__ import annotations

import argparse
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path

from app.operational_migration.job_source_readiness import (
    inventory_artifact,
    load_json,
    make_readiness_package,
    reconcile_legacy_exports,
    service_location_dispositions,
)


def _restricted(path: Path) -> None:
    details = path.lstat()
    if (
        not stat.S_ISREG(details.st_mode)
        or path.is_symlink()
        or details.st_mode & 0o077
    ):
        raise ValueError("readiness input must be a restricted regular file")


def _timestamp(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def _inventory(path: Path, location: str):
    _restricted(path)
    return inventory_artifact(
        filename=path.name,
        secure_location=f"{location}/{path.name}",
        source=path.read_bytes(),
        extraction_timestamp=_timestamp(path),
    )


def generate(args: argparse.Namespace) -> int:
    inputs = (
        args.legacy_earlier,
        args.legacy_authoritative,
        args.current,
        *args.aggregate,
        args.phase1_review,
        args.customer_review,
        args.customer_manifest,
    )
    for path in inputs:
        _restricted(path)
    phase1 = load_json(args.phase1_review)
    inventory = [
        _inventory(args.legacy_earlier, "$DOWNLOADS"),
        _inventory(args.legacy_authoritative, "$DOWNLOADS"),
        _inventory(args.current, "$DOWNLOADS"),
        *(_inventory(path, "$DOWNLOADS") for path in args.aggregate),
    ]
    reconciliation = reconcile_legacy_exports(
        earlier=args.legacy_earlier.read_bytes(),
        later=args.legacy_authoritative.read_bytes(),
        imported_source_ids=tuple(item["source_id"] for item in phase1["jobs"]),
    )
    locations = service_location_dispositions(
        source=args.legacy_authoritative.read_bytes(),
        phase1_review=phase1,
        customer_review=load_json(args.customer_review),
        customer_manifest=load_json(args.customer_manifest),
    )
    package = make_readiness_package(
        generated_at=datetime.now(timezone.utc),
        inventory=inventory,
        reconciliation=reconciliation,
        location_dispositions=locations,
    )
    args.output.write_text(
        json.dumps(
            package.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        + "\n",
        encoding="utf-8",
    )
    os.chmod(args.output, 0o600)
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--legacy-earlier", type=Path, required=True)
    result.add_argument("--legacy-authoritative", type=Path, required=True)
    result.add_argument("--current", type=Path, required=True)
    result.add_argument("--aggregate", type=Path, action="append", default=[])
    result.add_argument("--phase1-review", type=Path, required=True)
    result.add_argument("--customer-review", type=Path, required=True)
    result.add_argument("--customer-manifest", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    return result


def main() -> None:
    raise SystemExit(generate(parser().parse_args()))


if __name__ == "__main__":
    main()
