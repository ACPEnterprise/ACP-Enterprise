from datetime import date
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException

from app.accounts_payable.errors import APValidation
from app.accounts_payable.router import _branch as require_ap_branch
from app.accounts_payable.router import router as accounts_payable_router
from app.accounts_payable.service import AccountsPayableService
from app.invoicing.errors import InvoiceValidation
from app.invoicing.router import _branch as require_invoice_branch
from app.invoicing.router import router as invoice_router
from app.invoicing.service import InvoiceService

app = FastAPI()
app.include_router(invoice_router)
app.include_router(accounts_payable_router)


def test_invoice_and_ap_lists_publish_bounded_pagination_contracts() -> None:
    document = app.openapi()
    for path in ("/api/v1/invoices", "/api/v1/accounts-payable/aging"):
        operation = document["paths"][path]["get"]
        parameters = {item["name"]: item for item in operation["parameters"]}
        assert parameters["limit"]["schema"]["default"] == 100
        assert parameters["limit"]["schema"]["maximum"] == 200
        assert parameters["offset"]["schema"]["default"] == 0
        assert parameters["offset"]["schema"]["minimum"] == 0


@pytest.mark.asyncio
async def test_financial_services_reject_unbounded_internal_requests() -> None:
    with pytest.raises(InvoiceValidation, match="page is invalid"):
        await InvoiceService().list(
            object(),  # type: ignore[arg-type]
            uuid4(),
            frozenset({uuid4()}),
            limit=201,
        )
    with pytest.raises(APValidation, match="page is invalid"):
        await AccountsPayableService().aging(
            object(),  # type: ignore[arg-type]
            uuid4(),
            date(2026, 8, 30),
            frozenset({uuid4()}),
            limit=201,
        )


def test_financial_branch_concealment_uses_safe_recovery_contract() -> None:
    class DeniedContext:
        @staticmethod
        def can_access_branch(_branch_id) -> bool:
            return False

    canary = uuid4()
    for boundary in (require_invoice_branch, require_ap_branch):
        with pytest.raises(HTTPException) as captured:
            boundary(DeniedContext(), canary)  # type: ignore[arg-type]
        assert captured.value.status_code == 404
        assert captured.value.detail["code"] == "not_found"
        assert captured.value.detail["recovery"] == "TERMINAL_FAILURE"
        assert captured.value.detail["correlation_id"] is None
        assert str(canary) not in str(captured.value.detail)
