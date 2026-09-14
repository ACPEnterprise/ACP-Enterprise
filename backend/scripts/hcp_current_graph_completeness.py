"""Generate or verify the immutable complete current SOURCE.4 graph."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.operational_migration.hcp_current_graph_completeness import (
    build_complete_graph,
    canonical_bytes,
    verify_complete_graph,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("v3", "overlay", "delta", "baseline", "classifier", "successor-manifest", "refresh-root", "schedule-root", "output"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    value = build_complete_graph(
        v3_path=args.v3,
        overlay_path=args.overlay,
        delta_path=args.delta,
        baseline_path=args.baseline,
        classifier_path=args.classifier,
        successor_manifest_path=args.successor_manifest,
        refresh_root=args.refresh_root,
        schedule_root=args.schedule_root,
    )
    if args.verify:
        observed = json.loads(args.output.read_bytes())
        verify_complete_graph(observed)
        if canonical_bytes(observed) != canonical_bytes(value):
            raise ValueError("v4 does not reproduce byte-for-byte")
        print(json.dumps({"status": "verified", "digest": observed["digest"]}))
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
