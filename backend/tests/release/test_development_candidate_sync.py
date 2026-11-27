from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "scripts/verify-development-candidate.py"


def module():
    spec = importlib.util.spec_from_file_location("development_candidate", SCRIPT)
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def commit(repository: Path, message: str) -> str:
    git(repository, "add", ".")
    git(repository, "commit", "-q", "-m", message)
    return git(repository, "rev-parse", "HEAD")


def test_current_candidate_manifest_is_bound_to_qualified_hosted_run() -> None:
    loaded = module()
    payload = json.loads((ROOT / loaded.MANIFEST_PATH).read_text(encoding="utf-8"))

    assert (
        loaded.validate_manifest(payload)["baseline_sha"]
        == loaded.EXPECTED_BASELINE_SHA
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("baseline_sha", "0" * 40, "baseline SHA"),
        ("baseline_ref", "origin/obsolete", "baseline ref"),
        ("preservation_verifier", "disabled", "not mandatory"),
    ),
)
def test_manifest_tampering_fails_closed(field: str, value: str, message: str) -> None:
    loaded = module()
    payload = json.loads((ROOT / loaded.MANIFEST_PATH).read_text(encoding="utf-8"))
    payload[field] = value

    with pytest.raises(loaded.CandidateError, match=message):
        loaded.validate_manifest(payload)


def test_candidate_must_descend_from_exact_qualified_baseline(tmp_path: Path) -> None:
    loaded = module()
    repository = tmp_path / "repository"
    repository.mkdir()
    git(repository, "init", "-q")
    git(repository, "config", "user.name", "Candidate Test")
    git(repository, "config", "user.email", "candidate@example.invalid")
    (repository / "seed").write_text("baseline\n", encoding="utf-8")
    baseline = commit(repository, "baseline")

    loaded.EXPECTED_BASELINE_SHA = baseline
    payload = {
        "contract": loaded.CONTRACT,
        "baseline_ref": loaded.EXPECTED_BASELINE_REF,
        "baseline_sha": baseline,
        "preservation_verifier": "scripts/verify-platform-corrections.py",
        "qualification": {"conclusion": "success", "run_id": loaded.EXPECTED_RUN_ID},
    }
    paths = {
        loaded.MANIFEST_PATH: json.dumps(payload),
        ".github/workflows/immutable-ci-artifacts.yml": "scripts/verify-development-candidate.py\n",
        ".github/workflows/development-candidate-preflight.yml": (
            "scripts/verify-development-candidate.py\n"
            "scripts/verify-platform-corrections.py\n"
        ),
    }
    for relative, content in paths.items():
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    descendant = commit(repository, "descendant")

    result = loaded.verify_repository(repository, descendant)
    assert result["status"] == "PASS"
    assert result["full_qualification_required"] is True

    git(repository, "checkout", "-q", "--orphan", "divergent")
    for path in repository.iterdir():
        if path.name != ".git" and path.is_file():
            path.unlink()
    (repository / "divergent").write_text("not based on baseline\n", encoding="utf-8")
    divergent = commit(repository, "divergent")

    with pytest.raises(loaded.CandidateError, match="does not descend"):
        loaded.verify_repository(repository, divergent)
