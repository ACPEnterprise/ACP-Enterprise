"""Generate or verify the sealed SOURCE.4 UPDATE cohort authority."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.operational_migration.hcp_update_cohort_authority import (
    build_authority,
    canonical_bytes,
    verify_authority,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overlay", required=True, type=Path)
    parser.add_argument("--hold-packet", required=True, type=Path)
    parser.add_argument("--source-package-manifest", required=True, type=Path)
    parser.add_argument("--predecessor-packet", required=True, type=Path)
    parser.add_argument("--refresh-root", required=True, type=Path)
    parser.add_argument("--schedule-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    expected = build_authority(
        overlay_path=args.overlay,
        hold_path=args.hold_packet,
        source_package_manifest_path=args.source_package_manifest,
        predecessor_path=args.predecessor_packet,
        refresh_root=args.refresh_root,
        schedule_root=args.schedule_root,
    )
    if args.verify:
        observed = json.loads(args.output.read_bytes())
        verify_authority(observed)
        if canonical_bytes(observed) != canonical_bytes(expected):
            raise ValueError("sealed cohort does not match accepted inputs byte-for-byte")
        print(json.dumps({"status": "verified", "digest": observed["artifact_digest"]}))
        return 0
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output.parent.chmod(0o700)
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as destination:
        destination.write(canonical_bytes(expected))
    args.output.chmod(0o600)
    print(json.dumps({"status": "sealed", "digest": expected["artifact_digest"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
