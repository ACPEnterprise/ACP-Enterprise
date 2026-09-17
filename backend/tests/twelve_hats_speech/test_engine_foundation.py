from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.twelve_hats_speech.contracts import (
    DatasetAdmissionState,
    DatasetRightsStatus,
    DeliveryMetadata,
    InferenceStatus,
    PromotionStatus,
    QualificationStatus,
    SpeechAcousticEvaluation,
    SpeechDatasetVersion,
    SpeechEngineState,
    SpeechInferenceRequest,
    SpeechModelArtifact,
    SpeechTrainingRun,
    TrainingRunStatus,
)
from app.twelve_hats_speech.engine import TwelveHatsSpeechEngine
from app.twelve_hats_speech.governance import (
    authorize_training,
    canonical_digest,
)

NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
SHA = "a" * 64
CODE_REVISION = "b" * 40


def delivery() -> DeliveryMetadata:
    return DeliveryMetadata(
        style_version="lia-delivery-style.v1",
        nominal_pace="MODERATE",
        sentence_pause_intent="NATURAL",
        limitation_pause_intent="DELIBERATE",
        question_contour_intent="GENTLE_RISE",
        emphasis_intent="MEANING_BEARING_TERMS_ONLY",
        expressiveness="RESTRAINED",
    )


def request(**overrides: object) -> SpeechInferenceRequest:
    values: dict[str, object] = {
        "request_id": "speech-request-1",
        "semantic_text": "The current evidence is incomplete.",
        "language": "en-US",
        "response_mode": "NORMAL",
        "delivery": delivery(),
        "pronunciation_authority_version": "lia-pronunciation.v1",
        "pronunciation_digest": SHA,
    }
    values.update(overrides)
    return SpeechInferenceRequest.model_validate(values)


def artifact(
    *,
    qualification: QualificationStatus = QualificationStatus.QUALIFIED,
    promotion: PromotionStatus = PromotionStatus.ACCEPTED,
    manifest_digest: str | None = None,
) -> SpeechModelArtifact:
    values: dict[str, object] = {
        "model_id": "lia-owned-voice",
        "model_version": "1.0.0",
        "architecture_version": "unselected.v1",
        "code_revision": CODE_REVISION,
        "dataset_version": "dataset.v1",
        "training_run_id": "training-run-1",
        "training_config_digest": "c" * 64,
        "pronunciation_authority_version": "lia-pronunciation.v1",
        "evaluation_corpus_version": "lia-voice-evaluation.v1",
        "artifact_hashes": {"model": "d" * 64},
        "created_at": NOW,
        "qualification_status": qualification,
        "promotion_status": promotion,
    }
    values["manifest_digest"] = "0" * 64
    provisional = SpeechModelArtifact.model_validate(values)
    values = provisional.model_dump(mode="json", exclude={"manifest_digest"})
    values["manifest_digest"] = manifest_digest or canonical_digest(values)
    return SpeechModelArtifact.model_validate(values)


def training_run(dataset_version: str = "dataset.v1") -> SpeechTrainingRun:
    config = {"batch_size": 8, "learning_rate": "0.0001"}
    return SpeechTrainingRun(
        training_run_id="training-run-1",
        code_revision=CODE_REVISION,
        dataset_version=dataset_version,
        model_architecture_version="unselected.v1",
        exact_config=config,
        config_digest=canonical_digest(config),
        random_seeds=(314159,),
        hardware_profile="unallocated; no training runtime admitted",
        status=TrainingRunStatus.PLANNED,
        metrics_schema_version="speech-training-metrics.v1",
    )


def dataset(
    admission: DatasetAdmissionState = DatasetAdmissionState.QUALIFIED,
    rights: DatasetRightsStatus = DatasetRightsStatus.TWELVE_HATS_OWNED,
) -> SpeechDatasetVersion:
    return SpeechDatasetVersion(
        dataset_id="lia-owned-dataset",
        dataset_version="dataset.v1",
        manifest_digest="e" * 64,
        admission_state=admission,
        rights_status=rights,
        rights_evidence_digest="f" * 64 if admission is DatasetAdmissionState.QUALIFIED else None,
        provenance_digest="1" * 64,
        language="en-US",
        admitted_at=NOW if admission is DatasetAdmissionState.QUALIFIED else None,
    )


def test_no_model_fails_closed_without_fake_audio() -> None:
    engine = TwelveHatsSpeechEngine()

    assert engine.status().state is SpeechEngineState.MODEL_NOT_AVAILABLE
    result = engine.render(request())
    assert result.status is InferenceStatus.REJECTED
    assert result.failure_code == "MODEL_NOT_APPROVED"
    assert result.audio_bytes is None
    assert result.audio_reference is None
    assert result.render_digest is None


@pytest.mark.parametrize(
    ("qualification", "promotion"),
    (
        (QualificationStatus.NOT_EVALUATED, PromotionStatus.CANDIDATE),
        (QualificationStatus.FAILED, PromotionStatus.DEVELOPMENT),
        (QualificationStatus.QUALIFIED, PromotionStatus.REVOKED),
        (QualificationStatus.QUALIFIED, PromotionStatus.SUPERSEDED),
    ),
)
def test_unqualified_revoked_or_inactive_models_cannot_render(
    qualification: QualificationStatus, promotion: PromotionStatus
) -> None:
    current = artifact(qualification=qualification, promotion=promotion)
    result = TwelveHatsSpeechEngine(
        current, artifact_bytes_digests=current.artifact_hashes
    ).render(request())

    assert result.status is InferenceStatus.REJECTED
    assert result.failure_code == "MODEL_NOT_APPROVED"


def test_accepted_status_requires_explicit_qualification() -> None:
    with pytest.raises(ValidationError, match="explicitly qualified"):
        artifact(
            qualification=QualificationStatus.NOT_EVALUATED,
            promotion=PromotionStatus.ACCEPTED,
        )


def test_wrong_manifest_or_artifact_digest_is_rejected() -> None:
    invalid_manifest = artifact(manifest_digest="0" * 64)
    assert TwelveHatsSpeechEngine(
        invalid_manifest, artifact_bytes_digests=invalid_manifest.artifact_hashes
    ).render(request()).failure_code == "MODEL_ARTIFACT_INVALID"

    valid = artifact()
    result = TwelveHatsSpeechEngine(
        valid, artifact_bytes_digests={"model": "9" * 64}
    ).render(request())
    assert result.failure_code == "MODEL_ARTIFACT_INVALID"


def test_even_valid_manifest_refuses_until_owned_inference_exists() -> None:
    current = artifact()
    result = TwelveHatsSpeechEngine(
        current, artifact_bytes_digests=current.artifact_hashes
    ).render(request(requested_model_version=current.model_version))

    assert result.status is InferenceStatus.REJECTED
    assert result.failure_code == "INFERENCE_IMPLEMENTATION_NOT_AVAILABLE"
    assert result.model_id is None
    assert result.audio_bytes is None


def test_training_requires_qualified_rights_and_matching_dataset() -> None:
    authorize_training(dataset(), training_run())

    with pytest.raises(PermissionError, match="qualified dataset"):
        authorize_training(
            dataset(
                DatasetAdmissionState.NOT_REVIEWED,
                DatasetRightsStatus.MISSING,
            ),
            training_run(),
        )
    with pytest.raises(ValueError, match="does not match"):
        authorize_training(dataset(), training_run("other-dataset.v1"))


def test_missing_rights_cannot_be_labeled_as_qualified() -> None:
    with pytest.raises(ValidationError, match="rights evidence"):
        SpeechDatasetVersion(
            dataset_id="unsafe-dataset",
            dataset_version="v1",
            manifest_digest=SHA,
            admission_state=DatasetAdmissionState.QUALIFIED,
            rights_status=DatasetRightsStatus.MISSING,
            provenance_digest=SHA,
            language="en-US",
            admitted_at=NOW,
        )


def test_manifests_are_deterministic_and_traceable() -> None:
    current = artifact()
    assert canonical_digest(current.model_dump(mode="json", exclude={"manifest_digest"})) == current.manifest_digest
    assert canonical_digest(training_run()) == canonical_digest(training_run())
    assert current.dataset_version == training_run().dataset_version
    assert current.training_run_id == training_run().training_run_id


def test_no_external_provider_url_or_credentials_are_accepted() -> None:
    payload = request().model_dump()
    payload["provider"] = "outside"
    payload["external_url"] = "https://example.invalid/render"
    payload["credential"] = "not-allowed"
    with pytest.raises(ValidationError):
        SpeechInferenceRequest.model_validate(payload)


def test_acoustic_evaluation_cannot_claim_scores_without_audio() -> None:
    pending = SpeechAcousticEvaluation(
        model_id="lia-owned-voice",
        model_version="1.0.0",
        evaluation_corpus_version="lia-voice-evaluation.v1",
        semantic_evaluation_digest=SHA,
    )
    assert pending.status == "MODEL_ACOUSTIC_EVALUATION_PENDING"
    assert pending.scores == {}

    with pytest.raises(ValidationError, match="cannot claim"):
        SpeechAcousticEvaluation.model_validate(
            {**pending.model_dump(), "scores": {"INTELLIGIBILITY": 5.0}}
        )
