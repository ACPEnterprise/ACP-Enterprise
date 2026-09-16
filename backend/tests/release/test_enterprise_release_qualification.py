from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
from pathlib import Path


def _module():
    path = Path(__file__).parents[3] / "scripts" / "enterprise-release-qualify"
    loader = importlib.machinery.SourceFileLoader("enterprise_release_qualify", str(path))
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
    assert module.STATUSES == {"PASS", "FAIL", "BLOCKED", "NOT APPLICABLE", "NOT YET EXECUTED"}
