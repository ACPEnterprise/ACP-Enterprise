"""Seal HCP/QBO provider acquisition completeness without provider mutation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path

from app.operational_migration.provider_acquisition_completeness import (
    build_provider_completeness_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hcp-source-root", type=Path, required=True)
    parser.add_argument("--qbo-controls-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_provider_completeness_manifest(
        hcp_source_root=args.hcp_source_root,
        qbo_controls_root=args.qbo_controls_root,
    )
    payload = json.dumps(asdict(manifest), sort_keys=True, separators=(",", ":")).encode() + b"\n"
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output.parent.chmod(0o700)
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
    args.output.chmod(0o600)
    print(json.dumps({"digest": manifest.digest, "file_sha256": hashlib.sha256(payload).hexdigest()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
