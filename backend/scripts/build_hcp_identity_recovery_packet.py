#!/usr/bin/env python3
"""Build a private candidate-bound HCP identity recovery package."""

from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path
from typing import Any

from app.operational_migration.hcp_identity_recovery_packet import (
    build_recovery_package,
)


def private_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"protected input is unavailable or a symlink: {path}")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError(f"protected input must have mode 0600: {path}")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise TypeError("protected input must contain an object")
    return value


def dependency_graph(
    packet: dict[str, Any], inventory: dict[str, Any]
) -> dict[tuple[str, str], tuple[tuple[str, str], ...]]:
    records = packet.get("records")
    if not isinstance(records, list):
        raise TypeError("source packet records must be a list")
    inventory_records = inventory.get("records")
    if not isinstance(inventory_records, list):
        raise TypeError("runtime inventory records must be a list")
    inventory_keys = {
        (str(item["domain"]), str(item["source_id"])) for item in inventory_records
    }
    packet_by_key = {
        (str(item["domain"]), str(item["source_id"])): item for item in records
    }
    if inventory_keys - set(packet_by_key):
        raise ValueError("runtime inventory contains records absent from source packet")
    result: dict[tuple[str, str], tuple[tuple[str, str], ...]] = {}
    for key in inventory_keys:
        item = packet_by_key[key]
        result[key] = tuple(
            (str(parent["domain"]), str(parent["source_id"]))
            for parent in item.get("parent_keys", [])
            if (str(parent["domain"]), str(parent["source_id"])) in inventory_keys
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-inventory", required=True, type=Path)
    parser.add_argument("--source-packet", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-bindings", type=int, default=417)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError("recovery package output already exists")
    inventory = private_json(args.runtime_inventory)
    source = private_json(args.source_packet)
    result = build_recovery_package(
        inventory,
        dependency_graph(source, inventory),
        expected_bindings=args.expected_bindings,
    )
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    os.chmod(args.output, 0o600)
    print(
        json.dumps(
            {
                "binding_count": result["binding_count"],
                "classification_counts": result["classification_counts"],
                "digest": result["digest"],
                "independent_recovery_count": result["independent_recovery_count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
