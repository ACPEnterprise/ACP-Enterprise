#!/usr/bin/env python3
"""Fail closed when a development candidate omits the qualified common baseline."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

CONTRACT = "twelvehats-qualified-development-baseline/v1"
MANIFEST_PATH = "docs/engineering/qualified-development-baseline.v1.json"
EXPECTED_BASELINE_SHA = "6aec17be3ac0bc1316975b0222f39bc7c9903837"
EXPECTED_BASELINE_REF = "origin/handoff/friday-consolidated-20261127"
EXPECTED_RUN_ID = 46029775062
SHA40 = re.compile(r"[0-9a-f]{40}")
EVIDENCE_PREFIXES = ("docs/engineering/evidence/", "docs/quality/evidence/")


class CandidateError(ValueError):
    """The candidate is not safely synchronized with the qualified baseline."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CandidateError(message)


def _git(
    repository: Path, *arguments: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and completed.returncode:
        raise CandidateError(completed.stderr.strip() or "Git operation failed")
    return completed


def _candidate_text(repository: Path, candidate_sha: str, path: str) -> str:
    completed = _git(repository, "show", f"{candidate_sha}:{path}", check=False)
    if completed.returncode:
        raise CandidateError(f"candidate is missing required path: {path}")
    return completed.stdout


def validate_manifest(payload: Any) -> dict[str, object]:
    """Validate the immutable baseline identity and hosted qualification receipt."""

    _require(isinstance(payload, dict), "baseline manifest must be a JSON object")
    _require(payload.get("contract") == CONTRACT, "baseline contract does not match")
    _require(
        payload.get("baseline_sha") == EXPECTED_BASELINE_SHA,
        "baseline SHA does not match the qualified common baseline",
    )
    _require(
        payload.get("baseline_ref") == EXPECTED_BASELINE_REF,
        "baseline ref does not match the qualified common baseline",
    )
    _require(
        payload.get("preservation_verifier")
        == "scripts/verify-platform-corrections.py",
        "platform preservation verifier is not mandatory",
    )
    qualification = payload.get("qualification")
    _require(isinstance(qualification, dict), "qualification receipt is missing")
    _require(
        qualification.get("run_id") == EXPECTED_RUN_ID,
        "qualification run does not match the accepted hosted run",
    )
    _require(
        qualification.get("conclusion") == "success",
        "qualified baseline hosted run did not succeed",
    )
    return payload


def verify_repository(repository: Path, candidate_sha: str) -> dict[str, object]:
    """Verify exact identity, ancestry, workflow preservation, and trigger classification."""

    repository = repository.resolve()
    _require(
        SHA40.fullmatch(candidate_sha) is not None,
        "candidate SHA must be full lowercase",
    )
    resolved = _git(repository, "rev-parse", "--verify", f"{candidate_sha}^{{commit}}")
    _require(
        resolved.stdout.strip() == candidate_sha,
        "candidate SHA did not resolve exactly",
    )
    baseline = _git(
        repository, "rev-parse", "--verify", f"{EXPECTED_BASELINE_SHA}^{{commit}}"
    )
    _require(
        baseline.stdout.strip() == EXPECTED_BASELINE_SHA,
        "qualified baseline object is unavailable",
    )
    ancestry = _git(
        repository,
        "merge-base",
        "--is-ancestor",
        EXPECTED_BASELINE_SHA,
        candidate_sha,
        check=False,
    )
    _require(
        ancestry.returncode == 0, "candidate does not descend from qualified baseline"
    )

    try:
        manifest = json.loads(_candidate_text(repository, candidate_sha, MANIFEST_PATH))
    except json.JSONDecodeError as exc:
        raise CandidateError("baseline manifest is invalid JSON") from exc
    validate_manifest(manifest)

    full_workflow = _candidate_text(
        repository, candidate_sha, ".github/workflows/immutable-ci-artifacts.yml"
    )
    preflight_workflow = _candidate_text(
        repository,
        candidate_sha,
        ".github/workflows/development-candidate-preflight.yml",
    )
    _require(
        "scripts/verify-development-candidate.py" in full_workflow,
        "full qualification omits candidate synchronization verification",
    )
    _require(
        "scripts/verify-development-candidate.py" in preflight_workflow,
        "development preflight omits candidate synchronization verification",
    )
    _require(
        "scripts/verify-platform-corrections.py" in preflight_workflow,
        "development preflight omits platform preservation verification",
    )

    changed = tuple(
        line
        for line in _git(
            repository, "diff", "--name-only", EXPECTED_BASELINE_SHA, candidate_sha
        ).stdout.splitlines()
        if line
    )
    evidence_only = bool(changed) and all(
        path.startswith(EVIDENCE_PREFIXES) for path in changed
    )
    return {
        "candidate_sha": candidate_sha,
        "changed_paths": len(changed),
        "contract": CONTRACT,
        "evidence_only": evidence_only,
        "full_qualification_required": True,
        "qualified_baseline_sha": EXPECTED_BASELINE_SHA,
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--candidate-sha", required=True)
    arguments = parser.parse_args()
    try:
        result = verify_repository(arguments.repository, arguments.candidate_sha)
    except CandidateError as exc:
        print(f"development candidate synchronization: FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
