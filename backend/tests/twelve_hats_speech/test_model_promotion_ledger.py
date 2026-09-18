from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.twelve_hats_speech.contracts import PromotionStatus, QualificationStatus
from app.twelve_hats_speech.governance import canonical_digest
from app.twelve_hats_speech.registry import (
    SpeechModelPromotionEvidence,
    promotion_event_digest,
    resolve_active_model,
    validate_promotion_ledger,
)
from tests.twelve_hats_speech.test_engine_foundation import artifact

NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)


def event(
    *,
    to_status: PromotionStatus,
    from_status: PromotionStatus | None,
    prior: SpeechModelPromotionEvidence | None = None,
    model_version: str = "1.0.0",
    digest: str | None = None,
) -> SpeechModelPromotionEvidence:
    values: dict[str, object] = {
        "event_id": f"promotion-{to_status.value.lower()}",
        "model_id": "lia-owned-voice",
        "model_version": model_version,
        "from_status": from_status,
        "to_status": to_status,
        "reason": "synthetic governance qualification",
        "actor_reference": "owner-review",
        "occurred_at": NOW,
        "prior_event_digest": prior.event_digest if prior else None,
        "event_digest": "0" * 64,
    }
    provisional = SpeechModelPromotionEvidence.model_validate(values)
    values["event_digest"] = digest or promotion_event_digest(provisional)
    return SpeechModelPromotionEvidence.model_validate(values)


def accepted_ledger() -> tuple[SpeechModelPromotionEvidence, ...]:
    development = event(to_status=PromotionStatus.DEVELOPMENT, from_status=None)
    candidate = event(
        to_status=PromotionStatus.CANDIDATE,
        from_status=PromotionStatus.DEVELOPMENT,
        prior=development,
    )
    qualified = event(
        to_status=PromotionStatus.QUALIFIED,
        from_status=PromotionStatus.CANDIDATE,
        prior=candidate,
    )
    accepted = event(
        to_status=PromotionStatus.ACCEPTED,
        from_status=PromotionStatus.QUALIFIED,
        prior=qualified,
    )
    return development, candidate, qualified, accepted


def test_exact_append_only_ledger_resolves_accepted_model() -> None:
    current = artifact()
    ledger = accepted_ledger()
    assert validate_promotion_ledger(current, ledger) is PromotionStatus.ACCEPTED
    assert resolve_active_model(((current, ledger),)) == current


@pytest.mark.parametrize(
    "events",
    (
        (),
        (
            event(
                to_status=PromotionStatus.ACCEPTED,
                from_status=None,
            ),
        ),
    ),
)
def test_empty_or_skipped_transition_is_rejected(
    events: tuple[SpeechModelPromotionEvidence, ...],
) -> None:
    with pytest.raises(ValueError):
        validate_promotion_ledger(artifact(), events)


def test_rewritten_or_cross_model_evidence_is_rejected() -> None:
    ledger = accepted_ledger()
    tampered = ledger[-1].model_copy(update={"reason": "rewritten reason"})
    with pytest.raises(ValueError, match="digest"):
        validate_promotion_ledger(artifact(), (*ledger[:-1], tampered))

    foreign = ledger[-1].model_copy(update={"model_version": "2.0.0"})
    with pytest.raises(ValueError, match="different model"):
        validate_promotion_ledger(artifact(), (*ledger[:-1], foreign))


def test_unqualified_artifact_cannot_cross_qualified_transition() -> None:
    unqualified = artifact(
        qualification=QualificationStatus.NOT_EVALUATED,
        promotion=PromotionStatus.CANDIDATE,
    )
    development, candidate, *_ = accepted_ledger()
    assert validate_promotion_ledger(
        unqualified, (development, candidate)
    ) is PromotionStatus.CANDIDATE

    qualified = event(
        to_status=PromotionStatus.QUALIFIED,
        from_status=PromotionStatus.CANDIDATE,
        prior=candidate,
    )
    with pytest.raises(PermissionError, match="qualified artifact"):
        validate_promotion_ledger(unqualified, (development, candidate, qualified))


def test_multiple_accepted_models_fail_as_authority_fork() -> None:
    first = artifact()
    second_values = first.model_dump(mode="json", exclude={"manifest_digest"})
    second_values["model_version"] = "2.0.0"
    second_values["manifest_digest"] = canonical_digest(second_values)
    second = first.model_validate(second_values)
    second_ledger = tuple(
        item.model_copy(
            update={
                "model_version": "2.0.0",
                "event_digest": "0" * 64,
                "prior_event_digest": None,
            }
        )
        for item in accepted_ledger()
    )
    rebuilt: list[SpeechModelPromotionEvidence] = []
    for item in second_ledger:
        prior = rebuilt[-1] if rebuilt else None
        rebuilt.append(
            event(
                to_status=item.to_status,
                from_status=item.from_status,
                prior=prior,
                model_version="2.0.0",
            )
        )
    with pytest.raises(RuntimeError, match="fork"):
        resolve_active_model(((first, accepted_ledger()), (second, tuple(rebuilt))))
