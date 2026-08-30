from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.estimates.router import list_estimates
from app.estimates.schemas import EstimateSummary
from app.estimates.service import estimate_service


@pytest.mark.asyncio
async def test_estimate_pipeline_is_company_and_branch_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    company_id, branch_id, customer_id = uuid4(), uuid4(), uuid4()
    item = EstimateSummary(
        id=uuid4(),
        branch_id=branch_id,
        customer_id=customer_id,
        service_location_id=None,
        estimate_number="EST-000001",
        status="draft",
        acceptance_status="not_requested",
        version=1,
        proposal_title="Synthetic service proposal",
        currency="USD",
        total_amount=Decimal("125.00"),
        expires_at=None,
        updated_at=datetime.now(UTC),
    )
    listing = AsyncMock(return_value=(item,))
    monkeypatch.setattr(estimate_service.repository, "list_summaries", listing)
    context = SimpleNamespace(
        company=SimpleNamespace(id=company_id),
        authorized_branches=(SimpleNamespace(id=branch_id),),
    )
    session = AsyncMock()

    result = await list_estimates(
        context=context,
        session=session,
        customer_id=customer_id,
        status_filter="draft",
        limit=50,
    )

    assert result.total == 1
    assert result.items == (item,)
    listing.assert_awaited_once_with(
        session,
        company_id=company_id,
        branch_ids=frozenset({branch_id}),
        customer_id=customer_id,
        status="draft",
        limit=50,
    )
