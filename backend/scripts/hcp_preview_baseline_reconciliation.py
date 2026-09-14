"""Seal or byte-verify the Preview-baseline reconciled HCP overlay."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.operational_migration.hcp_preview_baseline_reconciliation import (
    build_successor,
    canonical_bytes,
    verify_successor,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    for argument in (
        "overlay", "hold", "cohort", "runtime", "baseline", "classifier",
        "successor-manifest", "refresh-root", "schedule-root", "output",
    ):
        parser.add_argument(f"--{argument}", required=True, type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    value = build_successor(
        overlay_path=args.overlay,
        hold_path=args.hold,
        cohort_path=args.cohort,
        runtime_path=args.runtime,
        baseline_path=args.baseline,
        classifier_path=args.classifier,
        successor_manifest_path=args.successor_manifest,
        refresh_root=args.refresh_root,
        schedule_root=args.schedule_root,
    )
    if args.verify:
        existing = json.loads(args.output.read_bytes())
        verify_successor(existing)
        if canonical_bytes(existing) != canonical_bytes(value):
            raise ValueError("successor overlay does not reproduce byte-for-byte")
        print(json.dumps({"status": "verified", "digest": existing["digest"]}))
        return 0
    args.output.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    args.output.parent.chmod(0o700)
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as destination:
        destination.write(canonical_bytes(value))
    args.output.chmod(0o600)
    print(json.dumps({"status": "sealed", "digest": value["digest"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
