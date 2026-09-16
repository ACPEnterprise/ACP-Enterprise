from uuid import uuid4

import httpx
import pytest
from app.estimates.errors import (
    EstimateConflictError,
    EstimateError,
    EstimateNotFoundError,
    EstimateValidationError,
)
from app.estimates.router import _branch, _error
from app.main import app
from fastapi import HTTPException


def test_estimate_errors_use_safe_recovery_envelopes_without_reflection() -> None:
    secret = f"sql-provider-secret-{uuid4()}"
    cases = (
        (EstimateNotFoundError(secret), 404, "not_found", "TERMINAL_FAILURE"),
        (
            EstimateConflictError(secret),
            409,
            "resource_state_conflict",
            "RETRY_AFTER_REFRESH",
        ),
        (
            EstimateValidationError(secret),
            422,
            "validation",
            "USER_CORRECTION_REQUIRED",
        ),
        (
            EstimateError(secret),
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
        assert secret not in str(response.detail)


def test_estimate_branch_denial_uses_safe_forbidden_contract() -> None:
    class Context:
        authorized_branches = ()

    canary = uuid4()
    with pytest.raises(HTTPException) as captured:
        _branch(Context(), canary)  # type: ignore[arg-type]

    assert captured.value.status_code == 403
    assert captured.value.detail["code"] == "forbidden"
    assert captured.value.detail["recovery"] == "OWNER_ADMIN_ACTION_REQUIRED"
    assert str(canary) not in str(captured.value.detail)


@pytest.mark.asyncio
async def test_estimate_job_conversion_is_authorized_and_not_an_internal_only_seam() -> None:
    path = "/api/v1/estimates/{estimate_id}/convert-to-job"
    assert path in app.openapi()["paths"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/estimates/00000000-0000-0000-0000-000000000001/convert-to-job",
            json={
                "branch_id": "00000000-0000-0000-0000-000000000002",
                "expected_version": 1,
                "idempotency_key": "estimate-job-boundary-test",
            },
        )
    assert response.status_code == 401
