from fastapi.routing import APIRoute

from app.financial_reporting.router import router


def test_reporting_api_is_read_only_and_bounded() -> None:
    assert {
        (route.path, tuple(sorted(route.methods or ())))
        for route in router.routes
        if isinstance(route, APIRoute)
    } == {
        ("/api/v1/accounting/reports/trial-balance", ("GET",)),
        ("/api/v1/accounting/reports/balance-sheet", ("GET",)),
        ("/api/v1/accounting/reports/income-statement", ("GET",)),
        ("/api/v1/accounting/reports/general-ledger", ("GET",)),
    }
