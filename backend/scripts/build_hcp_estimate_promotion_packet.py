"""Build a private, non-mutating HCP Estimate promotion decision packet."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.operational_migration.hcp_estimate_promotion import (
    EstimateLineEvidence,
    EstimateOptionEvidence,
    EstimateSourceEvidence,
    ExactParentBindings,
    NativeEstimateEvidence,
    build_estimate_promotion_plan,
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise TypeError(f"{path.name} must contain an object")
    return value


def _source(row: dict[str, Any]) -> EstimateSourceEvidence:
    options = tuple(
        EstimateOptionEvidence(
            source_id=option["source_id"],
            label=option["label"],
            status=option.get("status"),
            total_amount=option.get("total_amount"),
            lines=tuple(EstimateLineEvidence(**line) for line in option["lines"]),
        )
        for option in row["options"]
    )
    return EstimateSourceEvidence(**(row | {"options": options}))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cutoff", required=True)
    parser.add_argument("--acquired-at", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_packet = _load(args.source)
    binding_packet = _load(args.bindings)
    native_packet = _load(args.native)
    source = tuple(_source(row) for row in source_packet["records"])
    bindings = {
        row["source_id"]: ExactParentBindings(
            tuple(row["customer_ids"]),
            tuple(row.get("location_ids", [])),
            tuple(row.get("job_ids", [])),
            tuple(tuple(pair) for pair in row.get("line_snapshot_ids", [])),
        )
        for row in binding_packet["records"]
    }
    native = {
        row["source_id"]: NativeEstimateEvidence(
            **{key: value for key, value in row.items() if key != "source_id"}
        )
        for row in native_packet["records"]
    }
    plan = build_estimate_promotion_plan(
        cutoff=args.cutoff,
        acquired_at=args.acquired_at,
        source=source,
        bindings=bindings,
        native=native,
    )
    value = asdict(plan)
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2, default=str) + "\n")
    os.chmod(args.output, 0o600)
    print(json.dumps({"digest": plan.digest, "counts": plan.counts}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
