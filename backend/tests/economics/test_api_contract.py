from fastapi import FastAPI

from app.economics.router import router


def test_economics_api_is_read_only() -> None:
    app = FastAPI()
    app.include_router(router)
    economics_operations = {
        method
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api/v1/economics")
        for method in operations
    }

    assert economics_operations == {"get"}
    assert {
        "/api/v1/economics/facts",
        "/api/v1/economics/jobs/{job_id}/profitability",
        "/api/v1/economics/branches/{branch_id}/profitability",
        "/api/v1/economics/company/profitability",
        "/api/v1/economics/subjects/{subject_type}/{subject_id}/history",
        "/api/v1/economics/evidence-completeness",
        "/api/v1/economics/stale-measurements",
        "/api/v1/economics/periods/{period_id}/close-readiness",
        "/api/v1/economics/periods/{period_id}/reconciliation",
        "/api/v1/economics/periods/{period_id}/allocations",
        "/api/v1/economics/periods/{period_id}/audit-package",
        "/api/v1/economics/periods/{period_id}/exports",
        "/api/v1/economics/projections/{projection_id}/lineage",
        "/api/v1/economics/periods/{period_id}/financial-integrity",
    }.issubset(app.openapi()["paths"])
