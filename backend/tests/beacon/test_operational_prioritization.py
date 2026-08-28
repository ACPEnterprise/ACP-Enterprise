from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.beacon.contracts import BeaconLifecycleStatus, BeaconSeverity
from app.beacon.evaluation import SignalEvaluationService
from app.beacon.operational_prioritization import (
    RANKING_VERSION,
    OperationalSignalPrioritizer,
)
from tests.beacon.test_beacon import COMPANY_ID, snapshot

NOW = datetime(2026, 7, 28, 16, 0, tzinfo=timezone.utc)
BRANCH_ID = UUID("20000000-0000-0000-0000-000000000001")


def operational_signals():
    return tuple(
        item
        for item in SignalEvaluationService().evaluate_signals(snapshot())
        if item.evidence_quality is not None
    )


def prioritize(signals):
    return OperationalSignalPrioritizer().prioritize(
        tuple(signals),
        company_id=COMPANY_ID,
        branch_id=BRANCH_ID,
        evaluated_at=NOW,
    )


def test_permutations_and_cross_family_order_are_deterministic() -> None:
    scheduling, jobs = operational_signals()
    first = prioritize((scheduling, jobs))
    reversed_input = prioritize((jobs, scheduling))

    assert [item.signal.id for item in first.items] == [
        item.signal.id for item in reversed_input.items
    ]
    assert first.ranking_digest == reversed_input.ranking_digest
    assert first.ranking_version == RANKING_VERSION
    assert first.items[0].signal.severity is BeaconSeverity.CRITICAL
    assert first.items[0].ranking.position == 1


def test_severity_precedes_band_urgency_and_identity() -> None:
    scheduling, jobs = operational_signals()
    very_old_job = replace(
        jobs,
        severity=BeaconSeverity.IMPORTANT,
        supporting_facts=tuple(
            replace(item, value=999999) if item.name == "oldest_pause_hours" else item
            for item in jobs.supporting_facts
        ),
    )
    ordered = prioritize((very_old_job, scheduling))

    assert ordered.items[0].signal.id == scheduling.id
    assert "severity=critical" in ordered.items[0].ranking.ranking_reason


def test_definition_priority_band_precedes_urgency() -> None:
    scheduling, jobs = operational_signals()
    scheduling = replace(scheduling, severity=BeaconSeverity.IMPORTANT)
    very_old_job = replace(
        jobs,
        severity=BeaconSeverity.IMPORTANT,
        supporting_facts=tuple(
            replace(item, value=999999) if item.name == "oldest_pause_hours" else item
            for item in jobs.supporting_facts
        ),
    )
    ordered = prioritize((very_old_job, scheduling))

    assert ordered.items[0].signal.id == scheduling.id
    assert ordered.items[0].ranking.priority_band.value == "important"


def test_accepted_urgency_breaks_same_definition_ties() -> None:
    scheduling, _ = operational_signals()
    newer = replace(
        scheduling,
        id=UUID("00000000-0000-0000-0000-000000000001"),
        supporting_facts=tuple(
            replace(item, value=1) if item.name == "oldest_overdue_hours" else item
            for item in scheduling.supporting_facts
        ),
    )
    older = replace(
        scheduling,
        id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        supporting_facts=tuple(
            replace(item, value=48) if item.name == "oldest_overdue_hours" else item
            for item in scheduling.supporting_facts
        ),
    )
    ordered = prioritize((newer, older))

    assert ordered.items[0].signal.id == older.id
    assert ordered.items[0].ranking.urgency_value == "48"


def test_stable_identity_is_final_exact_tie_breaker() -> None:
    scheduling, _ = operational_signals()
    high_id = replace(scheduling, id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"))
    low_id = replace(scheduling, id=UUID("00000000-0000-0000-0000-000000000001"))
    ordered = prioritize((high_id, low_id))

    assert [item.signal.id for item in ordered.items] == [low_id.id, high_id.id]
    assert "stable signal identity" in ordered.items[1].ranking.ranking_reason


def test_inadmissible_expired_and_snoozed_signals_are_excluded() -> None:
    scheduling, jobs = operational_signals()
    snoozed = replace(
        scheduling,
        lifecycle=replace(
            scheduling.lifecycle,
            status=BeaconLifecycleStatus.SNOOZED,
            temporarily_suppressed=True,
        ),
    )
    expired = replace(jobs, expires_at=NOW)
    inadmissible = replace(
        jobs,
        expires_at=NOW + timedelta(minutes=1),
        evidence_quality=replace(
            jobs.evidence_quality,
            conclusion_admissible=False,  # type: ignore[arg-type]
        ),
    )

    assert prioritize((snoozed, expired, inadmissible)).items == ()


def test_legacy_invoice_and_financial_exposure_stay_outside_queue() -> None:
    signals = SignalEvaluationService().evaluate_signals(snapshot())
    queue = prioritize(signals)

    assert len(queue.items) == 2
    assert all(item.signal.source.value != "invoices" for item in queue.items)
    assert (
        "financial"
        not in " ".join(item.ranking.ranking_reason for item in queue.items).lower()
    )


def test_ranking_digest_changes_for_ordering_fact_not_signal_identity() -> None:
    scheduling, jobs = operational_signals()
    initial_ids = (scheduling.id, jobs.id)
    first = prioritize((scheduling, jobs))
    changed = replace(
        jobs,
        supporting_facts=tuple(
            replace(item, value=6) if item.name == "oldest_pause_hours" else item
            for item in jobs.supporting_facts
        ),
    )
    second = prioritize((scheduling, changed))

    assert first.ranking_digest != second.ranking_digest
    assert (scheduling.id, changed.id) == initial_ids


def test_company_and_branch_are_digest_bound() -> None:
    signals = operational_signals()
    first = prioritize(signals)
    other = OperationalSignalPrioritizer().prioritize(
        signals,
        company_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        branch_id=None,
        evaluated_at=NOW,
    )

    assert first.company_id == COMPANY_ID
    assert first.branch_id == BRANCH_ID
    assert first.ranking_digest != other.ranking_digest
