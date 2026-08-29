from __future__ import annotations

from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.platform.idempotency.errors import reliability_http_error
from app.platform.idempotency.reliability import (
    IdempotencyConflict,
    MutationInProgress,
    MutationReconciliationRequired,
)
from app.platform.reliability.correlation import CorrelationMiddleware
from app.platform.reliability.failures import ClientRecovery


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(CorrelationMiddleware)

    @app.get("/correlation")
    async def correlation() -> dict[str, bool]:
        return {"ok": True}

    return app


def test_request_correlation_is_safe_stable_uuid() -> None:
    supplied = "23a4fbe5-b785-4a42-99d6-692fddef4992"
    response = TestClient(_app()).get("/correlation", headers={"X-Request-ID": supplied})
    assert response.headers["X-Request-ID"] == supplied
    generated = TestClient(_app()).get("/correlation", headers={"X-Request-ID": "protected payload"})
    UUID(generated.headers["X-Request-ID"])
    assert generated.headers["X-Request-ID"] != "protected payload"


def test_idempotency_failure_recovery_is_machine_readable() -> None:
    cases: tuple[tuple[Exception, ClientRecovery], ...] = (
        (IdempotencyConflict(), ClientRecovery.USER_CORRECTION_REQUIRED),
        (MutationInProgress(), ClientRecovery.RETRY_SAFE),
        (MutationReconciliationRequired(), ClientRecovery.RECONCILIATION_REQUIRED),
    )
    for error, expected in cases:
        value = reliability_http_error(error)  # type: ignore[arg-type]
        assert isinstance(value, HTTPException)
        assert value.detail["recovery"] == expected.value
        assert "sql" not in str(value.detail).lower()
