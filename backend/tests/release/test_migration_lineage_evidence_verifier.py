from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import cast

import pytest
from scripts.verify_migration_lineage import (
    MigrationLineageError,
    build_lineage,
    verify_lineage_evidence,
)


def initialize_repository(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=root,
        check=True,
    )


def write_revision(path: Path, revision: str, down_revision: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"revision = {revision!r}\n"
        f"down_revision = {down_revision!r}\n"
        "\n"
        "def upgrade():\n"
        "    pass\n",
        encoding="utf-8",
    )


def fixture_repository(tmp_path: Path) -> tuple[Path, Path]:
    initialize_repository(tmp_path)
    versions = tmp_path / "backend/alembic/versions"
    write_revision(versions / "a_root.py", "a_root", None)
    write_revision(versions / "b_head.py", "b_head", "a_root")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "migrations"], cwd=tmp_path, check=True)
    evidence = tmp_path / "lineage.json"
    evidence.write_text(
        json.dumps(build_lineage(tmp_path, versions), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "lineage.json"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "evidence"], cwd=tmp_path, check=True)
    return versions, evidence


def test_verifies_exact_head_graph_and_evidence(tmp_path: Path) -> None:
    _, evidence = fixture_repository(tmp_path)
    source_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    result = verify_lineage_evidence(
        repo_root=tmp_path,
        evidence_path=evidence,
        expected_head="b_head",
        expected_source_sha=source_sha,
    )

    assert result["revision_count"] == 2
    assert result["head"] == "b_head"
    assert result["release_ready"] is True


def test_rejects_stale_head_expectation(tmp_path: Path) -> None:
    _, evidence = fixture_repository(tmp_path)

    with pytest.raises(MigrationLineageError, match="head does not match"):
        verify_lineage_evidence(
            repo_root=tmp_path,
            evidence_path=evidence,
            expected_head="a_root",
        )


def test_rejects_stale_evidence_after_migration_change(tmp_path: Path) -> None:
    versions, evidence = fixture_repository(tmp_path)
    write_revision(versions / "c_new.py", "c_new", "b_head")

    with pytest.raises(MigrationLineageError, match="evidence is stale"):
        verify_lineage_evidence(
            repo_root=tmp_path,
            evidence_path=evidence,
            expected_head="c_new",
        )


def test_rejects_modified_applied_revision(tmp_path: Path) -> None:
    versions, evidence = fixture_repository(tmp_path)
    with (versions / "a_root.py").open("a", encoding="utf-8") as stream:
        stream.write("# changed after evidence\n")

    with pytest.raises(MigrationLineageError, match="evidence is stale"):
        verify_lineage_evidence(
            repo_root=tmp_path,
            evidence_path=evidence,
            expected_head="b_head",
        )


def test_reports_split_heads_as_not_release_ready(tmp_path: Path) -> None:
    initialize_repository(tmp_path)
    versions = tmp_path / "backend/alembic/versions"
    write_revision(versions / "a_root.py", "a_root", None)
    write_revision(versions / "b_one.py", "b_one", "a_root")
    write_revision(versions / "b_two.py", "b_two", "a_root")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "split"], cwd=tmp_path, check=True)

    result = build_lineage(tmp_path, versions)

    assert result["heads"] == ["b_one", "b_two"]
    assert result["release_ready"] is False
    assert "HEAD_COUNT_NOT_ONE" in cast(list[str], result["risks"])


def test_rejects_wrong_source_checkpoint(tmp_path: Path) -> None:
    _, evidence = fixture_repository(tmp_path)

    with pytest.raises(
        MigrationLineageError, match="expected source SHA is not an ancestor"
    ):
        verify_lineage_evidence(
            repo_root=tmp_path,
            evidence_path=evidence,
            expected_head="b_head",
            expected_source_sha="f" * 40,
        )
