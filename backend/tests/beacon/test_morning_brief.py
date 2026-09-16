from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

from app.beacon.briefing import OwnerAttentionWindow, build_morning_brief
from app.beacon.contracts import BeaconPriorityBand, BeaconSeverity
from app.beacon.evaluation import signal_evaluation_service
from app.beacon.history import BeaconEvaluationRecord, EvaluationDisposition
from tests.beacon.test_beacon import snapshot

COMPANY_ID = UUID("10000000-0000-0000-0000-000000000001")


def test_morning_brief_groups_attention_without_claiming_history() -> None:
    evaluated_at = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
    signals = signal_evaluation_service.evaluate_signals(
        replace(snapshot(), measured_at=evaluated_at)
    )
    assert signals
    critical = replace(
        signals[0],
        severity=BeaconSeverity.CRITICAL,
        priority=replace(signals[0].priority, band=BeaconPriorityBand.CRITICAL),
    )
    watch = replace(
        signals[-1],
        severity=BeaconSeverity.INFORMATION,
        priority=replace(signals[-1].priority, band=BeaconPriorityBand.MONITOR),
    )

    brief = build_morning_brief(
        company_id=COMPANY_ID,
        branch_id=None,
        active=(critical, watch),
        snoozed=(signals[1],),
        evaluated_at=evaluated_at,
    )

    groups = {group.window: group.signal_ids for group in brief.groups}
    assert groups[OwnerAttentionWindow.NOW] == (critical.id,)
    assert groups[OwnerAttentionWindow.WATCH] == (watch.id,)
    assert brief.unresolved_count == 3
    assert brief.snoozed_count == 1
    assert brief.urgent_today_count == 1
    assert brief.new_since_yesterday is None
    assert brief.resolved_since_yesterday is None
    assert not brief.historical_comparison_available
    assert brief.dashboard_ready
    assert not brief.mobile_inbox_ready
    assert not brief.external_delivery_ready
    assert len(brief.brief_digest) == 64


def test_morning_brief_is_deterministic_and_company_scoped() -> None:
    evaluated_at = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
    signals = signal_evaluation_service.evaluate_signals(
        replace(snapshot(), measured_at=evaluated_at)
    )
    first = build_morning_brief(
        company_id=COMPANY_ID,
        branch_id=None,
        active=signals,
        snoozed=(),
        evaluated_at=evaluated_at,
    )
    replay = build_morning_brief(
        company_id=COMPANY_ID,
        branch_id=None,
        active=signals,
        snoozed=(),
        evaluated_at=evaluated_at,
    )
    other_company = build_morning_brief(
        company_id=UUID("10000000-0000-0000-0000-000000000002"),
        branch_id=None,
        active=signals,
        snoozed=(),
        evaluated_at=evaluated_at,
    )
    assert first == replay
    assert first.brief_digest != other_company.brief_digest


def test_morning_brief_uses_persisted_history_deltas() -> None:
    evaluated_at = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
    signals = signal_evaluation_service.evaluate_signals(
        replace(snapshot(), measured_at=evaluated_at)
    )
    records = tuple(
        BeaconEvaluationRecord(
            id=UUID(int=index + 10),
            run_id=UUID(int=1),
            company_id=COMPANY_ID,
            branch_id=None,
            condition_key=UUID(int=index + 20),
            signal_id=UUID(int=index + 30),
            definition_id="qualification.definition",
            definition_version=1,
            evidence_digest=f"{index + 1:064x}",
            evaluated_at=evaluated_at,
            evidence_as_of=evaluated_at,
            signal_expires_at=evaluated_at,
            evaluator_version="qualification.v1",
            disposition=disposition,
            prior_evaluation_id=None,
        )
        for index, disposition in enumerate(
            (
                EvaluationDisposition.NEW,
                EvaluationDisposition.RESOLVED,
                EvaluationDisposition.CHANGED,
                EvaluationDisposition.EXPIRED,
            )
        )
    )
    brief = build_morning_brief(
        company_id=COMPANY_ID,
        branch_id=None,
        active=signals,
        snoozed=(),
        evaluated_at=evaluated_at,
        historical_deltas=records,
    )

    assert brief.historical_comparison_available
    assert brief.new_since_yesterday == 1
    assert brief.resolved_since_yesterday == 1
    assert brief.changed_since_yesterday == 1
    assert brief.expired_since_yesterday == 1
    without_history = build_morning_brief(
        company_id=COMPANY_ID,
        branch_id=None,
        active=signals,
        snoozed=(),
        evaluated_at=evaluated_at,
    )
    changed_history = build_morning_brief(
        company_id=COMPANY_ID,
        branch_id=None,
        active=signals,
        snoozed=(),
        evaluated_at=evaluated_at,
        historical_deltas=(replace(records[0], evidence_digest="f" * 64), *records[1:]),
    )
    assert brief.brief_digest != without_history.brief_digest
    assert brief.brief_digest != changed_history.brief_digest
