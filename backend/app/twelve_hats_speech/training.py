from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .contracts import (
    Identifier,
    Sha256,
    SpeechContract,
    SpeechTrainingRun,
    TrainingRunStatus,
)
from .governance import canonical_digest


class SpeechTrainingRunEvidence(SpeechContract):
    event_id: Identifier
    training_run_id: Identifier
    dataset_version: Identifier
    config_digest: Sha256
    from_status: TrainingRunStatus | None
    to_status: TrainingRunStatus
    occurred_at: datetime
    reason: str = Field(min_length=1, max_length=500)
    prior_event_digest: Sha256 | None = None
    event_digest: Sha256


_TRANSITIONS = {
    None: frozenset({TrainingRunStatus.PLANNED, TrainingRunStatus.REFUSED}),
    TrainingRunStatus.PLANNED: frozenset(
        {TrainingRunStatus.RUNNING, TrainingRunStatus.CANCELED, TrainingRunStatus.REFUSED}
    ),
    TrainingRunStatus.RUNNING: frozenset(
        {TrainingRunStatus.SUCCEEDED, TrainingRunStatus.FAILED, TrainingRunStatus.CANCELED}
    ),
    TrainingRunStatus.SUCCEEDED: frozenset(),
    TrainingRunStatus.FAILED: frozenset(),
    TrainingRunStatus.CANCELED: frozenset(),
    TrainingRunStatus.REFUSED: frozenset(),
}


def training_event_digest(event: SpeechTrainingRunEvidence) -> str:
    return canonical_digest(event.model_dump(mode="json", exclude={"event_digest"}))


def validate_training_run_ledger(
    run: SpeechTrainingRun, events: tuple[SpeechTrainingRunEvidence, ...]
) -> TrainingRunStatus:
    if not events:
        raise ValueError("training run ledger must not be empty")
    prior: SpeechTrainingRunEvidence | None = None
    for event in events:
        if (
            event.training_run_id != run.training_run_id
            or event.dataset_version != run.dataset_version
            or event.config_digest != run.config_digest
        ):
            raise ValueError("training event does not bind the exact run")
        expected = prior.to_status if prior else None
        if event.from_status is not expected or event.to_status not in _TRANSITIONS[expected]:
            raise ValueError("training status transition is not permitted")
        if event.prior_event_digest != (prior.event_digest if prior else None):
            raise ValueError("training event prior digest does not match")
        if training_event_digest(event) != event.event_digest:
            raise ValueError("training event digest does not match")
        if prior and event.occurred_at < prior.occurred_at:
            raise ValueError("training event time cannot move backward")
        prior = event
    assert prior is not None
    if run.status is not prior.to_status:
        raise ValueError("training snapshot status differs from ledger")
    if run.status is TrainingRunStatus.SUCCEEDED and not run.artifact_digests:
        raise ValueError("successful training requires artifact digests")
    if run.status is TrainingRunStatus.FAILED and not run.failures:
        raise ValueError("failed training requires bounded failure evidence")
    return prior.to_status
