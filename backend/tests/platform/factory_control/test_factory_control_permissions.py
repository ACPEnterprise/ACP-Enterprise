from app.platform.launch_controls import LAUNCH_ROLE_MATRIX, LaunchRoleCode
from app.platform.permissions.codes import LaunchPlatformPermission


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
