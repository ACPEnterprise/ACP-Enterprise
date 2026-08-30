from dataclasses import replace

import pytest

from app.beacon.escalation import escalation_service
from app.beacon.evaluation import SignalEvaluationService
from app.beacon.intelligence import (
    INTELLIGENCE_CONTRACT_VERSION,
    build_intelligence_packet,
)
from app.beacon.operational_prioritization import operational_signal_prioritizer
from app.beacon.router import beacon_system_readiness
from app.platform.permissions.codes import AnalyticsPermission, BeaconPermission
from tests.beacon.test_beacon import BRANCH_ID, COMPANY_ID, NOW, context, snapshot


def _item_and_context(*permissions: str):
    principal = context(AnalyticsPermission.READ, *permissions)
    object.__setattr__(principal, "active_branch", principal.authorized_branches[0])
    signals = SignalEvaluationService().evaluate_signals(
        replace(snapshot(), scope_identity="authorized-branch-scope")
    )
    queue = operational_signal_prioritizer.prioritize(
        signals,
        company_id=COMPANY_ID,
        branch_id=BRANCH_ID,
        evaluated_at=NOW,
    )
    return queue.items[0], principal


def test_intelligence_packet_is_deterministic_and_permission_bounded() -> None:
    item, principal = _item_and_context(BeaconPermission.REVIEW)
    escalation = escalation_service.project(
        item.signal,
        company_id=COMPANY_ID,
        branch_id=BRANCH_ID,
        workflow=None,
    )

    first = build_intelligence_packet(
        item, context=principal, workflow=None, escalation=escalation
    )
    second = build_intelligence_packet(
        item, context=principal, workflow=None, escalation=escalation
    )

    assert first == second
    assert first.contract_version == INTELLIGENCE_CONTRACT_VERSION
    assert first.company_id == COMPANY_ID
    assert first.branch_id == BRANCH_ID
    assert len(first.packet_digest) == 64
    assert next(
        action for action in first.actions if action.action == "acknowledge"
    ).available
    assert not next(
        action for action in first.actions if action.action == "take_ownership"
    ).available
    assert all(
        source.domain == item.signal.source.value for source in first.source_references
    )
    assert first.recommended_human_action == item.signal.recommended_action


def test_intelligence_packet_changes_with_authoritative_evidence() -> None:
    item, principal = _item_and_context(BeaconPermission.REVIEW)
    escalation = escalation_service.project(
        item.signal,
        company_id=COMPANY_ID,
        branch_id=BRANCH_ID,
        workflow=None,
    )
    original = build_intelligence_packet(
        item, context=principal, workflow=None, escalation=escalation
    )
    changed_item = replace(item, signal=replace(item.signal, evidence_digest="f" * 64))
    changed = build_intelligence_packet(
        changed_item, context=principal, workflow=None, escalation=escalation
    )

    assert changed.packet_digest != original.packet_digest


@pytest.mark.asyncio
async def test_system_readiness_exposes_unconfigured_policy_without_inventing_it() -> (
    None
):
    readiness = await beacon_system_readiness(context(AnalyticsPermission.READ))

    assert readiness.definitions_total == 21
    assert readiness.evaluable == 2
    assert readiness.partially_evaluable == 16
    assert readiness.not_evaluable == 3
    assert readiness.conflicting == 0
    assert readiness.escalation_ready == 0
    assert readiness.escalation_policy_unconfigured == 2
    assert readiness.production_policy_state == "UNCONFIGURED"
    assert not readiness.autonomous_action
    assert readiness.source_blockers
