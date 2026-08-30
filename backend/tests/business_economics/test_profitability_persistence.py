from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.business_economics.profitability_persistence import (
    EconomicsProfitabilityPersistenceService,
    ProfitabilityPersistenceError,
)


@pytest.mark.asyncio
async def test_profitability_persistence_requires_narrow_execution_permission() -> None:
    context = Mock()
    context.has_permission.return_value = False

    with pytest.raises(
        ProfitabilityPersistenceError,
        match="Economics measurement execution permission denied",
    ):
        await EconomicsProfitabilityPersistenceService().persist(
            Mock(), context=context, request=Mock(), result=Mock()
        )


@pytest.mark.asyncio
async def test_profitability_persistence_rejects_active_branch_escape() -> None:
    company_id, active_branch_id, other_branch_id = uuid4(), uuid4(), uuid4()
    context = SimpleNamespace(
        company=SimpleNamespace(id=company_id),
        active_branch=SimpleNamespace(id=active_branch_id),
        has_permission=lambda _permission: True,
    )
    request = SimpleNamespace(company_id=company_id, branch_id=other_branch_id)
    session = SimpleNamespace(scalar=AsyncMock())

    with pytest.raises(
        ProfitabilityPersistenceError, match="cross-Branch profitability result"
    ):
        await EconomicsProfitabilityPersistenceService().persist(
            session, context=context, request=request, result=Mock()
        )

    session.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_profitability_persistence_rejects_branch_outside_company() -> None:
    company_id, branch_id = uuid4(), uuid4()
    context = SimpleNamespace(
        company=SimpleNamespace(id=company_id),
        active_branch=None,
        has_permission=lambda _permission: True,
    )
    request = SimpleNamespace(company_id=company_id, branch_id=branch_id)
    session = SimpleNamespace(scalar=AsyncMock(return_value=None))

    with pytest.raises(
        ProfitabilityPersistenceError,
        match="profitability result branch is not available",
    ):
        await EconomicsProfitabilityPersistenceService().persist(
            session, context=context, request=request, result=Mock()
        )

    session.scalar.assert_awaited_once()
