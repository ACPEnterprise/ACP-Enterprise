from app.payroll.router import router


def test_reporting_admin_routes_are_bounded_and_not_employee_facing() -> None:
    paths = {route.path for route in router.routes}

    assert "/api/v1/payroll/reporting" in paths
    assert "/api/v1/payroll/reporting/{report_id}" in paths
    assert "/api/v1/payroll/reporting/{report_id}/filing-packages" in paths
    assert "/api/v1/payroll/me/reporting" not in paths
