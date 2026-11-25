#!/usr/bin/env python3
"""Independently verify current Alembic lineage evidence and expected head."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONTRACT = "enterprise-release.migration-lineage.v1"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
REVISION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class MigrationLineageError(ValueError):
    """A fail-closed migration lineage verification error."""


@dataclass(frozen=True)
class Revision:
    revision: str
    parents: tuple[str, ...]
    path: str
    sha256: str
    source_commit: str | None


def verify_lineage_evidence(
    *,
    repo_root: Path,
    evidence_path: Path,
    expected_head: str,
    expected_source_sha: str | None = None,
) -> dict[str, object]:
    root = repo_root.resolve()
    _validate_revision_id(expected_head, "expected migration head")
    source_sha = _git(root, "rev-parse", "HEAD")
    if not SHA40.fullmatch(source_sha):
        raise MigrationLineageError("repository HEAD is invalid")
    if expected_source_sha is not None:
        if not SHA40.fullmatch(expected_source_sha):
            raise MigrationLineageError("expected source SHA is invalid")
        if not _git_succeeds(
            root,
            "merge-base",
            "--is-ancestor",
            expected_source_sha,
            source_sha,
        ):
            raise MigrationLineageError("expected source SHA is not an ancestor")
        expected_tree = _git(
            root,
            "rev-parse",
            f"{expected_source_sha}:backend/alembic/versions",
        )
        actual_tree = _git(root, "rev-parse", "HEAD:backend/alembic/versions")
        if expected_tree != actual_tree:
            raise MigrationLineageError(
                "migration tree differs from expected source checkpoint"
            )

    evidence = _load_evidence(evidence_path)
    actual = build_lineage(root, root / "backend/alembic/versions")
    if evidence != actual:
        raise MigrationLineageError("stored migration lineage evidence is stale")
    if actual["heads"] != [expected_head]:
        raise MigrationLineageError("migration head does not match expected head")
    if not actual["release_ready"]:
        raise MigrationLineageError("migration lineage is not release ready")
    return {
        "contract": CONTRACT,
        "source_sha": source_sha,
        "migration_checkpoint_sha": expected_source_sha or source_sha,
        "revision_count": actual["revision_count"],
        "head": expected_head,
        "lineage_digest": actual["lineage_digest"],
        "evidence_sha256": _file_digest(evidence_path),
        "release_ready": True,
    }


def build_lineage(root: Path, versions: Path) -> dict[str, object]:
    revisions, parse_errors = _load_revisions(root, versions)
    grouped: dict[str, list[Revision]] = {}
    for item in revisions:
        grouped.setdefault(item.revision, []).append(item)
    duplicates = {
        revision: [item.path for item in items]
        for revision, items in grouped.items()
        if len(items) > 1
    }
    nodes = {revision: items[0] for revision, items in grouped.items()}
    children: dict[str, set[str]] = {revision: set() for revision in nodes}
    missing_parents: list[dict[str, str]] = []
    for item in nodes.values():
        for parent in item.parents:
            if parent not in nodes:
                missing_parents.append(
                    {"revision": item.revision, "missing_parent": parent}
                )
            else:
                children[parent].add(item.revision)

    heads = sorted(revision for revision, values in children.items() if not values)
    roots = sorted(revision for revision, item in nodes.items() if not item.parents)
    branchpoints = {
        revision: sorted(values)
        for revision, values in children.items()
        if len(values) > 1
    }
    merges = {
        revision: list(item.parents)
        for revision, item in nodes.items()
        if len(item.parents) > 1
    }
    cycles = _cycle_revisions(nodes)
    ordering = _topological_order(nodes, children)
    risks: list[str] = []
    if len(heads) != 1:
        risks.append("HEAD_COUNT_NOT_ONE")
    if duplicates:
        risks.append("DUPLICATE_REVISION_IDENTIFIERS")
    if missing_parents:
        risks.append("MISSING_DOWN_REVISION")
    if cycles:
        risks.append("REVISION_CYCLE")
    if len(roots) != 1:
        risks.append("ROOT_COUNT_NOT_ONE")
    if len(ordering) != len(nodes):
        risks.append("ORDERING_INCOMPLETE")

    records = [
        {
            "revision": item.revision,
            "down_revision": list(item.parents),
            "path": item.path,
            "sha256": item.sha256,
            "source_commit": item.source_commit,
            "is_head": item.revision in heads,
            "is_merge": len(item.parents) > 1,
        }
        for item in sorted(nodes.values(), key=lambda value: value.path)
    ]
    canonical: dict[str, object] = {
        "contract_version": CONTRACT,
        "revision_count": len(records),
        "roots": roots,
        "heads": heads,
        "branchpoints": branchpoints,
        "merge_revisions": merges,
        "duplicate_revisions": duplicates,
        "missing_down_revisions": missing_parents,
        "cycle_revisions": cycles,
        "topological_order": ordering,
        "parse_errors": parse_errors,
        "risks": risks,
        "release_ready": not risks,
        "revisions": records,
    }
    return {
        **canonical,
        "lineage_digest": hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def _load_revisions(
    root: Path, versions: Path
) -> tuple[list[Revision], list[dict[str, str]]]:
    revisions: list[Revision] = []
    errors: list[dict[str, str]] = []
    for path in sorted(versions.glob("*.py")):
        if path.name == "__init__.py":
            continue
        relative = path.relative_to(root).as_posix()
        try:
            content = path.read_bytes()
            tree = ast.parse(content, filename=relative)
            revision = _literal_assignment(tree, "revision")
            down_revision = _literal_assignment(tree, "down_revision")
            if not isinstance(revision, str) or not revision:
                raise ValueError("revision must be a non-empty string literal")
            _validate_revision_id(revision, "migration revision")
            parents = _parse_parents(down_revision)
            revisions.append(
                Revision(
                    revision=revision,
                    parents=parents,
                    path=relative,
                    sha256=hashlib.sha256(content).hexdigest(),
                    source_commit=_source_commit(root, relative),
                )
            )
        except (OSError, SyntaxError, ValueError) as error:
            errors.append({"path": relative, "error": str(error)})
    return revisions, errors


def _literal_assignment(tree: ast.Module, name: str) -> object | None:
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
            and node.value is not None
        ):
            return ast.literal_eval(node.value)
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    return None


def _parse_parents(value: object | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        parents = (value,)
    elif isinstance(value, (tuple, list)) and all(
        isinstance(item, str) for item in value
    ):
        parents = tuple(value)
    else:
        raise ValueError("down_revision must be None, a string, or string sequence")
    for parent in parents:
        _validate_revision_id(parent, "down revision")
    return parents


def _cycle_revisions(nodes: dict[str, Revision]) -> list[str]:
    visiting: set[str] = set()
    visited: set[str] = set()
    found: set[str] = set()

    def visit(revision: str) -> None:
        if revision in visiting:
            found.add(revision)
            return
        if revision in visited:
            return
        visiting.add(revision)
        for parent in nodes[revision].parents:
            if parent in nodes:
                visit(parent)
        visiting.remove(revision)
        visited.add(revision)

    for revision in nodes:
        visit(revision)
    return sorted(found)


def _topological_order(
    nodes: dict[str, Revision], children: dict[str, set[str]]
) -> list[str]:
    indegree = {
        revision: sum(parent in nodes for parent in item.parents)
        for revision, item in nodes.items()
    }
    ready = sorted(revision for revision, count in indegree.items() if count == 0)
    ordered: list[str] = []
    while ready:
        revision = ready.pop(0)
        ordered.append(revision)
        for child in sorted(children[revision]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort()
    return ordered


def _load_evidence(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise MigrationLineageError("migration evidence must be a regular file")
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MigrationLineageError("migration evidence is not valid JSON") from error
    if not isinstance(value, dict) or value.get("contract_version") != CONTRACT:
        raise MigrationLineageError("migration evidence contract is invalid")
    digest = value.get("lineage_digest")
    if not isinstance(digest, str) or not SHA64.fullmatch(digest):
        raise MigrationLineageError("migration evidence digest is invalid")
    return value


def _source_commit(root: Path, relative: str) -> str | None:
    result = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", relative],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    value = result.stdout.strip()
    return value or None


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise MigrationLineageError("Git inspection failed")
    return result.stdout.strip()


def _git_succeeds(root: Path, *arguments: str) -> bool:
    return (
        subprocess.run(
            ["git", *arguments],
            cwd=root,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_revision_id(value: str, label: str) -> None:
    if not REVISION_ID.fullmatch(value):
        raise MigrationLineageError(f"{label} is invalid")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=Path("docs/engineering/current-migration-lineage.json"),
    )
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-source-sha")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    evidence = args.evidence
    if not evidence.is_absolute():
        evidence = root / evidence
    try:
        result = verify_lineage_evidence(
            repo_root=root,
            evidence_path=evidence,
            expected_head=args.expected_head,
            expected_source_sha=args.expected_source_sha,
        )
    except MigrationLineageError as error:
        print(f"BLOCKED: {error}")
        return 2
    print(json.dumps({"result": "PASS", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
