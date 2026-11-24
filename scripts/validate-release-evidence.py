#!/usr/bin/env python3
"""Validate non-secret smoke-readiness and release-binding evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from release_evidence_contract import (
    EvidenceError,
    validate_evidence_binding,
    validate_smoke_readiness,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    smoke = subparsers.add_parser("smoke-readiness")
    add_common(smoke)
    smoke.add_argument("--artifact", type=Path, required=True)
    binding = subparsers.add_parser("evidence-binding")
    add_common(binding)
    binding.add_argument("--manifest", type=Path, required=True)
    binding.add_argument("--smoke-readiness", type=Path, required=True)
    binding.add_argument("--migration-head", required=True)
    binding.add_argument("--backup-receipt-sha256", required=True)
    binding.add_argument("--restore-receipt-sha256", required=True)
    binding.add_argument("--rollback-target-sha", required=True)
    binding.add_argument("--rollback-target-release", required=True)
    return result


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--tooling-sha", required=True)
    parser.add_argument("--company-id", required=True)
    parser.add_argument("--branch-id", required=True)
    parser.add_argument("--denied-company-id", required=True)
    parser.add_argument("--provisioner-path", type=Path, required=True)


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "smoke-readiness":
            result = validate_smoke_readiness(
                args.artifact,
                candidate_sha=args.candidate_sha,
                tooling_sha=args.tooling_sha,
                company_id=args.company_id,
                branch_id=args.branch_id,
                denied_company_id=args.denied_company_id,
                provisioner_path=args.provisioner_path,
            )
        else:
            result = validate_evidence_binding(
                args.manifest,
                args.smoke_readiness,
                candidate_sha=args.candidate_sha,
                tooling_sha=args.tooling_sha,
                migration_head=args.migration_head,
                backup_receipt_sha256=args.backup_receipt_sha256,
                restore_receipt_sha256=args.restore_receipt_sha256,
                rollback_target_sha=args.rollback_target_sha,
                rollback_target_release=args.rollback_target_release,
                company_id=args.company_id,
                branch_id=args.branch_id,
                denied_company_id=args.denied_company_id,
                provisioner_path=args.provisioner_path,
            )
    except EvidenceError as error:
        print(f"BLOCKED: {error}")
        return 2
    print(json.dumps({"result": "PASS", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
