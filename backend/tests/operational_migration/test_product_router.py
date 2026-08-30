from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import UUID

import pytest
from app.operational_migration import product_router


class ConnectedRuntime:
    def connection_state(self) -> str:
        return "connected"


@pytest.mark.asyncio
async def test_authorized_company_wide_review_succeeds_without_active_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        product_router,
        "get_sandbox_oauth_runtime",
        lambda: ConnectedRuntime(),
    )
    context = SimpleNamespace(
        company=SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000001")),
        active_branch=None,
    )
    response = await product_router.migration_readiness_review(context)  # type: ignore[arg-type]
    payload = json.loads(response.body)
    assert response.status_code == 200
    assert payload["scope"] == "company"
    assert payload["branch_id"] is None
    assert payload["sources"][1]["connection_state"] == "active_verified"
    assert all(item["delta"] == 0 for item in payload["counts"])
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.asyncio
async def test_explicit_authorized_branch_remains_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        product_router,
        "get_sandbox_oauth_runtime",
        lambda: ConnectedRuntime(),
    )
    context = SimpleNamespace(
        company=SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000001")),
        active_branch=SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000002")),
    )
    response = await product_router.migration_readiness_review(context)  # type: ignore[arg-type]
    payload = json.loads(response.body)
    assert response.status_code == 200
    assert payload["scope"] == "branch"
    assert payload["branch_id"] == "00000000-0000-0000-0000-000000000002"
