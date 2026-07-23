from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from development_factory.database import (
    DisposableDatabase,
    config_from_dict,
)
from development_factory.manifest import load_manifest
from development_factory.models import CheckDefinition, CheckResult, RepositoryState
from development_factory.policies import scan_policies
from development_factory.reports import build_report, redact, write_reports
from development_factory.repository import inspect_repository


class DevelopmentFactory:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.config = self._load_config()
        manifest_path = self.repo_root / str(self.config["manifest"])
        self.checks = load_manifest(manifest_path)

    def validate(
        self, selected_areas: tuple[str, ...], *, changed_only: bool = False
    ) -> tuple[dict[str, Any], Path, Path]:
        state = inspect_repository(self.repo_root)
        areas = self._changed_areas(state) if changed_only else selected_areas
        results: list[CheckResult] = []
        for check in self.checks:
            if not self._selected(check, areas):
                results.append(
                    CheckResult(
                        id=check.id,
                        name=check.name,
                        category=check.category,
                        required=check.required,
                        status="skipped",
                        duration_seconds=0,
                        summary="Skipped by explicit validation selection",
                    )
                )
                continue
            results.append(self._run_check(check, state))

        ordered = tuple(results)
        report = build_report(
            state=state,
            scope=areas,
            results=ordered,
            environment={
                "python": platform.python_version(),
                "platform": platform.system(),
                "factory_config": "development-factory/config.json",
            },
        )
        report_directory = Path(
            os.getenv(
                "DF_REPORT_DIRECTORY",
                str(self.config.get("report_directory", ".development-factory")),
            )
        )
        if not report_directory.is_absolute():
            report_directory = self.repo_root / report_directory
        json_path, markdown_path = write_reports(report, report_directory)
        return report, json_path, markdown_path

    def _run_check(self, check: CheckDefinition, state: RepositoryState) -> CheckResult:
        missing = [item for item in check.dependencies if shutil.which(item) is None]
        if missing:
            return CheckResult(
                id=check.id,
                name=check.name,
                category=check.category,
                required=check.required,
                status="unavailable",
                duration_seconds=0,
                summary=f"Missing dependencies: {', '.join(missing)}",
                failure_classification=check.failure_classification,
            )
        started = time.monotonic()
        try:
            if check.command is not None:
                completed = subprocess.run(
                    check.command,
                    cwd=(
                        self.repo_root / check.working_directory
                        if check.working_directory
                        else self.repo_root
                    ),
                    capture_output=True,
                    text=True,
                    timeout=check.timeout_seconds,
                    check=False,
                )
                status = "passed" if completed.returncode == 0 else "failed"
                output = redact((completed.stdout + completed.stderr)[-20000:])
                summary = (
                    "Command completed successfully"
                    if completed.returncode == 0
                    else f"Command exited with status {completed.returncode}"
                )
                return self._result(check, status, started, summary, output)
            if check.implementation == "repository_state":
                if state.conflicts:
                    return self._result(
                        check,
                        "failed",
                        started,
                        f"Unresolved conflicts: {', '.join(state.conflicts)}",
                    )
                return self._result(
                    check,
                    "passed",
                    started,
                    f"{len(state.files)} changed file(s); index "
                    f"{'clean' if state.index_clean else 'contains staged changes'}",
                )
            if check.implementation == "policy_scan":
                findings = scan_policies(self.repo_root, self.config)
                errors = [
                    item
                    for item in findings
                    if item.severity == "error" and not item.suppressed
                ]
                return self._result(
                    check,
                    "failed" if errors else "passed",
                    started,
                    f"{len(errors)} error(s), "
                    f"{sum(item.severity == 'warning' and not item.suppressed for item in findings)} warning(s)",
                    findings=findings,
                )
            if check.implementation == "backend_tests":
                return self._database_check(
                    check,
                    started,
                    f"pytest -q {os.getenv('DF_BACKEND_TEST_TARGET', 'tests')}",
                    migration_lifecycle=False,
                )
            if check.implementation == "migration_validation":
                return self._database_check(
                    check, started, "", migration_lifecycle=True
                )
            return self._result(
                check, "failed", started, "Unknown check implementation"
            )
        except subprocess.TimeoutExpired:
            return self._result(
                check,
                "failed",
                started,
                f"Timed out after {check.timeout_seconds} seconds",
            )
        except (
            OSError,
            RuntimeError,
            ValueError,
            subprocess.CalledProcessError,
        ) as exc:
            return self._result(
                check,
                "failed",
                started,
                redact(f"{type(exc).__name__}: {exc}"),
            )

    def _database_check(
        self,
        check: CheckDefinition,
        started: float,
        command: str,
        *,
        migration_lifecycle: bool,
    ) -> CheckResult:
        database = DisposableDatabase(config_from_dict(self.config), self.repo_root)
        output: list[str] = []
        status = "passed"
        summary = "Disposable PostgreSQL validation passed"
        try:
            database.create()
            commands: tuple[str, ...]
            if migration_lifecycle:
                commands = (
                    "alembic upgrade head",
                    "alembic downgrade -1",
                    "alembic upgrade head",
                    "alembic check",
                    "alembic heads",
                )
            else:
                commands = ("alembic upgrade head", command)
            for item in commands:
                completed = database.backend(item, check.timeout_seconds)
                output.append(completed.stdout)
                output.append(completed.stderr)
        except (
            OSError,
            RuntimeError,
            ValueError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ) as exc:
            status = "failed"
            summary = redact(f"Disposable PostgreSQL validation failed: {exc}")
            if isinstance(exc, subprocess.CalledProcessError):
                output.extend((exc.stdout or "", exc.stderr or ""))
        finally:
            try:
                database.drop_and_verify()
            except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
                status = "failed"
                summary = redact(f"Disposable database teardown failed: {exc}")
        return self._result(
            check,
            status,
            started,
            summary,
            redact("".join(output)[-20000:]),
        )

    def _result(
        self,
        check: CheckDefinition,
        status: str,
        started: float,
        summary: str,
        output: str = "",
        findings: tuple[Any, ...] = (),
    ) -> CheckResult:
        return CheckResult(
            id=check.id,
            name=check.name,
            category=check.category,
            required=check.required,
            status=status,  # type: ignore[arg-type]
            duration_seconds=round(time.monotonic() - started, 3),
            summary=summary,
            failure_classification=(
                check.failure_classification if status == "failed" else None
            ),
            output=output,
            findings=findings,
        )

    def _load_config(self) -> dict[str, Any]:
        path = self.repo_root / "development-factory" / "config.json"
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
            raise ValueError("Development Factory config schema_version must be 1.0")
        return payload

    @staticmethod
    def _selected(check: CheckDefinition, areas: tuple[str, ...]) -> bool:
        return (
            "all" in areas
            or check.category == "repository"
            or any(area in areas for area in check.areas)
        )

    @staticmethod
    def _changed_areas(state: RepositoryState) -> tuple[str, ...]:
        areas = {"architecture"}
        for item in state.files:
            if item.category.startswith("backend"):
                areas.add("backend")
            elif item.category.startswith("frontend"):
                areas.add("frontend")
            elif item.category == "migrations":
                areas.update(("backend", "migrations"))
        return tuple(sorted(areas))
