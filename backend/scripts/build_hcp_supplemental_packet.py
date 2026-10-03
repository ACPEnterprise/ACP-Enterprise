"""Build deterministic HCP attachment, membership, review, or delta packets."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from app.operational_migration.hcp_supplemental_evidence import (
    build_attachment_authority,
    build_membership_authority,
    build_review_authority,
    build_supplemental_delta,
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise TypeError(f"{path.name} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("domain", choices=("attachments", "memberships", "reviews"))
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = _load(args.input)
    common = {
        "company_id": source["company_id"],
        "acquired_at": source["acquired_at"],
        "records": source["records"],
    }
    if args.domain == "attachments":
        known = {
            key: set(value)
            for key, value in source.get("known_parents", {}).items()
        }
        packet = build_attachment_authority(
            **common,
            inventory_complete=source.get("inventory_complete") is True,
            known_parents=known,
        )
    elif args.domain == "memberships":
        packet = build_membership_authority(**common)
    else:
        packet = build_review_authority(**common)
    value: dict[str, Any] = packet
    if args.prior:
        value = build_supplemental_delta(
            domain=args.domain,
            prior_packet=_load(args.prior),
            current_packet=packet,
        )
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output.write_bytes(
        (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    )
    os.chmod(args.output, 0o600)
    print(json.dumps({"domain": args.domain, "digest": value["digest"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
