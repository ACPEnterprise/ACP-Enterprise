from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.accounting.errors import (
    AccountingConflict,
    AccountingNotFound,
    AccountingPermissionDenied,
    AccountingValidation,
)
from app.accounting.router import approve_reopen, close_period, router, translate
from app.accounting.schemas import PeriodTransitionRequest
from app.platform.permissions.codes import AccountingPermission
from fastapi import HTTPException


class PermissionContext:
    def __init__(self, *permissions: str) -> None:
        self.permissions = frozenset(permissions)

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions


@pytest.mark.parametrize(
    ("error", "status_code", "code", "recovery"),
    [
        (AccountingNotFound("protected id"), 404, "not_found", "TERMINAL_FAILURE"),
        (
            AccountingConflict("constraint or SQL detail"),
            409,
            "resource_state_conflict",
            "RETRY_AFTER_REFRESH",
        ),
        (
            AccountingPermissionDenied("protected authority detail"),
            403,
            "forbidden",
            "OWNER_ADMIN_ACTION_REQUIRED",
        ),
        (
            AccountingValidation("protected payload"),
            422,
            "validation",
            "USER_CORRECTION_REQUIRED",
        ),
    ],
)
def test_accounting_failures_use_safe_non_reflective_recovery_contract(
    error, status_code: int, code: str, recovery: str
) -> None:
    translated = translate(error)
    assert translated.status_code == status_code
    assert translated.detail["code"] == code
    assert translated.detail["recovery"] == recovery
    assert translated.detail["correlation_id"] is None
    assert "sql" not in translated.detail["message"].lower()
    assert "payload" not in translated.detail["message"].lower()


def test_accounting_api_is_company_authenticated_and_bounded() -> None:
    paths = {route.path for route in router.routes}
    assert paths == {
        "/api/v1/accounting/charts",
        "/api/v1/accounting/accounts",
        "/api/v1/accounting/control-accounts",
        "/api/v1/accounting/periods",
        "/api/v1/accounting/periods/{period_id}/report-comparisons",
        "/api/v1/accounting/periods/{period_id}/close-readiness",
        "/api/v1/accounting/accountant-review",
        "/api/v1/accounting/periods/{period_id}/begin-close",
        "/api/v1/accounting/periods/{period_id}/close",
        "/api/v1/accounting/periods/{period_id}/reopen-request",
        "/api/v1/accounting/periods/{period_id}/reopen-approval",
        "/api/v1/accounting/journals",
        "/api/v1/accounting/journals/{journal_id}/prepare",
        "/api/v1/accounting/journals/{journal_id}/approve",
        "/api/v1/accounting/journals/{journal_id}/post",
        "/api/v1/accounting/journals/{journal_id}/reversals",
        "/api/v1/accounting/trial-balance",
        "/api/v1/accounting/opening-controls/sealed-preview",
        "/api/v1/accounting/opening-controls/sealed",
        "/api/v1/accounting/opening-controls/{package_id}",
        "/api/v1/accounting/opening-controls/{package_id}/subledger/{family}",
        "/api/v1/accounting/opening-controls/{package_id}/exceptions",
        "/api/v1/accounting/opening-controls/{package_id}/approve",
        "/api/v1/accounting/opening-controls/{package_id}/apply",
    }
    assert all(route.path.startswith("/api/v1/accounting") for route in router.routes)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "permissions",
    [
        (AccountingPermission.PERIOD_MANAGE,),
        (AccountingPermission.FINANCE_APPROVE,),
    ],
)
async def test_period_close_requires_independent_manage_and_approval_permissions(
    permissions: tuple[str, ...],
) -> None:
    with pytest.raises(HTTPException) as raised:
        await close_period(
            uuid4(),
            SimpleNamespace(),  # type: ignore[arg-type]
            PermissionContext(*permissions),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
        )

    assert raised.value.status_code == 403
    assert raised.value.detail["code"] == "forbidden"
    assert raised.value.detail["recovery"] == "OWNER_ADMIN_ACTION_REQUIRED"


@pytest.mark.asyncio
async def test_period_reopen_approval_requires_finance_approval_permission() -> None:
    with pytest.raises(HTTPException) as raised:
        await approve_reopen(
            uuid4(),
            SimpleNamespace(),  # type: ignore[arg-type]
            PermissionContext(AccountingPermission.PERIOD_MANAGE),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
        )

    assert raised.value.status_code == 403
    assert raised.value.detail["code"] == "forbidden"
    assert raised.value.detail["recovery"] == "OWNER_ADMIN_ACTION_REQUIRED"


@pytest.mark.asyncio
async def test_period_close_replaces_browser_assertions_with_server_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.accounting.router as accounting_router

    period_id = uuid4()
    company_id = uuid4()
    period = SimpleNamespace(id=period_id)
    readiness = SimpleNamespace(evidence_digest="b" * 64, overall_readiness="READY")
    result = SimpleNamespace(
        id=period_id,
        company_id=company_id,
        name="May 2026",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
        status="closed",
        version=3,
    )
    close = AsyncMock(return_value=result)
    monkeypatch.setattr(
        accounting_router, "_read_period", AsyncMock(return_value=period)
    )
    monkeypatch.setattr(
        accounting_router.accounting_close_control_service,
        "readiness",
        AsyncMock(return_value=readiness),
    )
    monkeypatch.setattr(accounting_router.accounting_service, "close_period", close)
    context = SimpleNamespace(
        company=SimpleNamespace(id=company_id),
        has_permission=lambda _permission: True,
    )
    request = PeriodTransitionRequest(
        expected_version=2,
        reason="Accountant approved",
        readiness_digest="b" * 64,
        evidence_digest="a" * 64,
        controls_reconciled=False,
    )

    await close_period(period_id, request, context, SimpleNamespace())

    sent = close.await_args.kwargs["data"]
    assert sent.controls_reconciled is True
    assert sent.evidence_digest == "b" * 64
