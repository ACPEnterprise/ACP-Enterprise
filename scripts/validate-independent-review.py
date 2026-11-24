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
from release_evidence_contract import EvidenceError, sha256, validate_evidence_binding


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
    evidence_manifest = getattr(args, "evidence_manifest", None)
    if evidence_manifest is not None:
        tooling_sha = getattr(args, "tooling_sha", None)
        if not tooling_sha:
            raise EvidenceError("tooling SHA is required for evidence binding")
        validate_evidence_binding(
            evidence_manifest,
            args.smoke_readiness,
            candidate_sha=args.candidate_sha,
            tooling_sha=tooling_sha,
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
        if review.get("evidence_archive_sha256") != sha256(evidence_manifest):
            raise EvidenceError("review evidence digest does not match manifest")
    return {
        "contract": REVIEW_CONTRACT,
        "review_id": str(review["review_id"]),
        "review_receipt_sha256": review_digest,
        "candidate_sha": args.candidate_sha,
        "migration_head": args.migration_head,
        "scope": SCOPE,
        "reviewed_at": str(review["reviewed_at"]),
        **(
            {"tooling_sha": str(args.tooling_sha)}
            if evidence_manifest is not None
            else {}
        ),
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
    result.add_argument("--tooling-sha")
    result.add_argument("--evidence-manifest", type=Path)
    result.add_argument("--smoke-readiness", type=Path)
    result.add_argument("--company-id")
    result.add_argument("--branch-id")
    result.add_argument("--denied-company-id")
    result.add_argument("--provisioner-path", type=Path)
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(validate_independent_review_receipt(parser().parse_args())))
    except (AuthorityError, EvidenceError) as error:
        print(f"BLOCKED: {error}")
        raise SystemExit(2)
