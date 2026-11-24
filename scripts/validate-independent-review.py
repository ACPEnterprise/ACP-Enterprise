#!/usr/bin/env python3
"""Validate Stage-C review evidence without requiring signed approval."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from enterprise_release_authority import (
    REVIEW_CONTRACT,
    SCOPE,
    AuthorityError,
    utc_now,
    validate_registry,
    validate_release_binding,
    validate_review,
)


def validate_independent_review_receipt(args: argparse.Namespace) -> dict[str, str]:
    observed = utc_now()
    validate_release_binding(
        candidate_sha=args.candidate_sha,
        migration_head=args.migration_head,
        backup_receipt_sha256=args.backup_receipt_sha256,
        restore_receipt_sha256=args.restore_receipt_sha256,
        rollback_target_sha=args.rollback_target_sha,
        rollback_target_release=args.rollback_target_release,
    )
    registry, _, _ = validate_registry(
        args.registry,
        args.trusted_key,
        expected_key_id=args.key_id,
        now=observed,
    )
    review, review_digest = validate_review(
        args.review_receipt,
        registry,
        candidate_sha=args.candidate_sha,
        migration_head=args.migration_head,
        backup_receipt_sha256=args.backup_receipt_sha256,
        restore_receipt_sha256=args.restore_receipt_sha256,
        rollback_target_sha=args.rollback_target_sha,
        rollback_target_release=args.rollback_target_release,
        now=observed,
    )
    return {
        "contract": REVIEW_CONTRACT,
        "review_id": str(review["review_id"]),
        "review_receipt_sha256": review_digest,
        "candidate_sha": args.candidate_sha,
        "migration_head": args.migration_head,
        "scope": SCOPE,
        "reviewed_at": str(review["reviewed_at"]),
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--review-receipt", type=Path, required=True)
    result.add_argument("--registry", type=Path, required=True)
    result.add_argument("--trusted-key", type=Path, required=True)
    result.add_argument("--key-id", required=True)
    result.add_argument("--candidate-sha", required=True)
    result.add_argument("--migration-head", required=True)
    result.add_argument("--backup-receipt-sha256", required=True)
    result.add_argument("--restore-receipt-sha256", required=True)
    result.add_argument("--rollback-target-sha", required=True)
    result.add_argument("--rollback-target-release", required=True)
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(validate_independent_review_receipt(parser().parse_args())))
    except AuthorityError as error:
        print(f"BLOCKED: {error}")
        raise SystemExit(2)
