from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.beacon.errors import (
    BeaconSignalNotFoundError,
    BeaconSignalStaleError,
    BeaconSnoozeInvalidError,
    BeaconWorkflowConflictError,
    BeaconWorkflowOwnerInvalidError,
)
from app.beacon.router import _lifecycle_http_error
from app.beacon.router import router as beacon_router
from app.beacon.workflow import beacon_workflow_service
from app.database.session import get_database_session
from app.platform.permissions.codes import AnalyticsPermission, BeaconPermission
from app.platform.permissions.dependencies import get_authorization_context


def test_beacon_errors_use_safe_recovery_envelopes_without_reflection() -> None:
    secret = f"signal-provider-secret-{uuid4()}"
    cases = (
        (BeaconSignalNotFoundError(secret), 404, "not_found", "TERMINAL_FAILURE"),
        (
            BeaconSignalStaleError(secret),
            409,
            "resource_state_conflict",
            "RETRY_AFTER_REFRESH",
        ),
        (
            BeaconWorkflowConflictError(secret),
            409,
            "resource_state_conflict",
            "RETRY_AFTER_REFRESH",
        ),
        (
            BeaconSnoozeInvalidError(secret),
            422,
            "validation",
            "USER_CORRECTION_REQUIRED",
        ),
        (
            BeaconWorkflowOwnerInvalidError(secret),
            422,
            "validation",
            "USER_CORRECTION_REQUIRED",
        ),
    )
    for error, status, code, recovery in cases:
        response = _lifecycle_http_error(error)
        assert response.status_code == status
        assert response.detail["code"] == code
        assert response.detail["recovery"] == recovery
        assert secret not in str(response.detail)


@pytest.mark.asyncio
async def test_beacon_routes_bind_read_claim_assign_and_release_independently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    permissions = {AnalyticsPermission.READ}
    actor_id = uuid4()
    company_id = uuid4()
    context = SimpleNamespace(
        user=SimpleNamespace(id=actor_id),
        company=SimpleNamespace(id=company_id),
        active_branch=None,
        has_permission=lambda code: code in permissions,
    )
    mutate = AsyncMock(side_effect=BeaconSignalNotFoundError("internal signal detail"))
    monkeypatch.setattr(beacon_workflow_service, "mutate", mutate)
    app = FastAPI()
    app.include_router(beacon_router)

    async def session_override():
        yield object()

    async def context_override():
        return context

    app.dependency_overrides[get_database_session] = session_override
    app.dependency_overrides[get_authorization_context] = context_override
    signal_id = uuid4()
    payload = {
        "evidence_digest": "a" * 64,
        "request_id": str(uuid4()),
        "expected_version": 0,
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for action in ("claim", "assign", "transfer", "release"):
            response = await client.post(
                f"/api/v1/beacon/signals/{signal_id}/{action}", json=payload
            )
            assert response.status_code == 403
        mutate.assert_not_awaited()

        permissions.clear()
        permissions.add(BeaconPermission.OWN)
        claim = await client.post(
            f"/api/v1/beacon/signals/{signal_id}/claim", json=payload
        )
        release_by_owner = await client.post(
            f"/api/v1/beacon/signals/{signal_id}/release", json=payload
        )
        assign_by_owner = await client.post(
            f"/api/v1/beacon/signals/{signal_id}/assign", json=payload
        )
        assert claim.status_code == 404
        assert release_by_owner.status_code == 404
        assert assign_by_owner.status_code == 403

        permissions.clear()
        permissions.add(BeaconPermission.ASSIGN)
        for action in ("assign", "transfer", "release"):
            response = await client.post(
                f"/api/v1/beacon/signals/{signal_id}/{action}", json=payload
            )
            assert response.status_code == 404

    assert mutate.await_count == 5
