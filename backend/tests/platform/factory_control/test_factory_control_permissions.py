from types import SimpleNamespace

import pytest
from app.platform.factory_control.router import require_platform_owner_admin, router
from app.platform.launch_controls import LAUNCH_ROLE_MATRIX, LaunchRoleCode
from app.platform.permissions.codes import LaunchPlatformPermission
from fastapi import HTTPException


def test_factory_control_permission_is_granted_only_to_platform_owner_admin():
    roles = {
        definition.code: definition.permission_codes
        for definition in LAUNCH_ROLE_MATRIX
    }
    permission = LaunchPlatformPermission.FACTORY_CONTROL_READ
    assert permission in roles[LaunchRoleCode.OWNER]
    assert permission in roles[LaunchRoleCode.ADMIN]
    assert permission not in roles[LaunchRoleCode.COMPANY_ADMINISTRATOR]
    assert all(
        permission not in permissions
        for role, permissions in roles.items()
        if role not in {LaunchRoleCode.OWNER, LaunchRoleCode.ADMIN}
    )


def test_company_administrator_role_is_denied_even_if_dependency_is_called_directly():
    context = SimpleNamespace(
        effective_roles=[SimpleNamespace(code=LaunchRoleCode.COMPANY_ADMINISTRATOR)]
    )
    with pytest.raises(HTTPException) as error:
        require_platform_owner_admin(context)  # type: ignore[arg-type]
    assert error.value.status_code == 403


def test_every_factory_control_api_uses_platform_owner_admin_dependency():
    assert router.routes
    for route in router.routes:
        assert any(
            dependency.call is require_platform_owner_admin
            for dependency in route.dependant.dependencies
        )
