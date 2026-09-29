from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest
from app.beacon.active_recommendations import (
    ActiveRecommendationReasoner,
    CustomerAdmissionGapFact,
    LuminaryFindingFact,
    SchedulingGapFact,
    active_recommendation_service,
    recommendation_digest,
)
from app.beacon.router import router
from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AnalyticsPermission
from app.platform.permissions.dependencies import get_authorization_context
from fastapi import FastAPI

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)


def test_reasoner_separates_scheduling_fact_interpretation_and_human_action() -> None:
    item = ActiveRecommendationReasoner().reason(
        scheduling=(
            SchedulingGapFact(
                UUID("11111111-1111-4111-8111-111111111111"),
                "Main Branch",
                None,
                0,
                NOW,
            ),
        ),
        evaluated_at=NOW,
    )[0]

    assert item.measured_fact == "Main Branch: no Branch scheduling calendar exists."
    assert "cannot reliably evaluate" in item.interpretation
    assert item.recommended_human_action == (
        "Configure and review the Branch scheduling calendar."
    )
    assert item.priority_window == "TODAY"
    assert item.action_destination == "Administration → Branch Scheduling Setup"
    assert item.priority_score == sum(
        factor.contribution for factor in item.priority_factors
    )
    assert next(
        factor for factor in item.priority_factors if factor.factor == "economic_materiality"
    ).available is False


def test_reasoner_uses_exact_customer_population_run_without_identity_inference() -> (
    None
):
    item = ActiveRecommendationReasoner().reason(
        customers=(
            CustomerAdmissionGapFact(
                UUID("22222222-2222-4222-8222-222222222222"),
                UUID("11111111-1111-4111-8111-111111111111"),
                "housecall_pro",
                100,
                80,
                15,
                3,
                2,
                "a" * 64,
                NOW,
            ),
        ),
        evaluated_at=NOW,
    )[0]

    assert "80 of 100" in item.measured_fact
    assert "20 remain held, ambiguous, or unexplained" in item.measured_fact
    assert "does not infer Customer identity" in item.limitations[0]
    assert item.evidence[0].digest == "a" * 64


def test_reasoner_preserves_canonical_luminary_gap_and_limitations() -> None:
    item = ActiveRecommendationReasoner().reason(
        luminary=(
            LuminaryFindingFact(
                UUID("33333333-3333-4333-8333-333333333333"),
                None,
                "insufficient_evidence",
                "missing_evidence",
                "Payroll burden evidence is incomplete",
                "Payroll burden evidence is unavailable for the measured period.",
                "Authoritative break-even interpretation is blocked.",
                40,
                "partial",
                "current",
                ("No burden policy is accepted.",),
                ("Complete Payroll readiness inputs.",),
                "b" * 64,
                "d" * 64,
                "2026-09-01",
                "2026-09-28",
                NOW,
            ),
        ),
        evaluated_at=NOW,
    )[0]

    assert item.kind == "EVIDENCE_GAP"
    assert item.measured_fact.startswith("Payroll burden evidence")
    assert item.interpretation == "Authoritative break-even interpretation is blocked."
    assert item.recommended_human_action == "Complete Payroll readiness inputs."
    assert item.confidence == "40% (Luminary canonical confidence)"
    assert item.limitations == ("No burden policy is accepted.",)
    assert item.decisions_blocked == (
        "Economic interpretation",
        "Owner economic decision",
    )


def test_measured_luminary_finding_recommends_investigation_not_employment_action() -> (
    None
):
    item = ActiveRecommendationReasoner().reason(
        luminary=(
            LuminaryFindingFact(
                UUID("44444444-4444-4444-8444-444444444444"),
                None,
                "measured_comparison",
                "labor_cost_change",
                "Direct labor changed",
                "Direct labor cost increased by a measured amount.",
                "The accepted finding does not establish an operational cause.",
                85,
                "complete",
                "current",
                ("Correlation is not causation.",),
                ("Review the supporting Job evidence.",),
                "c" * 64,
                "e" * 64,
                "2026-09-01",
                "2026-09-28",
                NOW,
            ),
        ),
        evaluated_at=NOW,
    )[0]

    combined = (
        f"{item.interpretation} {item.recommended_human_action} {item.priority_reason}"
    ).lower()
    assert item.kind == "MEASURED_FINDING"
    assert "investigation" in item.priority_reason
    assert "terminate" not in combined
    assert "discipline" not in combined
    assert "demote" not in combined


def test_related_findings_group_only_on_explicit_shared_root_key() -> None:
    first = LuminaryFindingFact(
        UUID("44444444-4444-4444-8444-444444444444"),
        None,
        "insufficient_evidence",
        "missing_evidence",
        "Payroll burden missing",
        "Employer burden is unavailable.",
        "Break-even is blocked.",
        40,
        "partial",
        "current",
        ("Burden policy unavailable.",),
        ("Complete Payroll readiness.",),
        "a" * 64,
        "f" * 64,
        "2026-09-01",
        "2026-09-28",
        NOW,
    )
    related_fact = replace(
        first,
        finding_id=UUID("55555555-5555-4555-8555-555555555555"),
        title="Technician burden unavailable",
        summary="Technician burden cannot be measured.",
        finding_digest="b" * 64,
        finding_identity="payroll-technician-burden",
    )
    separate_fact = replace(
        first,
        finding_id=UUID("66666666-6666-4666-8666-666666666666"),
        title="Separate source gap",
        finding_digest="c" * 64,
        finding_identity="separate-source-gap",
    )

    ungrouped = ActiveRecommendationReasoner().reason(
        luminary=(first, related_fact, separate_fact),
        evaluated_at=NOW,
    )
    primary, related, separate = ungrouped
    grouped_items = ActiveRecommendationReasoner._group(
        [primary, replace(related, root_issue_key=primary.root_issue_key), separate]
    )

    assert len(grouped_items) == 2
    grouped = next(item for item in grouped_items if item.related_recommendations)
    assert len(grouped.related_recommendations) == 1
    assert len(grouped.evidence) == 2
    assert grouped.priority_factors[-1].factor == "root_condition_breadth"
    assert "canonical root-condition key" in grouped.priority_reason


def test_recommendation_identity_order_and_digest_are_deterministic() -> None:
    reasoner = ActiveRecommendationReasoner()
    facts = (
        SchedulingGapFact(
            UUID("11111111-1111-4111-8111-111111111111"),
            "Main Branch",
            None,
            0,
            NOW,
        ),
    )
    first = reasoner.reason(scheduling=facts, evaluated_at=NOW)
    second = reasoner.reason(scheduling=facts, evaluated_at=NOW)

    assert first == second
    assert recommendation_digest(first) == recommendation_digest(second)


@pytest.mark.asyncio
async def test_active_recommendation_api_is_read_only_and_evidence_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    branch_id = UUID("11111111-1111-4111-8111-111111111111")
    item = ActiveRecommendationReasoner().reason(
        scheduling=(SchedulingGapFact(branch_id, "Main Branch", None, 0, NOW),),
        evaluated_at=NOW,
    )[0]
    query = AsyncMock(return_value=(item,))
    monkeypatch.setattr(active_recommendation_service, "list", query)

    context = object.__new__(AuthorizationContext)
    object.__setattr__(
        context,
        "company",
        SimpleNamespace(id=UUID("55555555-5555-4555-8555-555555555555")),
    )
    object.__setattr__(context, "active_branch", SimpleNamespace(id=branch_id))
    object.__setattr__(context, "authorized_branches", (context.active_branch,))
    object.__setattr__(context, "membership", SimpleNamespace(id=branch_id))
    object.__setattr__(
        context,
        "effective_permissions",
        (SimpleNamespace(code=AnalyticsPermission.READ),),
    )

    app = FastAPI()
    app.include_router(router)

    async def session_override():
        yield object()

    async def context_override() -> AuthorizationContext:
        return context

    app.dependency_overrides[get_database_session] = session_override
    app.dependency_overrides[get_authorization_context] = context_override
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/beacon/active-recommendations")

    assert response.status_code == 200
    body = response.json()
    assert body["autonomous_action"] is False
    assert body["items"][0]["measured_fact"] == item.measured_fact
    assert body["items"][0]["interpretation"] == item.interpretation
    assert body["items"][0]["recommended_human_action"] == (
        item.recommended_human_action
    )
    assert body["items"][0]["evidence"][0]["entity_type"] == (
        "branch_scheduling_calendar"
    )
