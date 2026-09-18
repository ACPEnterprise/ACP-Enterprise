from types import SimpleNamespace

import pytest
from app.platform.factory_control.router import require_platform_owner_admin, router
from app.platform.launch_controls import LAUNCH_ROLE_MATRIX, LaunchRoleCode
from app.platform.permissions.catalog import permission_catalog
from app.platform.permissions.codes import LaunchPlatformPermission
from fastapi import HTTPException


def test_factory_control_permission_is_not_granted_to_tenant_roles():
    roles = {
        definition.code: definition.permission_codes
        for definition in LAUNCH_ROLE_MATRIX
    }
    permission = LaunchPlatformPermission.FACTORY_CONTROL_READ
    assert all(permission not in permissions for permissions in roles.values())


def test_company_administrator_role_is_denied_even_if_dependency_is_called_directly():
    context = SimpleNamespace(
        effective_roles=[SimpleNamespace(code=LaunchRoleCode.COMPANY_ADMINISTRATOR)]
    )
    with pytest.raises(HTTPException) as error:
        require_platform_owner_admin(context)  # type: ignore[arg-type]
    assert error.value.status_code == 503
    assert error.value.detail == "PLATFORM_IDENTITY_HUMAN_GATE"


def test_every_factory_control_api_uses_platform_owner_admin_dependency():
    assert router.routes
    for route in router.routes:
        assert any(
            dependency.call is require_platform_owner_admin
            for dependency in route.dependant.dependencies
        )


def test_factory_control_permission_has_platform_catalog_semantics():
    definition = next(
        item
        for item in permission_catalog.definitions
        if item.code == LaunchPlatformPermission.FACTORY_CONTROL_READ
    )
    assert definition.resource == "factory_control"
    assert definition.action == "read"
    assert definition.scope.value == "platform"
