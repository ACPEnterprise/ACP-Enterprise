from app.payroll.permissions import PayrollPermission
from app.platform.permissions.codes import WorkforcePermission
from app.timekeeping.permissions import TimekeepingPermission

READ_PERMISSION_CODES = frozenset(
    {
        WorkforcePermission.READ,
        PayrollPermission.POLICY_READ,
        PayrollPermission.COMPENSATION_READ,
        PayrollPermission.RUN_READ,
        PayrollPermission.REPORTING_READ,
        TimekeepingPermission.ADMIN_READ,
    }
)
ROLE_CODE = "ACCEPTANCE_READONLY_SERVICE"
AUTHENTICATION_METHOD = "acceptance_service_principal"
