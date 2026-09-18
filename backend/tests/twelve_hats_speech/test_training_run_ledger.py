from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.twelve_hats_speech.contracts import SpeechTrainingRun, TrainingRunStatus
from app.twelve_hats_speech.governance import canonical_digest
from app.twelve_hats_speech.training import (
    SpeechTrainingRunEvidence,
    training_event_digest,
    validate_training_run_ledger,
)

NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
CONFIG = {"architecture": "unselected", "seed": 42}


def run(status: TrainingRunStatus, **updates: object) -> SpeechTrainingRun:
    values: dict[str, object] = {
        "training_run_id": "run-1",
        "code_revision": "a" * 40,
        "dataset_version": "dataset.v1",
        "model_architecture_version": "unselected.v1",
        "exact_config": CONFIG,
        "config_digest": canonical_digest(CONFIG),
        "random_seeds": (42,),
        "hardware_profile": "isolated synthetic qualification",
        "status": status,
        "metrics_schema_version": "metrics.v1",
    }
    values.update(updates)
    return SpeechTrainingRun.model_validate(values)


def event(
    to_status: TrainingRunStatus,
    from_status: TrainingRunStatus | None,
    prior: SpeechTrainingRunEvidence | None = None,
) -> SpeechTrainingRunEvidence:
    values: dict[str, object] = {
        "event_id": f"run-1-{to_status.value.lower()}",
        "training_run_id": "run-1",
        "dataset_version": "dataset.v1",
        "config_digest": canonical_digest(CONFIG),
        "from_status": from_status,
        "to_status": to_status,
        "occurred_at": NOW + timedelta(minutes=1 if prior else 0),
        "reason": "synthetic lifecycle evidence",
        "prior_event_digest": prior.event_digest if prior else None,
        "event_digest": "0" * 64,
    }
    provisional = SpeechTrainingRunEvidence.model_validate(values)
    values["event_digest"] = training_event_digest(provisional)
    return SpeechTrainingRunEvidence.model_validate(values)


def test_successful_run_requires_exact_append_only_evidence_and_artifact() -> None:
    planned = event(TrainingRunStatus.PLANNED, None)
    running = event(TrainingRunStatus.RUNNING, TrainingRunStatus.PLANNED, planned)
    succeeded = event(TrainingRunStatus.SUCCEEDED, TrainingRunStatus.RUNNING, running)
    current = run(TrainingRunStatus.SUCCEEDED, artifact_digests=("b" * 64,))
    assert validate_training_run_ledger(current, (planned, running, succeeded)) is TrainingRunStatus.SUCCEEDED


def test_skipped_rewritten_or_cross_run_evidence_fails_closed() -> None:
    planned = event(TrainingRunStatus.PLANNED, None)
    succeeded = event(TrainingRunStatus.SUCCEEDED, TrainingRunStatus.PLANNED, planned)
    with pytest.raises(ValueError, match="not permitted"):
        validate_training_run_ledger(
            run(TrainingRunStatus.SUCCEEDED, artifact_digests=("b" * 64,)),
            (planned, succeeded),
        )
    tampered = planned.model_copy(update={"reason": "rewritten"})
    with pytest.raises(ValueError, match="digest"):
        validate_training_run_ledger(run(TrainingRunStatus.PLANNED), (tampered,))


def test_terminal_claims_require_evidence() -> None:
    planned = event(TrainingRunStatus.PLANNED, None)
    running = event(TrainingRunStatus.RUNNING, TrainingRunStatus.PLANNED, planned)
    succeeded = event(TrainingRunStatus.SUCCEEDED, TrainingRunStatus.RUNNING, running)
    with pytest.raises(ValueError, match="artifact digests"):
        validate_training_run_ledger(
            run(TrainingRunStatus.SUCCEEDED), (planned, running, succeeded)
        )

    failed = event(TrainingRunStatus.FAILED, TrainingRunStatus.RUNNING, running)
    with pytest.raises(ValueError, match="failure evidence"):
        validate_training_run_ledger(
            run(TrainingRunStatus.FAILED), (planned, running, failed)
        )
