from uuid import uuid4

from app.main import app
from app.payroll.contracts import PayrollAuthorizationError, PayrollConflictError
from app.payroll.router import _error


def test_payroll_errors_use_safe_recovery_envelopes_without_reflection() -> None:
    protected = f"ssn-routing-provider-secret-{uuid4()}"
    cases = (
        (PayrollAuthorizationError(protected), 403, "forbidden", "TERMINAL_FAILURE"),
        (
            PayrollConflictError(protected),
            409,
            "resource_state_conflict",
            "RETRY_AFTER_REFRESH",
        ),
        (
            ValueError(protected),
            422,
            "validation",
            "USER_CORRECTION_REQUIRED",
        ),
        (
            RuntimeError(protected),
            500,
            "internal_failure",
            "OWNER_ADMIN_ACTION_REQUIRED",
        ),
    )
    for error, status, code, recovery in cases:
        response = _error(error)
        assert response.status_code == status
        assert response.detail["code"] == code
        assert response.detail["recovery"] == recovery
        assert protected not in str(response.detail)


def test_own_pay_statement_list_publishes_bounded_pagination() -> None:
    operation = app.openapi()["paths"]["/api/v1/payroll/me/pay-statements"]["get"]
    parameters = {item["name"]: item for item in operation["parameters"]}
    assert parameters["limit"]["schema"] == {
        "type": "integer",
        "maximum": 200,
        "minimum": 1,
        "default": 100,
        "title": "Limit",
    }
    assert parameters["offset"]["schema"] == {
        "type": "integer",
        "minimum": 0,
        "default": 0,
        "title": "Offset",
    }
