from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
from development_factory import ci_artifacts


def git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def repository(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repository"
    root.mkdir(mode=0o700)
    git(root, "init", "-q")
    git(root, "config", "user.name", "CI Artifact Test")
    git(root, "config", "user.email", "ci-artifact-test@example.invalid")
    directories = {
        "backend/alembic",
        "backend/app",
        "backend/development_factory",
        "backend/scripts",
        "development-factory",
        "frontend/public",
        "frontend/src",
        "mobile/src",
        "scripts",
    }
    for directory in directories:
        path = root / directory / "content.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"qualified {directory}\n", encoding="utf-8")
    files = (
        set(ci_artifacts.DEPENDENCY_PATHS)
        | set(ci_artifacts.CONFIGURATION_PATHS)
        | {path for path in ci_artifacts.APPLICATION_PATHS if path not in directories}
    )
    for filename in files:
        path = root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"qualified {filename}\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "candidate")
    return root, git(root, "rev-parse", "HEAD")


def build(tmp_path: Path) -> tuple[Path, str, Path, dict[str, object]]:
    root, candidate = repository(tmp_path)
    output = tmp_path / "artifacts"
    output.mkdir(mode=0o700)
    manifest = ci_artifacts.build_ci_artifacts(
        repository=root,
        output_directory=output,
        candidate_sha=candidate,
    )
    return root, candidate, output, manifest


def test_build_and_independently_rebuild_artifacts(tmp_path: Path) -> None:
    root, candidate, output, manifest = build(tmp_path)

    result = ci_artifacts.verify_ci_artifacts(
        repository=root,
        manifest_path=output / "ci-artifact-manifest.json",
        candidate_sha=candidate,
    )

    assert result["reproducible"] is True
    assert result["artifacts_verified"] == 2
    assert manifest["deployment_authorized"] is False
    for filename in ("application.tar.gz", "tooling.tar.gz"):
        assert (output / filename).stat().st_mode & 0o777 == 0o400


def test_same_commit_builds_identical_artifact_bytes(tmp_path: Path) -> None:
    root, candidate = repository(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir(mode=0o700)
    second.mkdir(mode=0o700)

    ci_artifacts.build_ci_artifacts(
        repository=root, output_directory=first, candidate_sha=candidate
    )
    ci_artifacts.build_ci_artifacts(
        repository=root, output_directory=second, candidate_sha=candidate
    )

    for filename in (
        "application.tar.gz",
        "tooling.tar.gz",
        "ci-artifact-manifest.json",
    ):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()


def test_artifact_tampering_is_rejected(tmp_path: Path) -> None:
    root, candidate, output, _manifest = build(tmp_path)
    artifact = output / "application.tar.gz"
    artifact.chmod(0o600)
    artifact.write_bytes(artifact.read_bytes() + b"tampered")
    artifact.chmod(0o400)

    with pytest.raises(ci_artifacts.CIArtifactError, match="size does not match"):
        ci_artifacts.verify_ci_artifacts(
            repository=root,
            manifest_path=output / "ci-artifact-manifest.json",
            candidate_sha=candidate,
        )


def test_dependency_identity_mismatch_is_rejected(tmp_path: Path) -> None:
    root, candidate, output, _manifest = build(tmp_path)
    manifest_path = output / "ci-artifact-manifest.json"
    manifest_path.chmod(0o600)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["dependency_sha256"]["backend/requirements.txt"] = "0" * 64
    unsigned = {
        key: value for key, value in payload.items() if key != "manifest_sha256"
    }
    payload["manifest_sha256"] = ci_artifacts.digest_bytes(
        ci_artifacts.canonical(unsigned)
    )
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    manifest_path.chmod(0o400)

    with pytest.raises(ci_artifacts.CIArtifactError, match="dependency identity"):
        ci_artifacts.verify_ci_artifacts(
            repository=root,
            manifest_path=manifest_path,
            candidate_sha=candidate,
        )


def test_candidate_binding_and_immutable_outputs_fail_closed(tmp_path: Path) -> None:
    root, candidate, output, _manifest = build(tmp_path)

    with pytest.raises(ci_artifacts.CIArtifactError, match="full lowercase"):
        ci_artifacts.verify_ci_artifacts(
            repository=root,
            manifest_path=output / "ci-artifact-manifest.json",
            candidate_sha="HEAD",
        )
    with pytest.raises(ci_artifacts.CIArtifactError, match="overwrite"):
        ci_artifacts.build_ci_artifacts(
            repository=root,
            output_directory=output,
            candidate_sha=candidate,
        )


def test_dirty_worktree_cannot_change_commit_derived_artifacts(tmp_path: Path) -> None:
    root, candidate = repository(tmp_path)
    (root / "backend/app/content.txt").write_text(
        "uncommitted mutation\n", encoding="utf-8"
    )
    output = tmp_path / "artifacts"
    output.mkdir(mode=0o700)

    manifest = ci_artifacts.build_ci_artifacts(
        repository=root,
        output_directory=output,
        candidate_sha=candidate,
    )

    assert manifest["candidate_sha"] == candidate
    assert ci_artifacts.verify_ci_artifacts(
        repository=root,
        manifest_path=output / "ci-artifact-manifest.json",
        candidate_sha=candidate,
    )["reproducible"]


def test_ci_workflow_is_read_only_pinned_and_verifies_before_upload() -> None:
    repository_root = Path(__file__).parents[3]
    workflow = (
        repository_root / ".github/workflows/immutable-ci-artifacts.yml"
    ).read_text(encoding="utf-8")
    action_refs = re.findall(r"uses: [^@\s]+@([^\s]+)", workflow)

    assert action_refs == [
        "3d3c42e5aac5ba805825da76410c181273ba90b1",
        "6d4fd22b20465ccc0f7354476588e8df7c9ca0e0",
        "949feb2413d6458794dcd2491c4babbbce0c15c1",
        "cf430e030ddbb5b0abf93d22962f4752f3646cd9",
    ]
    assert all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs)
    assert "contents: read" in workflow
    assert "persist-credentials: false" in workflow
    assert "release-secret-custody-check.py" in workflow
    assert "node-version-file: .node-version" in workflow
    assert 'scripts/qualify-backend-tests --python "$QUALIFICATION_PYTHON"' in workflow
    assert "--python python" not in workflow
    assert 'qualification_python="$(command -v python)"' in workflow
    assert "using Node.js 20" not in workflow
    assert '"$QUALIFICATION_PYTHON" scripts/verify-platform-corrections.py' in workflow
    assert workflow.index("scripts/ci-artifacts verify") < workflow.index(
        "actions/upload-artifact@"
    )
    assert "compression-level: 0" in workflow
    assert "deployment" not in workflow.lower()


def test_node_runtime_is_consistent_across_ci_packages_and_artifacts() -> None:
    repository_root = Path(__file__).parents[3]
    version = (repository_root / ".node-version").read_text(encoding="utf-8").strip()
    assert version == "24.22.3"
    for package in ("frontend", "mobile"):
        package_json = json.loads(
            (repository_root / package / "package.json").read_text(encoding="utf-8")
        )
        package_lock = json.loads(
            (repository_root / package / "package-lock.json").read_text(
                encoding="utf-8"
            )
        )
        assert package_json["engines"]["node"] == version
        assert package_lock["packages"][""]["engines"]["node"] == version
    dockerfile = (repository_root / "frontend/Dockerfile").read_text(encoding="utf-8")
    assert f"FROM node:{version}-alpine@sha256:" in dockerfile
    assert ".node-version" in ci_artifacts.DEPENDENCY_PATHS
    assert ".node-version" in ci_artifacts.CONFIGURATION_PATHS
    assert ".node-version" in ci_artifacts.APPLICATION_PATHS
