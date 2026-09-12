"""Create an immutable HCP historical tranche packet without mutation."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from app.operational_migration.hcp_historical_safe_tranche import (
    build_historical_tranche,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overlay", required=True, type=Path)
    parser.add_argument("--acceptance-plan", required=True, type=Path)
    parser.add_argument("--protected-authority", required=True)
    parser.add_argument("--native-bindings", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    packet = build_historical_tranche(
        overlay_path=args.overlay,
        acceptance_plan_path=args.acceptance_plan,
        protected_authority=args.protected_authority,
        native_bindings_path=args.native_bindings,
    )
    packet.verify()
    args.output.write_text(
        json.dumps(asdict(packet), sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "digest": packet.digest,
                "counts": packet.counts,
                "execution_allowed": packet.execution_allowed,
                "execution_blockers": packet.execution_blockers,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
