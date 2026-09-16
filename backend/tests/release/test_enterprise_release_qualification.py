from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
from pathlib import Path


def _module():
    path = Path(__file__).parents[3] / "scripts" / "enterprise-release-qualify"
    loader = importlib.machinery.SourceFileLoader(
        "enterprise_release_qualify", str(path)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


def test_release_catalog_covers_required_gates() -> None:
    module = _module()
    keys = {check.key for check in module.checks()}
    assert {
        "repository_cleanliness",
        "backend_dependencies",
        "frontend_dependencies",
        "backend_lint",
        "backend_types",
        "backend_tests",
        "frontend_lint",
        "frontend_types",
        "frontend_tests",
        "frontend_build",
        "migration_heads",
        "migration_rehearsal",
        "api_health",
        "authentication_smoke",
        "authorization_smoke",
        "critical_crud",
        "background_services",
        "postgres_health",
        "redis_health",
        "preview_configuration",
        "secret_custody",
        "release_revision",
        "rollback_readiness",
        "postdeploy_routes",
    } <= keys


def test_status_vocabulary_is_closed() -> None:
    module = _module()
    assert module.STATUSES == {
        "PASS",
        "FAIL",
        "BLOCKED",
        "NOT APPLICABLE",
        "NOT YET EXECUTED",
    }


def test_supported_python_is_used_for_backend_checks(monkeypatch) -> None:
    module = _module()
    monkeypatch.setattr(module.sys, "version_info", (3, 9, 0))
    monkeypatch.setattr(
        module.shutil,
        "which",
        lambda tool: "/qualified/python3.12" if tool == "python3.12" else None,
    )
    assert module.supported_python() == "/qualified/python3.12"
    backend = next(check for check in module.checks() if check.key == "backend_tests")
    assert backend.command is not None
    assert backend.command[0] == "/qualified/python3.12"


def test_explicit_supported_python_environment_wins(monkeypatch) -> None:
    module = _module()
    monkeypatch.setenv("ENTERPRISE_RELEASE_PYTHON", "/qualified/venv/bin/python")
    assert module.supported_python() == "/qualified/venv/bin/python"
