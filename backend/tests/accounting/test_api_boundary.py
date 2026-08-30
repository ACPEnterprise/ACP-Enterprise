from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.accounting.errors import (
    AccountingConflict,
    AccountingNotFound,
    AccountingPermissionDenied,
    AccountingValidation,
)
from app.accounting.router import approve_reopen, close_period, router, translate
from app.platform.permissions.codes import AccountingPermission


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
