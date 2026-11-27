#!/usr/bin/env python3
"""Compare sealed historical and current HCP population snapshots read-only."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from app.operational_migration.hcp_historical_population_reconciliation import (
    PopulationSnapshot,
    SnapshotRecord,
    reconcile_historical_population,
)


def _snapshot(path: Path) -> PopulationSnapshot:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"snapshot is unavailable or a symlink: {path}")
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or not isinstance(value.get("records"), list):
        raise TypeError("snapshot must be an object containing records")
    return PopulationSnapshot(
        snapshot_id=value["snapshot_id"],
        acquired_at=value["acquired_at"],
        provenance_digest=value["provenance_digest"],
        records=tuple(SnapshotRecord(**row) for row in value["records"]),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--previous", required=True, type=Path)
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError("reconciliation output already exists")
    result = reconcile_historical_population(
        _snapshot(args.previous), _snapshot(args.current)
    )
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output.write_text(json.dumps(asdict(result), indent=2, sort_keys=True) + "\n")
    os.chmod(args.output, 0o600)
    print(
        json.dumps(
            {
                "current_counts": result.current_counts,
                "digest": result.digest,
                "missing_identity_count": len(result.missing_identities),
                "previous_counts": result.previous_counts,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
