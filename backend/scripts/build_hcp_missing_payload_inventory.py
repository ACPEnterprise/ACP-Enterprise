#!/usr/bin/env python3
"""Generate a private missing-payload inventory from a sealed HCP packet."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from app.operational_migration.hcp_missing_payload_inventory import (
    build_missing_payload_inventory,
)


def _load(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("source packet is unavailable or a symlink")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise TypeError("source packet must be an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    packet = _load(args.packet)
    records = packet.get("records")
    if not isinstance(records, list):
        raise TypeError("source packet records are invalid")
    available: set[str] = set()
    for row in records:
        if not isinstance(row, dict) or not isinstance(row.get("payload_locator"), str):
            continue
        locator = row["payload_locator"]
        relative = Path(locator.split("#", 1)[0])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("payload locator escapes evidence root")
        if (args.evidence_root / relative).is_file():
            available.add(locator)

    inventory = build_missing_payload_inventory(
        packet=packet, available_payload_locators=available
    )
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError("inventory output already exists")
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(asdict(inventory), indent=2, sort_keys=True) + "\n"
    )
    os.chmod(args.output, 0o600)
    print(
        json.dumps(
            {"counts": inventory.counts, "digest": inventory.digest}, sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
