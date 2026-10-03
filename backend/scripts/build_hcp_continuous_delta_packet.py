"""Build a private HCP continuous-delta overlay from sealed read-only evidence."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from app.operational_migration.hcp_continuous_delta import (
    NativeObservation,
    ProviderObservation,
    build_continuous_delta,
)
from app.operational_migration.hcp_current_overlay import OverlayKey
from app.operational_migration.hcp_source_completeness import (
    SourceIdentity,
    build_source_completeness,
    manifest_value,
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise TypeError(f"{path.name} must contain an object")
    return value


def build(args: argparse.Namespace):  # type: ignore[no-untyped-def]
    provider_packet = _load(args.provider_observations)
    native_packet = _load(args.native_observations)
    provider = tuple(
        ProviderObservation(
            domain=row["domain"],
            source_id=row["source_id"],
            source_digest=row["source_digest"],
            acquired_at=row["acquired_at"],
            source_updated_at=row.get("source_updated_at"),
            payload=row["payload"],
            parent_keys=tuple(OverlayKey(**parent) for parent in row["parent_keys"]),
            native_fingerprint=row.get("native_fingerprint"),
        )
        for row in provider_packet["records"]
    )
    native = {
        OverlayKey(row["domain"], row["source_id"]): NativeObservation(
            source_digest=row["source_digest"],
            source_applied_at=row["source_applied_at"],
            native_updated_at=row["native_updated_at"],
        )
        for row in native_packet["records"]
    }
    return build_continuous_delta(
        cutoff=args.cutoff,
        base_source4_digest=args.base_source4_digest,
        company_id=args.company_id,
        branch_id=args.branch_id,
        acquired_at=provider_packet["acquired_at"],
        provider=provider,
        native=native,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cutoff", required=True)
    parser.add_argument("--base-source4-digest", required=True)
    parser.add_argument("--company-id", required=True)
    parser.add_argument("--branch-id", required=True)
    parser.add_argument("--provider-observations", required=True, type=Path)
    parser.add_argument("--native-observations", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    plan = build(args)
    provider_packet = _load(args.provider_observations)
    completeness = build_source_completeness(
        cutoff=args.cutoff,
        acquired_at=provider_packet["acquired_at"],
        source=tuple(
            SourceIdentity(
                row["domain"],
                row["source_id"],
                row.get("source_version"),
                row["source_digest"],
            )
            for row in provider_packet["records"]
        ),
        delta=plan,
    )
    value = {
        "contract": plan.contract,
        "cutoff": plan.cutoff,
        "digest": plan.digest,
        "decisions": [
            {
                "domain": row.key.domain,
                "source_id": row.key.source_id,
                "disposition": row.disposition.value,
                "reason": row.reason,
                "before_digest": row.before_digest,
                "after_digest": row.after_digest,
            }
            for row in plan.decisions
        ],
        "overlay": plan.manifest.private_payload() if plan.manifest else None,
        "source_completeness": manifest_value(completeness),
    }
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2) + "\n")
    os.chmod(args.output, 0o600)
    print(
        json.dumps(
            {
                "digest": plan.digest,
                "records": len(plan.decisions),
                "overlay_records": len(plan.manifest.records)
                if plan.manifest
                else 0,
                "unexplained_provider_gaps": (
                    completeness.unexplained_provider_gaps
                ),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
