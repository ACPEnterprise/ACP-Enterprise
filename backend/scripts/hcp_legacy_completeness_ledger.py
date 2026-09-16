"""Seal the read-only legacy replacement completeness ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path

from app.operational_migration.legacy_completeness_ledger import (
    build_legacy_completeness_ledger,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--job-appointment-readiness", type=Path, required=True)
    parser.add_argument("--estimate-readiness", type=Path, required=True)
    parser.add_argument("--employee-packet", type=Path, required=True)
    parser.add_argument("--attachment-packet", type=Path, required=True)
    parser.add_argument("--qbo-controls-root", type=Path, required=True)
    parser.add_argument("--native-binding-snapshot", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ledger = build_legacy_completeness_ledger(
        source_root=args.source_root,
        job_appointment_readiness_path=args.job_appointment_readiness,
        estimate_readiness_path=args.estimate_readiness,
        employee_packet_path=args.employee_packet,
        attachment_packet_path=args.attachment_packet,
        qbo_controls_root=args.qbo_controls_root,
        native_binding_snapshot_path=args.native_binding_snapshot,
    )
    payload = json.dumps(asdict(ledger), sort_keys=True, separators=(",", ":")).encode() + b"\n"
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output.parent.chmod(0o700)
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
    args.output.chmod(0o600)
    print(json.dumps({"digest": ledger.digest, "file_sha256": hashlib.sha256(payload).hexdigest()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
