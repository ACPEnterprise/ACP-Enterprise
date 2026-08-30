from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.financial_reporting.errors import (
    ReportingIntegrityError,
    ReportingNotFound,
    ReportingRequestError,
)
from app.financial_reporting.router import _generate
from app.financial_reporting.router import (
    accounting_service as router_accounting_service,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "status", "code", "recovery"),
    (
        (ReportingNotFound, 404, "not_found", "TERMINAL_FAILURE"),
        (ReportingRequestError, 422, "validation", "USER_CORRECTION_REQUIRED"),
    ),
)
async def test_reporting_errors_do_not_reflect_protected_details(
    error: type[Exception], status: int, code: str, recovery: str
) -> None:
    protected = f"sql-payroll-secret-{uuid4()}"

    async def fail():
        raise error(protected)

    with pytest.raises(HTTPException) as captured:
        await _generate(
            session=AsyncMock(),
            context=SimpleNamespace(),
            report_name="trial_balance",
            request_identity="safe-request",
            operation=fail,
        )
    response = captured.value
    assert response.status_code == status
    assert response.detail["code"] == code
    assert response.detail["recovery"] == recovery
    assert protected not in str(response.detail)


@pytest.mark.asyncio
async def test_integrity_failure_uses_fixed_durable_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protected = f"constraint-payroll-secret-{uuid4()}"
    session = AsyncMock()
    record = AsyncMock()
    monkeypatch.setattr(router_accounting_service, "record_posting_failure", record)

    async def fail():
        raise ReportingIntegrityError(protected)

    with pytest.raises(HTTPException) as captured:
        await _generate(
            session=session,
            context=SimpleNamespace(),
            report_name="income_statement",
            request_identity="company-safe-request",
            operation=fail,
        )
    response = captured.value
    assert response.status_code == 409
    assert response.detail["code"] == "reconciliation_required"
    assert response.detail["recovery"] == "RECONCILIATION_REQUIRED"
    assert protected not in str(response.detail)
    record.assert_awaited_once()
    assert record.await_args.kwargs["error_code"] == "ledger_integrity_failure"
    assert protected not in str(record.await_args.kwargs)
