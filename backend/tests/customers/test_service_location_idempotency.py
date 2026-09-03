from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from app.customers.models import ServiceLocation
from app.customers.schemas import ServiceLocationCreate
from app.customers.service import CustomerService
from app.platform.idempotency.reliability import (
    AuthoritativeOutcome,
    MutationDisposition,
)


@pytest.mark.asyncio
async def test_service_location_creation_uses_reliability_authority():
    service = CustomerService()
    location = ServiceLocation(id=uuid4(), customer_id=uuid4())
    service._stage_location = AsyncMock(return_value=location)  # type: ignore[method-assign]
    data = ServiceLocationCreate(
        address="100 Test Fixture Way",
        city="Example",
        state="NY",
        postal_code="10001",
    )
    context = SimpleNamespace(
        company=SimpleNamespace(id=uuid4()),
        active_branch=SimpleNamespace(id=uuid4()),
        user=SimpleNamespace(id=uuid4()),
    )

    async def execute(_session, **values):
        outcome: AuthoritativeOutcome[ServiceLocation] = await values["mutate"]()
        assert outcome.result_type == "service_location"
        return SimpleNamespace(
            value=outcome.value, disposition=MutationDisposition.EXECUTED
        )

    reliability = AsyncMock(side_effect=execute)
    with patch(
        "app.customers.service.mutation_reliability_service.execute", reliability
    ):
        result, disposition = await service.add_location_idempotent(
            object(),  # type: ignore[arg-type]
            context=context,
            customer_id=location.customer_id,
            data=data,
            idempotency_key="acp-employee-beta-v1:service-location",
        )

    assert result is location
    assert disposition == MutationDisposition.EXECUTED
    identity = reliability.await_args.kwargs["identity"]
    assert identity.operation == "customers.service_location.create"
    assert identity.idempotency_key == "acp-employee-beta-v1:service-location"
