#!/usr/bin/env python3
"""Validate a v2 Beta approval against the protected authority enrollment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from enterprise_release_authority import AuthorityError, validate_approval


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--authority-registry", type=Path, required=True)
    parser.add_argument("--trusted-issuer-key", type=Path, required=True)
    parser.add_argument("--trusted-key-id", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--migration-head", required=True)
    parser.add_argument("--backup-receipt-sha256", required=True)
    parser.add_argument("--restore-receipt-sha256", required=True)
    parser.add_argument("--rollback-target-sha", required=True)
    parser.add_argument("--rollback-target-release", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = validate_approval(
            args.artifact,
            args.authority_registry,
            args.trusted_issuer_key,
            expected_key_id=args.trusted_key_id,
            candidate_sha=args.candidate_sha,
            migration_head=args.migration_head,
            backup_receipt_sha256=args.backup_receipt_sha256,
            restore_receipt_sha256=args.restore_receipt_sha256,
            rollback_target_sha=args.rollback_target_sha,
            rollback_target_release=args.rollback_target_release,
        )
    except AuthorityError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"result": "PASS", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
