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

