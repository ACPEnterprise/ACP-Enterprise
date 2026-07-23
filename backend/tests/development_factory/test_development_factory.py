import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from development_factory.manifest import ManifestError, load_manifest
from development_factory.models import (
    CheckDefinition,
    CheckResult,
    ClassifiedFile,
    RepositoryState,
)
from development_factory.engine import DevelopmentFactory
from development_factory.policies import scan_policies
from development_factory.reports import build_report, redact, render_markdown
from development_factory.repository import (
    classification_summary,
    classify_path,
    inspect_repository,
)
import development_factory.repository as repository_module


def valid_check(**overrides: object) -> dict[str, object]:
    check: dict[str, object] = {
        "id": "example.check",
        "name": "Example",
        "category": "backend",
        "command": ["true"],
        "required": True,
        "areas": ["backend"],
        "timeout_seconds": 10,
        "dependencies": [],
        "failure_classification": "quality",
        "parallel": False,
        "order": 10,
    }
    check.update(overrides)
    return check


def write_manifest(path: Path, checks: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps({"schema_version": "1.0", "checks": checks}),
        encoding="utf-8",
    )


def clean_state() -> RepositoryState:
    return RepositoryState(branch="test", head="a" * 40)


def result(
    status: str = "passed", *, required: bool = True, identifier: str = "check"
) -> CheckResult:
    return CheckResult(
        id=identifier,
        name=identifier,
        category="backend",
        required=required,
        status=status,  # type: ignore[arg-type]
        duration_seconds=0.1,
        summary=status,
    )


def test_manifest_loading_is_ordered_and_immutable(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    write_manifest(
        path,
        [
            valid_check(id="second", order=20),
            valid_check(id="first", order=10),
        ],
    )
    checks = load_manifest(path)
    assert [check.id for check in checks] == ["first", "second"]
    with pytest.raises(FrozenInstanceError):
        checks[0].name = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"schema_version": "2.0", "checks": []},
        {"schema_version": "1.0", "checks": []},
        {
            "schema_version": "1.0",
            "checks": [valid_check(implementation="x")],
        },
        {
            "schema_version": "1.0",
            "checks": [valid_check(id="same"), valid_check(id="same")],
        },
    ],
)
def test_invalid_manifest_is_rejected(tmp_path: Path, payload: object) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(path)


def test_check_classification_and_required_unavailable_blocking() -> None:
    report = build_report(
        state=clean_state(),
        scope=("backend",),
        results=(result("unavailable"), result("skipped", identifier="other")),
        environment={},
    )
    assert report["exit_status"] == 1
    assert report["readiness"] == "Blocked by unavailable required checks"
    assert report["blocking_failures"] == ["check"]


def test_optional_unavailable_does_not_block_owner_review() -> None:
    report = build_report(
        state=RepositoryState(
            branch="test",
            head="a" * 40,
            files=[ClassifiedFile("docs/a.md", "??", "documentation", False, True)],
        ),
        scope=("all",),
        results=(result("unavailable", required=False),),
        environment={},
    )
    assert report["exit_status"] == 0
    assert report["readiness"] == "Ready for owner review"


def test_missing_dependency_is_classified_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = DevelopmentFactory.__new__(DevelopmentFactory)
    factory.repo_root = tmp_path
    factory.config = {}
    check = CheckDefinition(
        id="missing",
        name="Missing dependency",
        category="backend",
        required=True,
        areas=("backend",),
        timeout_seconds=10,
        dependencies=("not-installed",),
        failure_classification="quality",
        parallel=False,
        order=1,
        command=("not-installed",),
    )
    monkeypatch.setattr("development_factory.engine.shutil.which", lambda _name: None)
    value = factory._run_check(check, clean_state())
    assert value.status == "unavailable"
    assert value.required
    assert "not-installed" in value.summary


def test_report_schema_contract_and_markdown() -> None:
    report = build_report(
        state=clean_state(),
        scope=("all",),
        results=(result(),),
        environment={"python": "test"},
    )
    required = {
        "schema_version",
        "generated_at",
        "repository",
        "selected_scope",
        "checks",
        "exit_status",
        "readiness",
        "changed_files",
        "blocking_failures",
        "owner_review_items",
    }
    assert required <= report.keys()
    assert report["schema_version"] == "1.0"
    markdown = render_markdown(report)
    assert "# ACP Development Factory Report" in markdown
    assert "Ready for owner review" in markdown
    assert "Automation does not approve" in markdown


def test_secret_redaction() -> None:
    output = redact(
        "DATABASE_URL=postgresql://user:password@host/db "
        "api_key=super-secret-value token=abc123"
    )
    assert "postgresql://" not in output
    assert "super-secret-value" not in output
    assert "abc123" not in output
    assert output.count("[REDACTED]") == 3


@pytest.mark.parametrize(
    "path,expected",
    [
        ("backend/app/jobs/service.py", "backend_runtime"),
        ("backend/tests/jobs/test_service.py", "backend_tests"),
        ("frontend/src/api/jobs.ts", "frontend_runtime"),
        ("frontend/src/api/jobs.test.ts", "frontend_tests"),
        ("backend/alembic/versions/a.py", "migrations"),
        ("docs/a.md", "documentation"),
        ("infrastructure/main.tf", "infrastructure"),
        ("backend/development_factory/engine.py", "development_tooling"),
        (".gitignore", "development_tooling"),
        ("strange.bin", "unknown"),
    ],
)
def test_changed_file_classification(path: str, expected: str) -> None:
    assert classify_path(path) == expected


def test_classification_totals_are_deterministic() -> None:
    state = clean_state()
    state.files.extend(
        [
            ClassifiedFile("docs/b.md", "??", "documentation", False, True),
            ClassifiedFile("docs/a.md", " M", "documentation", False, False),
            ClassifiedFile("backend/app/x.py", " M", "backend_runtime", False, False),
        ]
    )
    assert classification_summary(state) == {
        "backend_runtime": 1,
        "documentation": 2,
    }


def test_repository_state_detects_staged_untracked_and_conflicts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_git(_repo_root: Path, *args: str) -> str:
        if args == ("branch", "--show-current"):
            return "test\n"
        if args == ("rev-parse", "HEAD"):
            return f"{'a' * 40}\n"
        if args[:2] == ("status", "--porcelain=v1"):
            return "M  tracked.txt\0?? new.txt\0"
        if args == ("diff", "--name-only", "--diff-filter=U"):
            return "conflicted.txt\n"
        raise AssertionError(args)

    monkeypatch.setattr(repository_module, "_git", fake_git)
    state = inspect_repository(tmp_path)
    assert not state.index_clean
    assert {item.path for item in state.files} == {"tracked.txt", "new.txt"}
    assert any(item.staged for item in state.files)
    assert any(item.untracked for item in state.files)
    assert state.conflicts == ["conflicted.txt"]


def test_policy_findings_cover_boundaries_conflicts_and_forbidden_actions(
    tmp_path: Path,
) -> None:
    router = tmp_path / "backend/app/jobs/router.py"
    router.parent.mkdir(parents=True)
    router.write_text("value = select(Job)\nsession.commit()\n", encoding="utf-8")
    service = tmp_path / "backend/app/jobs/service.py"
    service.write_text(
        "from fastapi import HTTPException\n<<<<<<< HEAD\n", encoding="utf-8"
    )
    script = tmp_path / "scripts/development-factory"
    script.parent.mkdir()
    script.write_text("#!/bin/sh\ngit commit -m bad\n", encoding="utf-8")
    findings = scan_policies(
        tmp_path, {"policy": {"allowlisted_paths": [], "suppressions": []}}
    )
    rules = {finding.rule_id for finding in findings}
    assert "architecture.router_boundary" in rules
    assert "architecture.service_http" in rules
    assert "repository.merge_marker" in rules
    assert "factory.forbidden_action" in rules


def test_runtime_import_isolation_finding(tmp_path: Path) -> None:
    runtime = tmp_path / "backend/app/main.py"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("import development_factory\n", encoding="utf-8")
    findings = scan_policies(
        tmp_path, {"policy": {"allowlisted_paths": [], "suppressions": []}}
    )
    assert any(item.rule_id == "runtime.factory_import" for item in findings)


def test_suppression_requires_rationale_and_remains_visible(tmp_path: Path) -> None:
    router = tmp_path / "backend/app/jobs/router.py"
    router.parent.mkdir(parents=True)
    router.write_text("value = select(Job)\n", encoding="utf-8")
    with pytest.raises(ValueError, match="rationale"):
        scan_policies(
            tmp_path,
            {
                "policy": {
                    "allowlisted_paths": [],
                    "suppressions": [
                        {
                            "rule_id": "architecture.router_boundary",
                            "path": "backend/app/jobs/router.py",
                        }
                    ],
                }
            },
        )
    findings = scan_policies(
        tmp_path,
        {
            "policy": {
                "allowlisted_paths": [],
                "suppressions": [
                    {
                        "rule_id": "architecture.router_boundary",
                        "path": "backend/app/jobs/router.py",
                        "rationale": "Reviewed compatibility query.",
                    }
                ],
            }
        },
    )
    assert findings[0].suppressed
    assert findings[0].rationale == "Reviewed compatibility query."


def test_report_order_follows_input_check_order() -> None:
    report = build_report(
        state=clean_state(),
        scope=("all",),
        results=(
            result(identifier="first"),
            result(identifier="second"),
        ),
        environment={},
    )
    assert [item["id"] for item in report["checks"]] == ["first", "second"]
