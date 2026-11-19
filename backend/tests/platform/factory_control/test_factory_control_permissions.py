import inspect
from pathlib import Path

from app.platform.factory_control.authority import require_platform_factory_reader
from app.platform.factory_control.router import router
from app.platform.launch_controls import LAUNCH_ROLE_MATRIX
from app.platform.permissions.catalog import permission_catalog
from app.platform.permissions.codes import LaunchPlatformPermission


def test_factory_control_permissions_are_not_granted_to_tenant_roles():
    factory_permissions = {
        LaunchPlatformPermission.FACTORY_CONTROL_READ,
        LaunchPlatformPermission.FACTORY_CONTROL_INGEST,
        LaunchPlatformPermission.FACTORY_CONTROL_SNAPSHOT,
    }
    assert all(
        not (factory_permissions & definition.permission_codes)
        for definition in LAUNCH_ROLE_MATRIX
    )


def test_human_read_and_controller_mutation_dependencies_are_split():
    by_path_method = {
        (route.path, method): route
        for route in router.routes
        for method in route.methods
    }
    for path in (
        "/api/v1/platform/factory-control/overview",
        "/api/v1/platform/factory-control/lanes/{lane_code}",
    ):
        route = by_path_method[(path, "GET")]
        assert any(
            dependency.call is require_platform_factory_reader
            for dependency in route.dependant.dependencies
        )
    for path in (
        "/api/v1/platform/factory-control/internal/events",
        "/api/v1/platform/factory-control/internal/live-sync",
        "/api/v1/platform/factory-control/internal/sync",
        "/api/v1/platform/factory-control/internal/snapshots",
    ):
        route = by_path_method[(path, "POST")]
        calls = [dependency.call for dependency in route.dependant.dependencies]
        assert require_platform_factory_reader not in calls
        assert any(
            inspect.iscoroutinefunction(call) and call.__name__ == "dependency"
            for call in calls
        )


def test_factory_control_permission_catalog_has_distinct_platform_actions():
    definitions = {
        item.code: item
        for item in permission_catalog.definitions
        if item.resource == "factory_control"
    }
    assert {code: definition.action for code, definition in definitions.items()} == {
        LaunchPlatformPermission.FACTORY_CONTROL_READ: "read",
        LaunchPlatformPermission.FACTORY_CONTROL_INGEST: "ingest",
        LaunchPlatformPermission.FACTORY_CONTROL_SNAPSHOT: "snapshot",
    }
    assert all(
        definition.scope.value == "platform" for definition in definitions.values()
    )


def test_factory_control_migration_does_not_auto_assign_platform_authority():
    migration = (
        Path(__file__).resolve().parents[3]
        / "alembic/versions/p2r4t6v8x1z3_create_factory_control_telemetry.py"
    ).read_text()
    assert "INSERT INTO platform_authority_assignments" not in migration
