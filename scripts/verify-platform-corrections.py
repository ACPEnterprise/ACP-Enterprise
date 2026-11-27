"""Verify accepted Platform corrections in an exact candidate Git tree."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

CONTRACT = "twelvehats-platform-correction-preservation/v1"
NODE_VERSION = "24.22.3"
SHA40 = re.compile(r"[0-9a-f]{40}")
REQUIRED_PATHS = (
    ".github/workflows/development-candidate-preflight.yml",
    ".github/workflows/immutable-ci-artifacts.yml",
    ".node-version",
    "backend/development_factory/ci_artifacts.py",
    "backend/tests/development_factory/test_ci_artifacts.py",
    "backend/tests/release/test_backend_test_qualification_harness.py",
    "backend/tests/release/test_preview_release_authorization.py",
    "frontend/Dockerfile",
    "frontend/Dockerfile.mission-control",
    "frontend/package-lock.json",
    "frontend/package.json",
    "frontend/src/components/customers/CustomerManagement.test.tsx",
    "frontend/src/routes/SchedulingRoute.test.tsx",
    "mobile/package-lock.json",
    "mobile/package.json",
    "scripts/qualify-backend-tests",
    "scripts/verify-development-candidate.py",
)


class PreservationError(ValueError):
    """A candidate omitted or changed an accepted Platform correction."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PreservationError(message)


def _load_json(files: Mapping[str, str], path: str) -> dict[str, object]:
    try:
        value = json.loads(files[path])
    except (KeyError, json.JSONDecodeError) as exc:
        raise PreservationError(f"{path}: invalid or missing JSON") from exc
    _require(isinstance(value, dict), f"{path}: top-level value must be an object")
    return value


def evaluate_candidate_files(files: Mapping[str, str]) -> dict[str, str]:
    """Evaluate semantic invariants without depending on a working tree."""

    missing = sorted(set(REQUIRED_PATHS) - set(files))
    if missing:
        raise PreservationError(f"candidate is missing required path: {missing[0]}")

    workflow = files[".github/workflows/immutable-ci-artifacts.yml"]
    action_refs = re.findall(r"uses: [^@\s]+@([^\s]+)", workflow)
    _require(
        action_refs and all(SHA40.fullmatch(ref) for ref in action_refs),
        "CI actions must remain pinned to immutable SHAs",
    )
    _require(
        'qualification_python="$(command -v python)"' in workflow,
        "CI must resolve the qualification Python path",
    )
    _require(
        'scripts/qualify-backend-tests --python "$QUALIFICATION_PYTHON"' in workflow,
        "CI must pass the absolute qualification Python path",
    )
    _require(
        "--python python" not in workflow,
        "CI reintroduced the non-path Python argument",
    )
    _require(
        "node-version-file: .node-version" in workflow,
        "CI must derive Node.js from .node-version",
    )
    _require(
        '"$QUALIFICATION_PYTHON" scripts/verify-platform-corrections.py' in workflow,
        "CI must execute the Platform correction preservation check",
    )
    _require(
        '"$QUALIFICATION_PYTHON" scripts/verify-development-candidate.py' in workflow,
        "full CI must verify qualified development baseline ancestry",
    )
    preflight = files[".github/workflows/development-candidate-preflight.yml"]
    _require(
        "- work/**" in preflight
        and "scripts/verify-development-candidate.py" in preflight
        and "scripts/verify-platform-corrections.py" in preflight,
        "work branches must run synchronization and preservation preflight",
    )
    _require(
        "- work/**" not in workflow,
        "work branches must not start duplicate full qualification runs",
    )

    _require(
        files[".node-version"].strip() == NODE_VERSION,
        f"Node.js must remain pinned to {NODE_VERSION}",
    )
    for package in ("frontend", "mobile"):
        package_json = _load_json(files, f"{package}/package.json")
        package_lock = _load_json(files, f"{package}/package-lock.json")
        engines = package_json.get("engines")
        lock_root = (
            package_lock.get("packages", {}).get("")
            if isinstance(package_lock.get("packages"), dict)
            else None
        )
        _require(
            isinstance(engines, dict) and engines.get("node") == NODE_VERSION,
            f"{package} package must pin Node.js {NODE_VERSION}",
        )
        _require(
            isinstance(lock_root, dict)
            and isinstance(lock_root.get("engines"), dict)
            and lock_root["engines"].get("node") == NODE_VERSION,
            f"{package} lockfile must pin Node.js {NODE_VERSION}",
        )
    for path in ("frontend/Dockerfile", "frontend/Dockerfile.mission-control"):
        _require(
            f"FROM node:{NODE_VERSION}-alpine@sha256:" in files[path],
            f"{path} must use the supported immutable Node.js runtime",
        )
    artifact_source = files["backend/development_factory/ci_artifacts.py"]
    _require(
        artifact_source.count('".node-version"') >= 3,
        "immutable artifact provenance must include .node-version",
    )

    redis_harness = files["scripts/qualify-backend-tests"]
    _require(
        "qualification_uid=$(id -u)" in redis_harness
        and "qualification_gid=$(id -g)" in redis_harness,
        "Redis qualification must derive the runner UID and GID",
    )
    _require(
        '--user "$qualification_uid:$qualification_gid"' in redis_harness,
        "Redis qualification must preserve mounted secret custody",
    )
    redis_regression = files[
        "backend/tests/release/test_backend_test_qualification_harness.py"
    ]
    _require(
        'f"--user {os.getuid()}:{os.getgid()}"' in redis_regression,
        "Redis custody correction lacks permanent regression coverage",
    )

    scheduling_test = files["frontend/src/routes/SchedulingRoute.test.tsx"]
    _require(
        'new Date("2026-08-13T14:30:00Z")' in scheduling_test,
        "Scheduling current-time proof must use an absolute UTC instant",
    )
    _require(
        "new Date(2026, 7, 13, 10, 30)" not in scheduling_test,
        "Scheduling current-time proof reintroduced a host-timezone dependency",
    )

    release_clock_test = files[
        "backend/tests/release/test_preview_release_authorization.py"
    ]
    _require(
        'monkeypatch.setattr(validator, "utc_now", lambda: NOW)' in release_clock_test,
        "release review validation must isolate its freshness clock",
    )

    customer_test = files[
        "frontend/src/components/customers/CustomerManagement.test.tsx"
    ]
    _require(
        'vi.mock("./HistoricalCustomerSearch"' in customer_test
        and "HistoricalCustomerSearch: () => null" in customer_test,
        "Customer roster tests must isolate HistoricalCustomerSearch",
    )

    ci_regression = files["backend/tests/development_factory/test_ci_artifacts.py"]
    _require(
        'assert "--python python" not in workflow' in ci_regression,
        "absolute Python correction lacks permanent regression coverage",
    )
    _require(
        'assert version == "24.22.3"' in ci_regression,
        "Node.js runtime correction lacks permanent regression coverage",
    )

    return {
        "ci_runtime": "PASS",
        "node_runtime": "PASS",
        "redis_secret_custody": "PASS",
        "scheduling_timezone": "PASS",
        "release_clock_isolation": "PASS",
        "customer_test_isolation": "PASS",
    }


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise PreservationError("candidate Git object is unavailable")
    return completed.stdout


def _committed_file(repository: Path, candidate_sha: str, path: str) -> str:
    completed = subprocess.run(
        ("git", "show", f"{candidate_sha}:{path}"),
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise PreservationError(f"candidate is missing required path: {path}")
    return completed.stdout


def verify_repository(repository: Path, candidate_sha: str) -> dict[str, object]:
    repository = repository.resolve()
    _require(
        SHA40.fullmatch(candidate_sha) is not None,
        "candidate SHA must be a full lowercase Git SHA",
    )
    resolved = _git(repository, "rev-parse", "--verify", f"{candidate_sha}^{{commit}}")
    _require(resolved.strip() == candidate_sha, "candidate SHA did not resolve exactly")
    files = {
        path: _committed_file(repository, candidate_sha, path)
        for path in REQUIRED_PATHS
    }
    checks = evaluate_candidate_files(files)
    return {
        "contract": CONTRACT,
        "candidate_sha": candidate_sha,
        "status": "PASS",
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--candidate-sha", required=True)
    arguments = parser.parse_args()
    try:
        result = verify_repository(arguments.repository, arguments.candidate_sha)
    except PreservationError as exc:
        print(f"platform correction preservation: FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
