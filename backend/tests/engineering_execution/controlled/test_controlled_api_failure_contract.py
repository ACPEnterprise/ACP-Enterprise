from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.engineering_execution.controlled.errors import ControlledExecutionError
from app.engineering_execution.controlled.router import adopt_expired_result, service
from app.engineering_execution.controlled.schemas import AdoptControlledResultRequest


@pytest.mark.asyncio
async def test_adoption_failure_is_classified_and_non_reflective(monkeypatch) -> None:
    canary = "provider-token=controlled-canary /private/repository/path"
    monkeypatch.setattr(
        service,
        "adopt_expired_result",
        AsyncMock(side_effect=ControlledExecutionError(canary)),
    )

    with pytest.raises(HTTPException) as raised:
        await adopt_expired_result(
            execution_id=uuid4(),
            data=AdoptControlledResultRequest.model_construct(),
            context=object(),
            database=object(),
        )

    failure = raised.value
    assert failure.status_code == 409
    assert failure.detail["recovery"] == "RETRY_AFTER_REFRESH"
    assert canary not in str(failure.detail)
