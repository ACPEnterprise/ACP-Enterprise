from uuid import uuid4

import pytest
from fastapi import FastAPI

from app.inventory.errors import (
    InventoryConflict,
    InventoryNotFound,
    InventoryValidation,
)
from app.inventory.router import router, translate
from app.inventory.service import InventoryService

app = FastAPI()
app.include_router(router)


def test_inventory_errors_use_safe_recovery_envelopes_without_reflection() -> None:
    secret = f"sql-provider-secret-{uuid4()}"
    cases = (
        (InventoryNotFound(secret), 404, "not_found", "TERMINAL_FAILURE"),
        (
            InventoryConflict(secret),
            409,
            "resource_state_conflict",
            "RETRY_AFTER_REFRESH",
        ),
        (
            InventoryValidation(secret),
            422,
            "validation",
            "USER_CORRECTION_REQUIRED",
        ),
    )
    for error, status, code, recovery in cases:
        response = translate(error)
        assert response.status_code == status
        assert response.detail["code"] == code
        assert response.detail["recovery"] == recovery
        assert secret not in str(response.detail)


def test_cycle_count_history_publishes_bounded_pagination_contract() -> None:
    operation = app.openapi()["paths"]["/api/v1/inventory/cycle-counts"]["get"]
    parameters = {item["name"]: item for item in operation["parameters"]}

    assert parameters["limit"]["schema"]["default"] == 100
    assert parameters["limit"]["schema"]["maximum"] == 200
    assert parameters["offset"]["schema"]["default"] == 0
    assert parameters["offset"]["schema"]["minimum"] == 0


@pytest.mark.asyncio
async def test_cycle_count_service_rejects_unbounded_internal_requests() -> None:
    with pytest.raises(InventoryValidation, match="pagination"):
        await InventoryService().list_cycle_counts(
            object(),  # type: ignore[arg-type]
            context=object(),  # type: ignore[arg-type]
            branch_id=None,
            limit=201,
        )
