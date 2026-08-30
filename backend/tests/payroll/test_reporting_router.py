from fastapi import FastAPI

from app.payroll.router import router

app = FastAPI()
app.include_router(router)


def test_reporting_admin_routes_are_bounded_and_not_employee_facing() -> None:
    paths = {route.path for route in router.routes}

    assert "/api/v1/payroll/reporting" in paths
    assert "/api/v1/payroll/reporting/{report_id}" in paths
    assert "/api/v1/payroll/reporting/{report_id}/filing-packages" in paths
    assert "/api/v1/payroll/me/reporting" not in paths


def test_reporting_lists_publish_bounded_pagination_contract() -> None:
    document = app.openapi()
    for path in (
        "/api/v1/payroll/reporting",
        "/api/v1/payroll/compliance/schemas",
        "/api/v1/payroll/reporting/{report_id}/filing-packages",
    ):
        parameters = {
            item["name"]: item
            for item in document["paths"][path]["get"]["parameters"]
        }
        assert parameters["limit"]["schema"]["default"] == 100
        assert parameters["limit"]["schema"]["maximum"] == 200
        assert parameters["offset"]["schema"]["default"] == 0
        assert parameters["offset"]["schema"]["minimum"] == 0
