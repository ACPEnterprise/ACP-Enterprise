from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .contracts import (
    Identifier,
    PromotionStatus,
    QualificationStatus,
    Sha256,
    SpeechContract,
    SpeechModelArtifact,
)
from .governance import canonical_digest, verify_model_manifest


class SpeechModelPromotionEvidence(SpeechContract):
    event_id: Identifier
    model_id: Identifier
    model_version: Identifier
    from_status: PromotionStatus | None
    to_status: PromotionStatus
    reason: str = Field(min_length=1, max_length=500)
    actor_reference: str = Field(min_length=1, max_length=160)
    occurred_at: datetime
    prior_event_digest: Sha256 | None = None
    event_digest: Sha256


_ALLOWED_TRANSITIONS: dict[PromotionStatus | None, frozenset[PromotionStatus]] = {
    None: frozenset({PromotionStatus.DEVELOPMENT}),
    PromotionStatus.DEVELOPMENT: frozenset(
        {PromotionStatus.CANDIDATE, PromotionStatus.REVOKED}
    ),
    PromotionStatus.CANDIDATE: frozenset(
        {PromotionStatus.QUALIFIED, PromotionStatus.REVOKED}
    ),
    PromotionStatus.QUALIFIED: frozenset(
        {PromotionStatus.ACCEPTED, PromotionStatus.REVOKED}
    ),
    PromotionStatus.ACCEPTED: frozenset(
        {PromotionStatus.SUPERSEDED, PromotionStatus.REVOKED}
    ),
    PromotionStatus.SUPERSEDED: frozenset(),
    PromotionStatus.REVOKED: frozenset(),
}


def promotion_event_digest(event: SpeechModelPromotionEvidence) -> str:
    return canonical_digest(event.model_dump(mode="json", exclude={"event_digest"}))


def validate_promotion_ledger(
    artifact: SpeechModelArtifact,
    events: tuple[SpeechModelPromotionEvidence, ...],
) -> PromotionStatus:
    verify_model_manifest(artifact)
    if not events:
        raise ValueError("model promotion ledger must not be empty")
    previous: SpeechModelPromotionEvidence | None = None
    for event in events:
        if event.model_id != artifact.model_id or event.model_version != artifact.model_version:
            raise ValueError("promotion evidence names a different model")
        expected_from = previous.to_status if previous else None
        if event.from_status is not expected_from:
            raise ValueError("promotion evidence does not continue prior state")
        if event.to_status not in _ALLOWED_TRANSITIONS[expected_from]:
            raise ValueError("model promotion transition is not permitted")
        expected_prior = previous.event_digest if previous else None
        if event.prior_event_digest != expected_prior:
            raise ValueError("promotion evidence prior digest does not match")
        if promotion_event_digest(event) != event.event_digest:
            raise ValueError("promotion evidence digest does not match")
        if (
            event.to_status
            in {PromotionStatus.QUALIFIED, PromotionStatus.ACCEPTED}
            and artifact.qualification_status is not QualificationStatus.QUALIFIED
        ):
            raise PermissionError("qualified promotion requires a qualified artifact")
        previous = event
    assert previous is not None
    if artifact.promotion_status is not previous.to_status:
        raise ValueError("artifact promotion status differs from promotion ledger")
    return previous.to_status


def resolve_active_model(
    candidates: tuple[
        tuple[SpeechModelArtifact, tuple[SpeechModelPromotionEvidence, ...]], ...
    ],
) -> SpeechModelArtifact | None:
    active: list[SpeechModelArtifact] = []
    for artifact, events in candidates:
        if validate_promotion_ledger(artifact, events) is PromotionStatus.ACCEPTED:
            active.append(artifact)
    if len(active) > 1:
        raise RuntimeError("multiple accepted speech models would fork active authority")
    return active[0] if active else None
