from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.business_economics.policy_administration import (
    EconomicsPolicyAdministrationService,
)
from app.business_economics.workspace import EconomicsWorkspaceService


class Rows:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def all(self) -> list[object]:
        return self.values


def _workspace(quality: str = "partial") -> dict[str, object]:
    return {
        "period": {"start": "2026-08-01", "end": "2026-08-31"},
        "quality_state": quality,
        "source_result_count": 1,
        "job_count": 1,
        "unclassified_job_count": 1,
        "totals": {"revenue": 100, "labor": 40, "materials": None},
        "jobs": [{"other_direct_cost_minor": 0}],
        "fully_allocated_available": False,
        "readiness": {"policy_gaps": []},
    }


@pytest.mark.asyncio
async def test_policy_administration_is_read_only_truthful_and_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id, user_id, policy_id = uuid4(), uuid4(), uuid4()
    policy = SimpleNamespace(
        id=policy_id,
        family_key="revenue_recognition",
        policy_version=1,
        strategy_key="invoice_issuance",
        disposition="selected",
        lifecycle="approved",
        effective_start=date(2026, 1, 1),
        effective_end=None,
        supersedes_policy_id=None,
        definition_version="eco.finance-policy.v1",
        decision_evidence_digest="a" * 64,
        policy_digest="b" * 64,
    )
    gap = SimpleNamespace(
        family_key="overhead_allocation",
        gap_key="allocation_driver_required",
        requirement="Owner must approve an allocation driver.",
        state="open",
        authority_dependency="owner_policy_decision",
        effective_start=date(2026, 1, 1),
        gap_digest="c" * 64,
    )
    snapshot = SimpleNamespace(
        id=uuid4(),
        subject_identity="company-economics",
        as_of_date=date(2026, 8, 31),
        policy_ids=[str(policy_id)],
        deferred_family_keys=["overhead_allocation"],
        parameter_gap_digests=["c" * 64],
        definition_version="eco.finance-policy-snapshot.v1",
        snapshot_digest="d" * 64,
        created_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
    )
    session = SimpleNamespace(
        scalars=AsyncMock(
            side_effect=[Rows([policy]), Rows([]), Rows([gap]), Rows([snapshot])]
        )
    )
    context = SimpleNamespace(
        company=SimpleNamespace(id=company_id),
        active_branch=None,
        user=SimpleNamespace(id=user_id),
    )
    monkeypatch.setattr(
        EconomicsWorkspaceService,
        "overview",
        AsyncMock(return_value=_workspace()),
    )

    first = await EconomicsPolicyAdministrationService().dashboard(
        session,
        context=context,
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
    )
    session.scalars.side_effect = [
        Rows([policy]),
        Rows([]),
        Rows([gap]),
        Rows([snapshot]),
    ]
    second = await EconomicsPolicyAdministrationService().dashboard(
        session,
        context=context,
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
    )

    assert first["administration_fingerprint"] == second["administration_fingerprint"]
    assert first["mutation_authority"] == "none"
    assert first["readiness"]["sources"][4]["state"] == "UNAVAILABLE"
    overhead = next(
        item
        for item in first["policy_families"]
        if item["family_key"] == "overhead_allocation"
    )
    assert overhead["state"] == "OWNER_DECISION_REQUIRED"
    assert overhead["current_strategy"] is None
    assert overhead["supported_strategies"] == ["approved_allocation_drivers"]
    assert first["policy_history"][0]["authority_state"] == "current"
    assert "parameters" not in first["policy_history"][0]


def test_source_states_survive_stale_and_conflicting_projection() -> None:
    from app.business_economics.source_completeness import source_completeness_matrix

    stale = source_completeness_matrix(_workspace("stale"))
    conflicting = source_completeness_matrix(_workspace("conflicting"))
    assert stale["sources"][0]["state"] == "STALE"
    assert conflicting["sources"][0]["state"] == "CONFLICTING"
