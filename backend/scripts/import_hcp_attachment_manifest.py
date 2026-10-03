"""Import a sealed HCP attachment manifest into immutable local custody."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from app.operational_migration.hcp_supplemental_evidence import (
    attachment_retry_queue,
    build_attachment_authority,
    import_attachment_manifest,
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise TypeError("attachment manifest must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--custody-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--retry-output", type=Path, required=True)
    args = parser.parse_args()
    source = _load(args.input)
    records, import_counts = import_attachment_manifest(
        source_root=args.source_root,
        custody_root=args.custody_root,
        company_id=source["company_id"],
        records=source["records"],
    )
    packet = build_attachment_authority(
        company_id=source["company_id"],
        acquired_at=source["acquired_at"],
        inventory_complete=source.get("inventory_complete") is True,
        records=records,
        known_parents={
            key: set(value)
            for key, value in source.get("known_parents", {}).items()
        },
    )
    retry = attachment_retry_queue(packet)
    for path, value in (
        (args.output, packet),
        (args.retry_output, {"contract": "hcp-attachment-retry/v1", "records": retry}),
    ):
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode())
        os.chmod(path, 0o600)
    print(
        json.dumps(
            {
                "packet_digest": packet["digest"],
                "import_counts": import_counts,
                "retry_count": len(retry),
            }
        )
    )
    return 0 if not retry else 2


if __name__ == "__main__":
    raise SystemExit(main())
