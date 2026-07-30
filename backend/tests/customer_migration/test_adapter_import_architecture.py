import ast
import inspect
import textwrap
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from app.customer_migration.adapter_import import CustomerAdapterImportService
from app.customer_migration.customer_import import (
    CustomerImportFacade,
    customer_import_facade,
)
from app.customer_migration.housecall_pro import HousecallProCustomerMigration

APP_ROOT = Path(__file__).parents[2] / "app"
MIGRATION_ROOT = APP_ROOT / "customer_migration"


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def calls_named(path: Path, name: str) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sum(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == name
        for node in ast.walk(tree)
    )


@pytest.mark.asyncio
async def test_facade_is_the_production_entry_point_and_delegates() -> None:
    service = AsyncMock(spec=CustomerAdapterImportService)
    facade = CustomerImportFacade(service=service)
    factory = cast(Any, object())
    context = cast(Any, object())
    reviewed = cast(Any, object())
    boundary = cast(Any, object())
    service.run.return_value = object()

    result = await facade.import_reviewed(
        factory, context=context, reviewed=reviewed, boundary=boundary
    )

    assert result is service.run.return_value
    service.run.assert_awaited_once_with(
        factory, context=context, reviewed=reviewed, boundary=boundary
    )
    assert isinstance(customer_import_facade, CustomerImportFacade)


def test_only_authoritative_adapter_service_reaches_customer_creation() -> None:
    production_files = tuple(MIGRATION_ROOT.glob("*.py"))
    callers = {
        path.name: calls_named(path, "stage_migrated_customer")
        for path in production_files
        if calls_named(path, "stage_migrated_customer")
    }
    assert callers == {"adapter_import.py": 1}


def test_legacy_orchestration_is_fail_closed_and_cannot_import() -> None:
    source = inspect.getsource(HousecallProCustomerMigration.run)
    tree = ast.parse(textwrap.dedent(source))
    assert any(isinstance(node, ast.Raise) for node in ast.walk(tree))
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "stage_migrated_customer"
        for node in ast.walk(tree)
    )


def test_repository_is_persistence_only() -> None:
    path = MIGRATION_ROOT / "adapter_import_repository.py"
    source = path.read_text(encoding="utf-8")
    repository_imports = imports(path)
    assert "app.customers.normalization" not in repository_imports
    assert "app.customers.service" not in repository_imports
    assert "duplicate_members" not in source
    assert "candidate_hashes" not in source
    assert "normalize_email" not in source
    assert "normalize_phone" not in source
    assert "build_normalized_address" not in source


def test_dependency_direction_is_acyclic() -> None:
    facade_imports = imports(MIGRATION_ROOT / "customer_import.py")
    service_imports = imports(MIGRATION_ROOT / "adapter_import.py")
    policy_imports = imports(MIGRATION_ROOT / "adapter_import_policy.py")
    repository_imports = imports(MIGRATION_ROOT / "adapter_import_repository.py")

    assert "app.customer_migration.adapter_import" in facade_imports
    assert "app.customer_migration.adapter_import_policy" in service_imports
    assert "app.customer_migration.adapter_import_repository" in service_imports
    assert "app.customer_migration.adapter_import" not in policy_imports
    assert "app.customer_migration.adapter_import" not in repository_imports
    assert "app.customer_migration.customer_import" not in service_imports
    assert "app.customer_migration.customer_import" not in policy_imports
    assert "app.customer_migration.customer_import" not in repository_imports


def test_provider_specific_code_stays_outside_domain_and_persistence() -> None:
    protected = (
        APP_ROOT / "customers" / "service.py",
        APP_ROOT / "customers" / "models.py",
        MIGRATION_ROOT / "adapter_import_repository.py",
        MIGRATION_ROOT / "adapter_import_policy.py",
        MIGRATION_ROOT / "adapter_import.py",
        MIGRATION_ROOT / "customer_import.py",
    )
    for path in protected:
        assert all("housecall_pro" not in module for module in imports(path))
