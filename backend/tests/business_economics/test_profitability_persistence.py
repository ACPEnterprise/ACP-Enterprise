from unittest.mock import Mock

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
async def test_profitability_persistence_rejects_unauthorized_branch() -> None:
    context = Mock()
    context.has_permission.return_value = True
    context.company.id = Mock(name="company_id")
    context.authorized_branch_ids = frozenset()
    request = Mock(company_id=context.company.id, branch_id=Mock(name="branch_id"))

    with pytest.raises(
        ProfitabilityPersistenceError, match="cross-Branch profitability result"
    ):
        await EconomicsProfitabilityPersistenceService().persist(
            Mock(), context=context, request=request, result=Mock()
        )


@pytest.mark.asyncio
async def test_profitability_persistence_rejects_inactive_authorized_branch() -> None:
    context = Mock()
    context.has_permission.return_value = True
    context.company.id = Mock(name="company_id")
    request = Mock(company_id=context.company.id, branch_id=Mock(name="branch_id"))
    context.authorized_branch_ids = frozenset({request.branch_id})
    context.active_branch.id = Mock(name="active_branch_id")

    with pytest.raises(
        ProfitabilityPersistenceError, match="inactive-Branch profitability result"
    ):
        await EconomicsProfitabilityPersistenceService().persist(
            Mock(), context=context, request=request, result=Mock()
        )
