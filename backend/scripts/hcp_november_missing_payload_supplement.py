"""Fetch only the exact missing November HCP payload identities via GET."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.operational_migration.hcp_november_supplemental import build_supplemental
from app.operational_migration.hcp_readonly_extractor import (
    HcpReadOnlyConfig,
    HcpReadOnlyTransport,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--secret-file", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--inventory-sha256", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--source-packet-sha256", required=True)
    parser.add_argument("--source-canonical-digest", required=True)
    args = parser.parse_args()
    config = HcpReadOnlyConfig.load(args.secret_file)
    manifest = build_supplemental(
        transport=HcpReadOnlyTransport(config),
        inventory_path=args.inventory,
        inventory_sha256=args.inventory_sha256,
        output_root=args.output_root,
        source_packet_sha256=args.source_packet_sha256,
        source_canonical_digest=args.source_canonical_digest,
    )
    print(
        json.dumps(
            {
                "contract": manifest["contract"],
                "count": manifest["inventory_count"],
                "digest": manifest["digest"],
                "http_method_allowlist": manifest["http_method_allowlist"],
                "status": manifest["status"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
