"""Build or verify the HCP current-overlay acceptance packet without mutation."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from app.operational_migration.hcp_post_admission_acceptance import (
    AcceptancePlan,
    ClassifiedRecord,
    WriteClassification,
    build_acceptance_plan,
    verify_execution,
    verify_failed_execution,
)


def _load_plan(path: Path) -> AcceptancePlan:
    value = json.loads(path.read_bytes())
    plan = AcceptancePlan(
        contract=value["contract"],
        overlay_manifest_digest=value["overlay_manifest_digest"],
        overlay_file_sha256=value["overlay_file_sha256"],
        acquired_at=value["acquired_at"],
        cutoff_date=value["cutoff_date"],
        records=tuple(
            ClassifiedRecord(
                domain=item["domain"],
                source_id=item["source_id"],
                assertion=item["assertion"],
                classification=WriteClassification(item["classification"]),
                reason=item["reason"],
                source_digest=item["source_digest"],
                parent_keys=tuple(item["parent_keys"]),
            )
            for item in value["records"]
        ),
        classification_counts=value["classification_counts"],
        assertion_counts=value["assertion_counts"],
        current_source_ids={
            key: tuple(items) for key, items in value["current_source_ids"].items()
        },
        digest=value["digest"],
    )
    plan.verify()
    return plan


def _write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--overlay", required=True, type=Path)
    build.add_argument("--refresh-root", required=True, type=Path)
    build.add_argument("--schedule-root", required=True, type=Path)
    build.add_argument("--cutoff", required=True, type=date.fromisoformat)
    build.add_argument("--output", required=True, type=Path)
    verify = commands.add_parser("verify")
    verify.add_argument("--plan", required=True, type=Path)
    verify.add_argument("--receipt", required=True, type=Path)
    verify.add_argument("--snapshot", required=True, type=Path)
    verify.add_argument("--replay-receipt", type=Path)
    verify.add_argument("--output", required=True, type=Path)
    failure = commands.add_parser("verify-failure")
    failure.add_argument("--evidence", required=True, type=Path)
    failure.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "build":
        result: object = asdict(
            build_acceptance_plan(
                overlay_path=args.overlay,
                refresh_root=args.refresh_root,
                schedule_root=args.schedule_root,
                cutoff=args.cutoff,
            )
        )
    elif args.command == "verify":
        result = verify_execution(
            _load_plan(args.plan),
            receipt=json.loads(args.receipt.read_bytes()),
            snapshot=json.loads(args.snapshot.read_bytes()),
            replay_receipt=(
                json.loads(args.replay_receipt.read_bytes())
                if args.replay_receipt
                else None
            ),
        )
    else:
        result = verify_failed_execution(json.loads(args.evidence.read_bytes()))
    _write(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
