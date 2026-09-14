from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.workforce.administration_commands import WorkforceAdministrationService
from app.workforce.router import prepare_field_readiness
from app.workforce.schemas import FieldReadinessRequest


@pytest.mark.asyncio
async def test_field_readiness_uses_canonical_capability_and_exact_window() -> None:
    service = WorkforceAdministrationService()
    profile_id, capability_id, availability_id = uuid4(), uuid4(), uuid4()
    service.ensure_profile = AsyncMock(return_value=(SimpleNamespace(id=profile_id), True))
    service.add_capability = AsyncMock(return_value=(capability_id, True))
    service.add_availability = AsyncMock(return_value=(availability_id, True))
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=SimpleNamespace(id=uuid4())),
        rollback=AsyncMock(),
    )
    context = SimpleNamespace(company=SimpleNamespace(id=uuid4()))
    employee_id, branch_id = uuid4(), uuid4()
    start = datetime.now(timezone.utc)
    result = await service.prepare_field_readiness(
        session, context=context, employee_id=employee_id, branch_id=branch_id,
        start_at=start, end_at=start + timedelta(hours=2),
    )
    assert result == (profile_id, capability_id, availability_id)
    service.add_capability.assert_awaited_once()
    assert service.add_capability.await_args.kwargs["proficiency"] == "qualified"
    assert service.add_availability.await_args.kwargs["source"] == "operator_confirmed_dispatch_window"


@pytest.mark.asyncio
async def test_field_readiness_requires_both_workforce_permissions() -> None:
    context = SimpleNamespace(has_permission=lambda _permission: False)
    request = FieldReadinessRequest(
        branch_id=uuid4(),
        window_start_at=datetime.now(timezone.utc),
        window_end_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    with pytest.raises(HTTPException) as captured:
        await prepare_field_readiness(uuid4(), request, context, object())
    assert captured.value.status_code == 403
