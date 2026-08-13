from app.accounting.router import router


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
