from datetime import date
from uuid import uuid4

import pytest
from app.business_economics.router import (
    CashOperationalEconomicsService,
    EconomicsWorkspaceService,
    cash_operational_economics,
    economics_result,
    economics_workspace,
)
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_economics_errors_do_not_reflect_protected_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protected = f"payroll-customer-secret-{uuid4()}"

    async def invalid(*_args, **_kwargs):
        raise ValueError(protected)

    monkeypatch.setattr(EconomicsWorkspaceService, "overview", invalid)
    with pytest.raises(HTTPException) as captured:
        await economics_workspace(
            session=object(),
            context=object(),
            start=date(2026, 8, 1),
            end=date(2026, 8, 31),
        )
    response = captured.value
    assert response.status_code == 422
    assert response.detail["recovery"] == "USER_CORRECTION_REQUIRED"
    assert protected not in str(response.detail)

    monkeypatch.setattr(CashOperationalEconomicsService, "overview", invalid)
    with pytest.raises(HTTPException) as captured:
        await cash_operational_economics(
            session=object(),
            context=object(),
            start=date(2026, 8, 1),
            end=date(2026, 8, 31),
        )
    assert captured.value.status_code == 422
    assert protected not in str(captured.value.detail)

    async def missing(*_args, **_kwargs):
        raise LookupError(protected)

    monkeypatch.setattr(EconomicsWorkspaceService, "detail", missing)
    with pytest.raises(HTTPException) as captured:
        await economics_result(result_id=uuid4(), session=object(), context=object())
    response = captured.value
    assert response.status_code == 404
    assert response.detail["recovery"] == "TERMINAL_FAILURE"
    assert protected not in str(response.detail)
