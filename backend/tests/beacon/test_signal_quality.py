from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.beacon.evaluation import SignalEvaluationService
from app.beacon.evidence_evaluation import EvaluationReadiness
from app.beacon.quality import (
    EVIDENCE_QUALITY_SERVICE,
    EvidenceCompletenessState,
    EvidenceConfidenceState,
    EvidenceFreshnessState,
    EvidenceQualityInput,
    EvidenceReconciliationState,
    StaleEvidenceBehavior,
)
from app.beacon.router import signal_quality_semantics
from tests.beacon.test_beacon import COMPANY_ID, snapshot

NOW = datetime(2026, 8, 28, 16, 0, tzinfo=timezone.utc)
BRANCH_ID = UUID("20000000-0000-0000-0000-000000000001")


def quality_input(
    definition_id: str = "operational.scheduling.appointment_overdue",
    *,
    observed_as_of: datetime | None = NOW,
    completeness: EvidenceCompletenessState = EvidenceCompletenessState.COMPLETE,
    reconciliation: EvidenceReconciliationState = (
        EvidenceReconciliationState.RECONCILED
    ),
    limitations: tuple[str, ...] = (),
    conflicts: tuple[str, ...] = (),
) -> EvidenceQualityInput:
    return EvidenceQualityInput(
        definition_id=definition_id,
        source_authority="accepted ACP operational records",
        evidence_identities=("appointment:1:event:1",),
        effective_at=NOW - timedelta(minutes=1),
        observed_as_of=observed_as_of,
        evaluated_at=NOW,
        completeness=completeness,
        reconciliation=reconciliation,
        limitations=limitations,
        conflict_identities=conflicts,
        evidence_digest="a" * 64,
    )


def test_high_current_quality_is_deterministic_and_not_probability() -> None:
    first = EVIDENCE_QUALITY_SERVICE.evaluate(quality_input())
    second = EVIDENCE_QUALITY_SERVICE.evaluate(quality_input())

    assert first == second
    assert first.confidence is EvidenceConfidenceState.HIGH
    assert first.freshness is EvidenceFreshnessState.CURRENT
    assert first.conclusion_admissible
    assert first.stale_behavior is StaleEvidenceBehavior.BLOCK_EVALUATION
    assert len(first.quality_digest) == 64
    assert "%" not in first.explanation


def test_limitations_are_moderate_without_changing_admission() -> None:
    result = EVIDENCE_QUALITY_SERVICE.evaluate(
        quality_input(limitations=("Branch projection is unavailable.",))
    )
    assert result.confidence is EvidenceConfidenceState.MODERATE
    assert result.freshness is EvidenceFreshnessState.CURRENT
    assert result.conclusion_admissible


def test_partial_evidence_is_low_and_cannot_admit_a_conclusion() -> None:
    result = EVIDENCE_QUALITY_SERVICE.evaluate(
        quality_input(completeness=EvidenceCompletenessState.PARTIAL)
    )
    assert result.confidence is EvidenceConfidenceState.LOW
    assert not result.conclusion_admissible


def test_missing_timestamp_or_policy_is_unknown_not_fabricated() -> None:
    missing_timestamp = EVIDENCE_QUALITY_SERVICE.evaluate(
        quality_input(observed_as_of=None)
    )
    missing_policy = EVIDENCE_QUALITY_SERVICE.evaluate(
        quality_input("operational.dispatch.state_stalled")
    )

    assert missing_timestamp.freshness is EvidenceFreshnessState.UNKNOWN
    assert missing_timestamp.confidence is EvidenceConfidenceState.UNKNOWN
    assert not missing_timestamp.conclusion_admissible
    assert missing_policy.freshness is EvidenceFreshnessState.UNKNOWN
    assert missing_policy.confidence is EvidenceConfidenceState.UNKNOWN
    assert any(
        "No approved freshness policy" in item for item in missing_policy.limitations
    )
    assert not missing_policy.conclusion_admissible


def test_stale_evidence_blocks_and_cannot_masquerade_as_current() -> None:
    stale = EVIDENCE_QUALITY_SERVICE.evaluate(
        quality_input(observed_as_of=NOW - timedelta(seconds=901))
    )
    boundary = EVIDENCE_QUALITY_SERVICE.evaluate(
        quality_input(observed_as_of=NOW - timedelta(seconds=900))
    )

    assert stale.freshness is EvidenceFreshnessState.STALE
    assert stale.confidence is EvidenceConfidenceState.LOW
    assert not stale.conclusion_admissible
    assert boundary.freshness is EvidenceFreshnessState.CURRENT
    assert boundary.conclusion_admissible


def test_conflicting_evidence_is_explicit_and_fail_closed() -> None:
    result = EVIDENCE_QUALITY_SERVICE.evaluate(
        quality_input(
            reconciliation=EvidenceReconciliationState.CONFLICTING,
            conflicts=("event:a", "event:b"),
        )
    )
    assert result.confidence is EvidenceConfidenceState.CONFLICTING
    assert result.conflict_identities == ("event:a", "event:b")
    assert not result.conclusion_admissible
    assert "no approved precedence" in result.explanation


def test_quality_never_promotes_blocked_readiness() -> None:
    result = EVIDENCE_QUALITY_SERVICE.evaluate(
        quality_input("operational.dispatch.state_stalled")
    )
    semantics = next(
        item
        for item in EVIDENCE_QUALITY_SERVICE.semantics()
        if item.definition_id == "operational.dispatch.state_stalled"
    )
    assert semantics.readiness is EvaluationReadiness.PARTIALLY_EVALUABLE
    assert not result.conclusion_admissible


def test_all_21_definitions_have_quality_semantics_without_fabricated_policy() -> None:
    semantics = EVIDENCE_QUALITY_SERVICE.semantics()
    assert len(semantics) == 21
    assert sum(item.confidence_semantics_available for item in semantics) == 21
    assert sum(item.freshness_semantics_available for item in semantics) == 2
    assert all(
        item.freshness_policy_id is None and item.policy_source is None
        for item in semantics
        if not item.freshness_semantics_available
    )


def test_existing_evaluators_are_qualified_without_signal_identity_change() -> None:
    service = SignalEvaluationService()
    source = snapshot()
    first = service.evaluate_signals(source)
    second = service.evaluate_signals(source)
    qualified = tuple(item for item in first if item.evidence_quality is not None)

    assert [item.id for item in first] == [item.id for item in second]
    assert len(qualified) == 2
    assert all(
        item.evidence_quality
        and item.evidence_quality.confidence is EvidenceConfidenceState.HIGH
        and item.evidence_quality.freshness is EvidenceFreshnessState.CURRENT
        for item in qualified
    )
    legacy_invoice = next(item for item in first if item.source == "invoices")
    assert legacy_invoice.evidence_quality is None


@pytest.mark.asyncio
async def test_quality_api_is_context_scoped_and_explanation_safe() -> None:
    context = SimpleNamespace(
        company=SimpleNamespace(id=COMPANY_ID),
        active_branch=SimpleNamespace(id=BRANCH_ID),
    )
    response = await signal_quality_semantics(context)  # type: ignore[arg-type]

    assert response.company_id == COMPANY_ID
    assert response.active_branch_id == BRANCH_ID
    assert len(response.definitions) == 21
    assert not hasattr(response.definitions[0], "evidence_identities")


def test_quality_service_has_no_ai_probability_or_mutation_semantics() -> None:
    rendered = " ".join(
        value
        for item in EVIDENCE_QUALITY_SERVICE.semantics()
        for value in (item.policy_source or "", item.blocker or "")
    )
    assert all(
        prohibited not in rendered.lower()
        for prohibited in (
            "probability",
            "machine learning",
            "ai judgment",
            "profitability",
            "revenue recognition",
            "autonomous",
        )
    )
