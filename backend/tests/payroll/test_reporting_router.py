import pytest
from fastapi import FastAPI, HTTPException

from app.payroll.router import _compliance, _experience, _not_found, router

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


def test_protected_storage_and_report_absence_use_safe_recovery_contracts(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.payroll.router.settings.payroll_paystatement_artifact_root", None
    )
    for factory in (_experience, _compliance):
        with pytest.raises(HTTPException) as captured:
            factory()
        assert captured.value.status_code == 503
        assert captured.value.detail["code"] == "dependency_unavailable"
        assert (
            captured.value.detail["recovery"] == "OWNER_ADMIN_ACTION_REQUIRED"
        )
        assert "configured" not in captured.value.detail["message"].lower()

    missing = _not_found()
    assert missing.status_code == 404
    assert missing.detail["code"] == "not_found"
    assert missing.detail["recovery"] == "TERMINAL_FAILURE"
