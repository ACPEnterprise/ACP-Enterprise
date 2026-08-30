from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from app.dispatch.errors import DispatchConflict, DispatchNotFound, DispatchValidation
from app.dispatch.router import dispatch_http, replace
from app.dispatch.schemas import AssignPrimaryRequest
from app.main import app
from app.platform.launch_controls import LAUNCH_ROLE_MATRIX, LaunchRoleCode
from app.platform.permissions.catalog import permission_catalog
from app.platform.permissions.codes import DispatchPermission, JobPermission


@pytest.mark.parametrize(
    ("error", "status_code", "code", "recovery"),
    [
        (DispatchNotFound("hidden"), 404, "not_found", "TERMINAL_FAILURE"),
        (
            DispatchConflict("internal conflict detail"),
            409,
            "resource_state_conflict",
            "RETRY_AFTER_REFRESH",
        ),
        (
            DispatchValidation("internal validation detail"),
            422,
            "validation",
            "USER_CORRECTION_REQUIRED",
        ),
    ],
)
def test_dispatch_failures_use_safe_recovery_contract(
    error, status_code: int, code: str, recovery: str
) -> None:
    translated = dispatch_http(error)
    assert translated.status_code == status_code
    assert translated.detail["code"] == code
    assert translated.detail["recovery"] == recovery
    assert translated.detail["correlation_id"] is None
    assert "internal" not in translated.detail["message"].lower()


def test_dispatch_permissions_are_canonical_and_separate() -> None:
    codes = {item.code for item in permission_catalog.definitions}
    assert DispatchPermission.READ in codes
    assert DispatchPermission.MANAGE in codes
    assert DispatchPermission.READ != DispatchPermission.MANAGE
    technician = next(
        role for role in LAUNCH_ROLE_MATRIX if role.code is LaunchRoleCode.TECHNICIAN
    )
    assert JobPermission.EXECUTE in technician.permission_codes
    assert DispatchPermission.MANAGE not in technician.permission_codes


@pytest.mark.asyncio
async def test_replace_missing_version_uses_safe_validation_contract() -> None:
    request = AssignPrimaryRequest(
        employee_id=uuid4(),
        reason="Synthetic replacement",
        idempotency_key="replace-safe-contract",
    )
    with pytest.raises(HTTPException) as captured:
        await replace(
            uuid4(),
            request,
            object(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
        )

    assert captured.value.status_code == 422
    assert captured.value.detail["code"] == "validation"
    assert captured.value.detail["recovery"] == "USER_CORRECTION_REQUIRED"
    assert "Expected version" not in str(captured.value.detail)


@pytest.mark.asyncio
async def test_dispatch_api_fails_closed_without_authentication() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        board = await client.get(
            "/api/v1/dispatch/board",
            params={
                "start_at": "2026-08-03T00:00:00Z",
                "end_at": "2026-08-04T00:00:00Z",
            },
        )
        assign = await client.post(
            "/api/v1/dispatch/appointments/00000000-0000-0000-0000-000000000001/assignment",
            json={
                "employee_id": "00000000-0000-0000-0000-000000000002",
                "reason": "test",
                "idempotency_key": "dispatch-api-test",
            },
        )
        arrival = await client.post(
            "/api/v1/dispatch/appointments/00000000-0000-0000-0000-000000000001/assignment/arrival",
            json={
                "state": "en_route",
                "expected_version": 1,
                "idempotency_key": "dispatch-arrival-test",
            },
        )
    assert board.status_code == 401
    assert assign.status_code == 401
    assert arrival.status_code == 401


def test_dispatch_openapi_contract_exposes_bounded_operations() -> None:
    paths = app.openapi()["paths"]
    assert "/api/v1/dispatch/board" in paths
    assert (
        "/api/v1/dispatch/appointments/{appointment_id}/eligible-technicians" in paths
    )
    assert "/api/v1/dispatch/appointments/{appointment_id}/assignment" in paths
    assert "/api/v1/dispatch/appointments/{appointment_id}/assignment/crew" in paths
    assert (
        "/api/v1/dispatch/appointments/{appointment_id}/assignment/reconcile" in paths
    )
    assert (
        "/api/v1/dispatch/appointments/{appointment_id}/assignment/exceptions" in paths
    )
    assert "/api/v1/dispatch/appointments/{appointment_id}/assignment/arrival" in paths
