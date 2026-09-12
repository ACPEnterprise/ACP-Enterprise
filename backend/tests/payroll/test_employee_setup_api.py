from app.main import app


def test_employee_setup_routes_are_bounded_and_separate_approval() -> None:
    paths = app.openapi()["paths"]
    assert set(paths["/api/v1/payroll/setup/employees/{employee_id}"]) == {"get"}
    assert set(paths["/api/v1/payroll/setup/employees/{employee_id}/compensations"]) == {"post"}
    assert set(paths["/api/v1/payroll/setup/employees/{employee_id}/inputs"]) == {"post"}
    assert set(paths["/api/v1/payroll/setup/compensations/{authority_id}/approve"]) == {"post"}
    assert set(paths["/api/v1/payroll/setup/inputs/{authority_id}/approve"]) == {"post"}


def test_protected_values_are_write_only() -> None:
    operation = app.openapi()["paths"]["/api/v1/payroll/setup/employees/{employee_id}"]["get"]
    assert "protected_values" not in repr(operation)
