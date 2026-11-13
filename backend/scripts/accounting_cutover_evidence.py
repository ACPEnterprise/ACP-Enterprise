"""Capture and seal Accounting cutover evidence without accounting mutation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.accounting.cutover_evidence import capture_source_baseline, seal_cutover_package


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    baseline = subparsers.add_parser("baseline")
    baseline.add_argument("--source-root", required=True, type=Path)
    baseline.add_argument("--output-root", required=True, type=Path)
    baseline.add_argument("--authority-id", required=True)
    baseline.add_argument("--cutoff", required=True)
    package = subparsers.add_parser("seal")
    package.add_argument("--workbook", required=True, type=Path)
    package.add_argument("--output-root", required=True, type=Path)
    package.add_argument("--sanitized-root", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "baseline":
        result = capture_source_baseline(
            source_root=args.source_root,
            output_root=args.output_root,
            authority_id=args.authority_id,
            cutoff=args.cutoff,
        )
        print(json.dumps({"baseline_digest": result["baseline_digest"], "file_count": len(result["files"]), "state": "IMMUTABLE_BASELINE_CAPTURED"}, sort_keys=True))
        return 0
    workbook = json.loads(args.workbook.read_bytes())
    if not isinstance(workbook, dict):
        raise SystemExit("workbook must be a JSON object")
    result = seal_cutover_package(
        workbook=workbook,
        output_root=args.output_root,
        sanitized_root=args.sanitized_root,
    )
    print(json.dumps({"package_digest": result["package_digest"], "file_count": result["file_count"], "state": "EVIDENCE_PACKAGE_SEALED"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
