from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path


def module():
    path = Path(__file__).parents[3] / "scripts/migration-lineage"
    loader = SourceFileLoader("migration_lineage", str(path))
    spec = importlib.util.spec_from_loader("migration_lineage", loader)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def migration(path: Path, revision: str, down: str | tuple[str, ...] | None) -> None:
    path.write_text(f"revision = {revision!r}\ndown_revision = {down!r}\n")


def test_linear_history_is_release_ready(tmp_path: Path) -> None:
    versions = tmp_path / "versions"
    versions.mkdir()
    migration(versions / "a.py", "a", None)
    migration(versions / "b.py", "b", "a")
    report = module().build_report(tmp_path, versions)
    assert report["heads"] == ["b"]
    assert report["release_ready"] is True
    assert report["risks"] == []
    assert report["topological_order"] == ["a", "b"]


def test_fork_is_an_explicit_release_stop(tmp_path: Path) -> None:
    versions = tmp_path / "versions"
    versions.mkdir()
    migration(versions / "a.py", "a", None)
    migration(versions / "b.py", "b", "a")
    migration(versions / "c.py", "c", "a")
    report = module().build_report(tmp_path, versions)
    assert report["heads"] == ["b", "c"]
    assert report["branchpoints"] == {"a": ["b", "c"]}
    assert "HEAD_COUNT_NOT_ONE" in report["risks"]
    assert report["release_ready"] is False


def test_duplicate_and_missing_parent_are_detected(tmp_path: Path) -> None:
    versions = tmp_path / "versions"
    versions.mkdir()
    migration(versions / "first.py", "same", None)
    migration(versions / "duplicate.py", "same", None)
    migration(versions / "orphan.py", "orphan", "absent")
    report = module().build_report(tmp_path, versions)
    assert report["duplicate_revisions"] == {
        "same": ["versions/duplicate.py", "versions/first.py"]
    }
    assert report["missing_down_revisions"] == [
        {"revision": "orphan", "missing_parent": "absent"}
    ]
    assert "DUPLICATE_REVISION_IDENTIFIERS" in report["risks"]
    assert "MISSING_DOWN_REVISION" in report["risks"]


def test_merge_revision_restores_one_head(tmp_path: Path) -> None:
    versions = tmp_path / "versions"
    versions.mkdir()
    migration(versions / "a.py", "a", None)
    migration(versions / "b.py", "b", "a")
    migration(versions / "c.py", "c", "a")
    migration(versions / "merge.py", "m", ("b", "c"))
    report = module().build_report(tmp_path, versions)
    assert report["heads"] == ["m"]
    assert report["merge_revisions"] == {"m": ["b", "c"]}
    assert report["topological_order"][-1] == "m"
    assert report["release_ready"] is True
