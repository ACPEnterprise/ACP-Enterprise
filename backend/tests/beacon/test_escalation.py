from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.beacon.escalation import (
    ESCALATION_REGISTRY,
    EscalationEligibility,
    EscalationRule,
    EscalationService,
    EscalationState,
)
from app.beacon.evaluation import SignalEvaluationService
from app.beacon.evidence_evaluation import EvaluationReadiness
from app.beacon.router import escalation_readiness
from app.beacon.workflow import _state
from tests.beacon.test_beacon import COMPANY_ID, snapshot

NOW = datetime(2026, 7, 28, 16, 0, tzinfo=timezone.utc)
BRANCH_ID = UUID("20000000-0000-0000-0000-000000000001")


def operational_signals():
    return tuple(
        item
        for item in SignalEvaluationService().evaluate_signals(snapshot())
        if item.evidence_quality is not None
    )


def test_all_21_definitions_have_fail_closed_escalation_classification() -> None:
    registrations = ESCALATION_REGISTRY.registrations

    assert len(registrations) == 21
    assert len({item.definition_id for item in registrations}) == 21
    assert (
        sum(
            item.eligibility is EscalationEligibility.POLICY_MISSING
            for item in registrations
        )
        == 2
    )
    assert (
        sum(
            item.eligibility is EscalationEligibility.NOT_EVALUABLE
            for item in registrations
        )
        == 19
    )
    assert all(item.rule is None and item.blocker for item in registrations)


def test_evaluable_signals_do_not_invent_time_policy_or_reuse_freshness() -> None:
    for definition_id in (
        "operational.scheduling.appointment_overdue",
        "operational.job.intermediate_state_stalled",
    ):
        registration = ESCALATION_REGISTRY.registration(definition_id)
        assert registration.evaluation_readiness is EvaluationReadiness.EVALUABLE
        assert registration.eligibility is EscalationEligibility.POLICY_MISSING
        assert registration.rule is None
        assert "freshness TTL is not an escalation policy" in registration.blocker


def test_rule_digest_is_versioned_and_deterministic() -> None:
    rule = EscalationRule(
        rule_id="example.approved.rule",
        version=1,
        definition_id="operational.scheduling.appointment_overdue",
        definition_version=1,
        triggering_condition="approved example only",
        required_evidence=("appointment_state",),
        elapsed_time_fact="oldest_overdue_hours",
        elapsed_time_threshold_seconds=3600,
        resulting_state=EscalationState.ESCALATED,
    )

    assert rule.rule_digest == replace(rule).rule_digest
    assert rule.rule_digest != replace(rule, version=2).rule_digest


def test_acknowledgement_and_ownership_are_context_not_suppression() -> None:
    signal = operational_signals()[0]
    workflow = replace(
        _state(None, signal, COMPANY_ID),
        branch_id=BRANCH_ID,
        acknowledged=True,
        acknowledged_by_user_id=UUID("10000000-0000-0000-0000-000000000001"),
        acknowledged_at=NOW,
        owner_user_id=UUID("10000000-0000-0000-0000-000000000002"),
        owned_since=NOW,
    )
    projection = EscalationService().project(
        signal,
        company_id=COMPANY_ID,
        branch_id=BRANCH_ID,
        workflow=workflow,
    )

    assert projection.state is EscalationState.NORMAL
    assert projection.eligibility is EscalationEligibility.POLICY_MISSING
    assert projection.acknowledged
    assert projection.owner_user_id == workflow.owner_user_id
    assert "owner-approved" in projection.reason


def test_inadmissible_evidence_cannot_enter_escalation() -> None:
    signal = operational_signals()[0]
    assert signal.evidence_quality is not None
    inadmissible = replace(
        signal,
        evidence_quality=replace(
            signal.evidence_quality,
            conclusion_admissible=False,
        ),
    )

    with pytest.raises(ValueError, match="admitted operational signal"):
        EscalationService().project(
            inadmissible,
            company_id=COMPANY_ID,
            branch_id=None,
            workflow=None,
        )


def test_escalation_does_not_change_signal_identity_severity_or_priority() -> None:
    signal = operational_signals()[0]
    before = (signal.id, signal.severity, signal.priority)
    EscalationService().project(
        signal,
        company_id=COMPANY_ID,
        branch_id=None,
        workflow=None,
    )

    assert (signal.id, signal.severity, signal.priority) == before


@pytest.mark.asyncio
async def test_escalation_api_is_context_scoped_and_explanation_safe() -> None:
    context = SimpleNamespace(
        company=SimpleNamespace(id=COMPANY_ID),
        active_branch=SimpleNamespace(id=BRANCH_ID),
    )
    response = await escalation_readiness(context)  # type: ignore[arg-type]

    assert response.company_id == COMPANY_ID
    assert response.active_branch_id == BRANCH_ID
    assert len(response.registrations) == 21
    assert all(not item.rule_available for item in response.registrations)
    assert "evidence_digest" not in response.model_dump_json()


def test_no_manual_or_notification_escalation_surface_exists() -> None:
    rendered = " ".join(
        item.blocker or "" for item in ESCALATION_REGISTRY.registrations
    )
    assert "manual escalation" not in rendered.lower()
    assert "notification" not in rendered.lower()
