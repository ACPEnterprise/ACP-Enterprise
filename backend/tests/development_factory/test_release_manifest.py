from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from development_factory.release_manifest import (
    ARTIFACT_ROLES,
    ReleaseManifestError,
    generate_release_manifest,
    verify_release_manifest,
)

CANDIDATE = "1" * 40
TOOLING = "2" * 40
ROLLBACK = "3" * 40


def artifacts(root: Path) -> dict[str, Path]:
    values: dict[str, Path] = {}
    for role in ARTIFACT_ROLES:
        path = root / "artifacts" / f"{role}.artifact"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"qualified-{role}\n".encode())
        values[role] = path
    return values


def generate(root: Path) -> Path:
    output = root / "evidence" / "release-manifest.json"
    generate_release_manifest(
        root=root,
        output=output,
        candidate_sha=CANDIDATE,
        tooling_sha=TOOLING,
        migration_head="x3y5z7a9c1e4",
        rollback_target_sha=ROLLBACK,
        rollback_target_release="enterprise-beta-prior",
        artifacts=artifacts(root),
    )
    return output


def test_generates_immutable_manifest_and_independently_verifies(
    tmp_path: Path,
) -> None:
    output = generate(tmp_path)

    assert stat.S_IMODE(output.stat().st_mode) == 0o400
    verified = verify_release_manifest(
        output,
        root=tmp_path,
        candidate_sha=CANDIDATE,
        tooling_sha=TOOLING,
        migration_head="x3y5z7a9c1e4",
        rollback_target_sha=ROLLBACK,
        rollback_target_release="enterprise-beta-prior",
    )

    assert verified.candidate_sha == CANDIDATE
    assert tuple(item.role for item in verified.artifacts) == ARTIFACT_ROLES
    assert all(not Path(item.path).is_absolute() for item in verified.artifacts)


def test_generation_never_overwrites_existing_manifest(tmp_path: Path) -> None:
    output = generate(tmp_path)
    original = output.read_bytes()

    with pytest.raises(ReleaseManifestError, match="already exists"):
        generate_release_manifest(
            root=tmp_path,
            output=output,
            candidate_sha=CANDIDATE,
            tooling_sha=TOOLING,
            migration_head="x3y5z7a9c1e4",
            rollback_target_sha=ROLLBACK,
            rollback_target_release="enterprise-beta-prior",
            artifacts=artifacts(tmp_path),
        )

    assert output.read_bytes() == original


@pytest.mark.parametrize(
    ("binding", "value", "message"),
    [
        ("candidate_sha", "4" * 40, "candidate SHA does not match"),
        ("tooling_sha", "4" * 40, "tooling SHA does not match"),
        ("migration_head", "stale-head", "migration head does not match"),
        ("rollback_target_sha", "4" * 40, "rollback target SHA does not match"),
        (
            "rollback_target_release",
            "wrong-release",
            "rollback target release does not match",
        ),
    ],
)
def test_rejects_identity_binding_mismatches(
    tmp_path: Path,
    binding: str,
    value: str,
    message: str,
) -> None:
    output = generate(tmp_path)
    arguments = {
        "candidate_sha": CANDIDATE,
        "tooling_sha": TOOLING,
        "migration_head": "x3y5z7a9c1e4",
        "rollback_target_sha": ROLLBACK,
        "rollback_target_release": "enterprise-beta-prior",
    }
    arguments[binding] = value

    with pytest.raises(ReleaseManifestError, match=message):
        verify_release_manifest(output, root=tmp_path, **arguments)


def test_rejects_artifact_digest_mismatch(tmp_path: Path) -> None:
    output = generate(tmp_path)
    (tmp_path / "artifacts" / "backup.artifact").write_text("tampered")

    with pytest.raises(ReleaseManifestError, match="backup artifact .* does not match"):
        verify_release_manifest(output, root=tmp_path)


def test_rejects_manifest_content_tampering(tmp_path: Path) -> None:
    output = generate(tmp_path)
    output.chmod(0o600)
    payload = json.loads(output.read_text())
    payload["migration_head"] = "stale-head"
    output.write_text(json.dumps(payload))
    output.chmod(0o400)

    with pytest.raises(ReleaseManifestError, match="digest does not match"):
        verify_release_manifest(output, root=tmp_path)


def test_rejects_secret_like_paths_without_persisting_content(tmp_path: Path) -> None:
    artifact_values = artifacts(tmp_path)
    secret = "do-not-persist-this-value"
    path = tmp_path / "artifacts" / f"access-token-{secret}.txt"
    path.write_text(secret)
    artifact_values["tooling"] = path
    output = tmp_path / "release-manifest.json"

    with pytest.raises(ReleaseManifestError, match="secret-like artifact paths"):
        generate_release_manifest(
            root=tmp_path,
            output=output,
            candidate_sha=CANDIDATE,
            tooling_sha=TOOLING,
            migration_head="x3y5z7a9c1e4",
            rollback_target_sha=ROLLBACK,
            rollback_target_release="enterprise-beta-prior",
            artifacts=artifact_values,
        )

    assert not output.exists()


def test_rejects_symlink_and_path_escape(tmp_path: Path) -> None:
    artifact_values = artifacts(tmp_path)
    outside = tmp_path.parent / "outside-release-artifact"
    outside.write_text("outside")
    symlink = tmp_path / "artifacts" / "tooling-link"
    symlink.symlink_to(outside)
    artifact_values["tooling"] = symlink

    with pytest.raises(ReleaseManifestError, match="beneath the artifact root"):
        generate_release_manifest(
            root=tmp_path,
            output=tmp_path / "release-manifest.json",
            candidate_sha=CANDIDATE,
            tooling_sha=TOOLING,
            migration_head="x3y5z7a9c1e4",
            rollback_target_sha=ROLLBACK,
            rollback_target_release="enterprise-beta-prior",
            artifacts=artifact_values,
        )
