from app.timekeeping.contracts import (
    WorkdayAuthorizationError,
    WorkdayConflictError,
    WorkdayTimeError,
)
from app.timekeeping.router import _error


def test_timekeeping_failures_are_classified_and_non_reflective() -> None:
    canary = "ssn=111-22-3333 routing=021000021 payroll-provider-token"
    forbidden = _error(WorkdayAuthorizationError(canary))
    conflict = _error(WorkdayConflictError(canary))
    validation = _error(WorkdayTimeError(canary))

    assert forbidden.status_code == 403
    assert forbidden.detail["recovery"] == "TERMINAL_FAILURE"
    assert conflict.status_code == 409
    assert conflict.detail["recovery"] == "RETRY_AFTER_REFRESH"
    assert validation.status_code == 422
    assert validation.detail["recovery"] == "USER_CORRECTION_REQUIRED"
    assert all(
        canary not in str(failure.detail)
        for failure in (forbidden, conflict, validation)
    )
