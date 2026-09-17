from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Identifier = Annotated[str, Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9._:-]+$")]


class SpeechContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SpeechEngineState(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    DATASET_NOT_READY = "DATASET_NOT_READY"
    TRAINING_NOT_READY = "TRAINING_NOT_READY"
    MODEL_NOT_AVAILABLE = "MODEL_NOT_AVAILABLE"
    MODEL_AVAILABLE = "MODEL_AVAILABLE"
    INFERENCE_READY = "INFERENCE_READY"
    FAILED = "FAILED"


class QualificationStatus(StrEnum):
    NOT_EVALUATED = "NOT_EVALUATED"
    FAILED = "FAILED"
    QUALIFIED = "QUALIFIED"


class PromotionStatus(StrEnum):
    DEVELOPMENT = "DEVELOPMENT"
    CANDIDATE = "CANDIDATE"
    QUALIFIED = "QUALIFIED"
    ACCEPTED = "ACCEPTED"
    SUPERSEDED = "SUPERSEDED"
    REVOKED = "REVOKED"


class DatasetAdmissionState(StrEnum):
    NOT_REVIEWED = "NOT_REVIEWED"
    RIGHTS_MISSING = "RIGHTS_MISSING"
    REJECTED = "REJECTED"
    QUALIFIED = "QUALIFIED"
    REVOKED = "REVOKED"


class DatasetRightsStatus(StrEnum):
    MISSING = "MISSING"
    AMBIGUOUS = "AMBIGUOUS"
    TWELVE_HATS_OWNED = "TWELVE_HATS_OWNED"
    COMMISSIONED_PERPETUAL_COMMERCIAL = "COMMISSIONED_PERPETUAL_COMMERCIAL"
    REVOKED = "REVOKED"


class TrainingRunStatus(StrEnum):
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    REFUSED = "REFUSED"


class InferenceStatus(StrEnum):
    RENDERED = "RENDERED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class AudioFormat(StrEnum):
    PCM_S16LE = "PCM_S16LE"
    WAV = "WAV"
    FLAC = "FLAC"
    OPUS = "OPUS"
    AAC = "AAC"


class SpeechDatasetVersion(SpeechContract):
    contract_version: Literal["TWELVE_HATS_SPEECH_DATASET.v1"] = (
        "TWELVE_HATS_SPEECH_DATASET.v1"
    )
    dataset_id: Identifier
    dataset_version: Identifier
    manifest_digest: Sha256
    admission_state: DatasetAdmissionState
    rights_status: DatasetRightsStatus
    rights_evidence_digest: Sha256 | None = None
    provenance_digest: Sha256
    language: str = Field(min_length=2, max_length=32)
    admitted_at: datetime | None = None

    @model_validator(mode="after")
    def qualified_dataset_has_rights(self) -> SpeechDatasetVersion:
        if self.admission_state is DatasetAdmissionState.QUALIFIED and (
            self.rights_status
            not in {
                DatasetRightsStatus.TWELVE_HATS_OWNED,
                DatasetRightsStatus.COMMISSIONED_PERPETUAL_COMMERCIAL,
            }
            or self.rights_evidence_digest is None
            or self.admitted_at is None
        ):
            raise ValueError("qualified dataset requires admitted rights evidence")
        return self


class SpeechCheckpoint(SpeechContract):
    checkpoint_id: Identifier
    step: int = Field(ge=0)
    artifact_digest: Sha256
    metrics_digest: Sha256


class SpeechTrainingRun(SpeechContract):
    contract_version: Literal["TWELVE_HATS_SPEECH_TRAINING_RUN.v1"] = (
        "TWELVE_HATS_SPEECH_TRAINING_RUN.v1"
    )
    training_run_id: Identifier
    code_revision: Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")]
    dataset_version: Identifier
    model_architecture_version: Identifier
    exact_config: dict[str, Any]
    config_digest: Sha256
    random_seeds: tuple[int, ...] = Field(min_length=1)
    hardware_profile: str = Field(min_length=1, max_length=500)
    status: TrainingRunStatus
    started_at: datetime | None = None
    ended_at: datetime | None = None
    checkpoints: tuple[SpeechCheckpoint, ...] = ()
    metrics_schema_version: Identifier
    failures: tuple[str, ...] = ()
    artifact_digests: tuple[Sha256, ...] = ()
    evaluator_result_digests: tuple[Sha256, ...] = ()


class SpeechModelArtifact(SpeechContract):
    contract_version: Literal["TWELVE_HATS_SPEECH_MODEL_ARTIFACT.v1"] = (
        "TWELVE_HATS_SPEECH_MODEL_ARTIFACT.v1"
    )
    model_id: Identifier
    model_version: Identifier
    architecture_version: Identifier
    code_revision: Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")]
    dataset_version: Identifier
    training_run_id: Identifier
    training_config_digest: Sha256
    pronunciation_authority_version: Identifier
    evaluation_corpus_version: Identifier
    artifact_hashes: dict[str, Sha256] = Field(min_length=1)
    created_at: datetime
    qualification_status: QualificationStatus
    promotion_status: PromotionStatus
    manifest_digest: Sha256

    @model_validator(mode="after")
    def accepted_model_is_qualified(self) -> SpeechModelArtifact:
        if (
            self.promotion_status is PromotionStatus.ACCEPTED
            and self.qualification_status is not QualificationStatus.QUALIFIED
        ):
            raise ValueError("accepted model must be explicitly qualified")
        return self


class SpeechModelVersion(SpeechContract):
    model_id: Identifier
    model_version: Identifier
    artifact_manifest_digest: Sha256
    promotion_status: PromotionStatus
    qualified_at: datetime | None = None
    accepted_at: datetime | None = None
    supersedes_model_version: Identifier | None = None


class DeliveryMetadata(SpeechContract):
    style_version: Identifier
    nominal_pace: Literal["MODERATE"]
    sentence_pause_intent: Literal["NATURAL", "SHORT", "DELIBERATE"]
    limitation_pause_intent: Literal["NATURAL", "SHORT", "DELIBERATE"]
    question_contour_intent: Literal["GENTLE_RISE", "NEUTRAL"]
    emphasis_intent: Literal["MEANING_BEARING_TERMS_ONLY"]
    expressiveness: Literal["RESTRAINED"]


class SpeechInferenceRequest(SpeechContract):
    contract_version: Literal["TWELVE_HATS_SPEECH_INFERENCE.v1"] = (
        "TWELVE_HATS_SPEECH_INFERENCE.v1"
    )
    request_id: Identifier
    semantic_text: str = Field(min_length=1, max_length=10_000)
    language: str = Field(min_length=2, max_length=32)
    response_mode: Literal["BRIEF", "NORMAL", "DETAILED", "EVIDENCE"]
    delivery: DeliveryMetadata
    pronunciation_authority_version: Identifier
    pronunciation_digest: Sha256
    requested_model_version: Identifier | None = None
    deterministic_metadata: dict[str, str] = Field(default_factory=dict)


class SpeechInferenceResult(SpeechContract):
    request_id: Identifier
    status: InferenceStatus
    audio_reference: str | None = Field(default=None, max_length=500)
    audio_bytes: bytes | None = None
    audio_format: AudioFormat | None = None
    content_type: str | None = Field(default=None, max_length=100)
    sample_rate_hz: int | None = Field(default=None, ge=8_000, le=192_000)
    duration_ms: int | None = Field(default=None, ge=0)
    streaming_supported: bool = False
    model_id: str | None = None
    model_version: str | None = None
    dataset_version: str | None = None
    pronunciation_version: str | None = None
    renderer_version: str
    render_digest: Sha256 | None = None
    warnings: tuple[str, ...] = Field(default=(), max_length=8)
    failure_code: str | None = Field(default=None, max_length=100)


class SpeechEngineStatus(SpeechContract):
    engine_id: Literal["TWELVE_HATS_SPEECH"] = "TWELVE_HATS_SPEECH"
    state: SpeechEngineState
    renderer_version: Identifier
    active_model_version: str | None = None
    dataset_version: str | None = None
    acoustic_evaluation_status: Literal["MODEL_ACOUSTIC_EVALUATION_PENDING"] = (
        "MODEL_ACOUSTIC_EVALUATION_PENDING"
    )
    limitations: tuple[str, ...] = ()


class AcousticEvaluationDimension(StrEnum):
    INTELLIGIBILITY = "INTELLIGIBILITY"
    PRONUNCIATION = "PRONUNCIATION"
    PACING = "PACING"
    PAUSE_BEHAVIOR = "PAUSE_BEHAVIOR"
    NUMBER_ACCURACY = "NUMBER_ACCURACY"
    CURRENCY_ACCURACY = "CURRENCY_ACCURACY"
    ACRONYM_HANDLING = "ACRONYM_HANDLING"
    CLIPPING_ARTIFACTS = "CLIPPING_ARTIFACTS"
    CONSISTENCY = "CONSISTENCY"
    LATENCY = "LATENCY"
    OWNER_PREFERENCE = "OWNER_PREFERENCE"


class SpeechAcousticEvaluation(SpeechContract):
    contract_version: Literal["TWELVE_HATS_SPEECH_ACOUSTIC_EVALUATION.v1"] = (
        "TWELVE_HATS_SPEECH_ACOUSTIC_EVALUATION.v1"
    )
    model_id: Identifier
    model_version: Identifier
    evaluation_corpus_version: Identifier
    semantic_evaluation_digest: Sha256
    audio_artifact_digest: Sha256 | None = None
    status: Literal[
        "MODEL_ACOUSTIC_EVALUATION_PENDING", "EVALUATED", "FAILED"
    ] = "MODEL_ACOUSTIC_EVALUATION_PENDING"
    scores: dict[AcousticEvaluationDimension, float] = Field(default_factory=dict)
    evaluator_result_digest: Sha256 | None = None

    @model_validator(mode="after")
    def scores_require_audio(self) -> SpeechAcousticEvaluation:
        if self.status == "MODEL_ACOUSTIC_EVALUATION_PENDING" and (
            self.audio_artifact_digest is not None
            or self.scores
            or self.evaluator_result_digest is not None
        ):
            raise ValueError("pending acoustic evaluation cannot claim audio or scores")
        if self.status == "EVALUATED" and (
            self.audio_artifact_digest is None or self.evaluator_result_digest is None
        ):
            raise ValueError("evaluated acoustic result requires audio and evidence")
        return self
