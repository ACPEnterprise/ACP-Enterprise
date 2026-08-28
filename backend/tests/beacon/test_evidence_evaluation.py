from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.beacon.catalog import OPERATIONAL_SIGNAL_CATALOG
from app.beacon.evidence_evaluation import (
    EVIDENCE_EVALUATION_REGISTRY,
    EvaluationReadiness,
    EvidenceEvaluationRegistry,
)
from app.beacon.router import evidence_evaluation_readiness
from tests.beacon.test_beacon import COMPANY_ID, snapshot

BRANCH_ID = UUID("20000000-0000-0000-0000-000000000001")


def test_registry_classifies_every_catalog_definition_exactly_once() -> None:
    registry = EVIDENCE_EVALUATION_REGISTRY
    assert len(registry.registrations) == 21
    assert {item.definition_id for item in registry.registrations} == {
        item.definition_id for item in OPERATIONAL_SIGNAL_CATALOG.definitions
    }
    assert {
        state: sum(item.readiness is state for item in registry.registrations)
        for state in EvaluationReadiness
    } == {
        EvaluationReadiness.EVALUABLE: 2,
        EvaluationReadiness.PARTIALLY_EVALUABLE: 16,
        EvaluationReadiness.NOT_EVALUABLE: 3,
        EvaluationReadiness.CONFLICTING: 0,
    }


def test_evaluable_definitions_have_complete_adapters_and_no_blockers() -> None:
    evaluable = tuple(
        item
        for item in EVIDENCE_EVALUATION_REGISTRY.registrations
        if item.readiness is EvaluationReadiness.EVALUABLE
    )
    assert {item.definition_id for item in evaluable} == {
        "operational.scheduling.appointment_overdue",
        "operational.job.intermediate_state_stalled",
    }
    assert all(item.evaluator_implemented for item in evaluable)
    assert all(item.blocker is None for item in evaluable)


def test_blocked_definitions_preserve_exact_missing_evidence() -> None:
    blocked = tuple(
        item
        for item in EVIDENCE_EVALUATION_REGISTRY.registrations
        if item.readiness is not EvaluationReadiness.EVALUABLE
    )
    assert all(item.blocker for item in blocked)
    assert all(item.required_fact_contract for item in blocked)
    assert all(not item.evaluator_implemented for item in blocked)
    assert "similar" not in " ".join(item.blocker or "" for item in blocked).lower()


def test_registry_rejects_missing_duplicate_and_false_evaluable_entries() -> None:
    registrations = EVIDENCE_EVALUATION_REGISTRY.registrations
    with pytest.raises(ValueError, match="cover the catalog"):
        EvidenceEvaluationRegistry(registrations[:-1])
    with pytest.raises(ValueError, match="unique"):
        EvidenceEvaluationRegistry((*registrations, registrations[0]))
    with pytest.raises(ValueError, match="adapter/evaluator"):
        EvidenceEvaluationRegistry(
            (
                replace(
                    registrations[0],
                    readiness=EvaluationReadiness.EVALUABLE,
                    blocker=None,
                ),
                *registrations[1:],
            )
        )


def test_existing_evaluators_remain_deterministic_and_backward_compatible() -> None:
    registry = EVIDENCE_EVALUATION_REGISTRY
    source = snapshot()
    first = registry.evaluate_existing(source)
    second = registry.evaluate_existing(source)

    assert first == second
    assert [item.id for item in first] == [item.id for item in second]
    assert {item.rule_code for item in first} == {
        "scheduling.overdue_committed_appointments",
        "operations.paused_jobs",
        "revenue.past_due_invoices",
    }


def test_cleared_conditions_produce_no_duplicate_or_residual_signal() -> None:
    registry = EVIDENCE_EVALUATION_REGISTRY
    assert registry.evaluate_existing(snapshot(populated=False)) == ()


def test_conflicting_readiness_is_fail_closed_not_evaluable() -> None:
    registration = EVIDENCE_EVALUATION_REGISTRY.registrations[0]
    conflicting = replace(
        registration,
        readiness=EvaluationReadiness.CONFLICTING,
        blocker="Accepted evidence identities conflict without precedence.",
    )
    registry = EvidenceEvaluationRegistry(
        (conflicting, *EVIDENCE_EVALUATION_REGISTRY.registrations[1:])
    )
    assert registry.registration(conflicting.definition_id).readiness is (
        EvaluationReadiness.CONFLICTING
    )
    assert not registry.registration(conflicting.definition_id).evaluator_implemented


@pytest.mark.asyncio
async def test_readiness_api_is_company_branch_scoped_and_contains_no_raw_evidence() -> (
    None
):
    context = SimpleNamespace(
        company=SimpleNamespace(id=COMPANY_ID),
        active_branch=SimpleNamespace(id=BRANCH_ID),
    )
    response = await evidence_evaluation_readiness(context)  # type: ignore[arg-type]

    assert response.company_id == COMPANY_ID
    assert response.active_branch_id == BRANCH_ID
    assert len(response.registrations) == 21
    assert sum(item.evaluator_implemented for item in response.registrations) == 2
    assert all(not hasattr(item, "source_facts") for item in response.registrations)


def test_registry_contains_no_economics_accounting_or_automation_authority() -> None:
    flattened = " ".join(
        value
        for item in EVIDENCE_EVALUATION_REGISTRY.registrations
        for value in (
            item.authoritative_source_contract,
            *item.required_fact_contract,
            item.blocker or "",
            *item.limitations,
        )
    ).lower()
    for prohibited in (
        "profitability",
        "margin leakage",
        "revenue recognition",
        "cash/accrual",
        "qbo",
        "engineering command",
        "autonomous remediation",
    ):
        assert prohibited not in flattened
