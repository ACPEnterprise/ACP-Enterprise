from __future__ import annotations

from dataclasses import dataclass

from .contracts import (
    InferenceStatus,
    PromotionStatus,
    PronunciationAuthorityStatus,
    QualificationStatus,
    SpeechEngineState,
    SpeechEngineStatus,
    SpeechInferenceRequest,
    SpeechInferenceResult,
    SpeechModelArtifact,
    SpeechPronunciationAuthority,
)
from .governance import verify_model_manifest, verify_pronunciation_authority

RENDERER_VERSION = "twelve-hats-speech-scaffold.v1"


@dataclass(frozen=True, slots=True)
class TwelveHatsSpeechEngine:
    """Fail-closed scaffold. It cannot synthesize audio without an owned engine."""

    artifact: SpeechModelArtifact | None = None
    artifact_bytes_digests: dict[str, str] | None = None
    pronunciation_authority: SpeechPronunciationAuthority | None = None

    def status(self) -> SpeechEngineStatus:
        if self.artifact is None:
            return SpeechEngineStatus(
                state=SpeechEngineState.MODEL_NOT_AVAILABLE,
                renderer_version=RENDERER_VERSION,
                limitations=("No Twelve Hats speech model artifact is configured.",),
            )
        try:
            self._validate_artifact()
        except (PermissionError, ValueError):
            return SpeechEngineStatus(
                state=SpeechEngineState.FAILED,
                renderer_version=RENDERER_VERSION,
                active_model_version=self.artifact.model_version,
                dataset_version=self.artifact.dataset_version,
                limitations=("Configured model artifact is not render-eligible.",),
            )
        return SpeechEngineStatus(
            state=SpeechEngineState.MODEL_AVAILABLE,
            renderer_version=RENDERER_VERSION,
            active_model_version=self.artifact.model_version,
            dataset_version=self.artifact.dataset_version,
            limitations=("Owned waveform inference implementation is not available.",),
        )

    def render(self, request: SpeechInferenceRequest) -> SpeechInferenceResult:
        try:
            self._validate_artifact(
                request.requested_model_version,
                request.pronunciation_authority_version,
                request.pronunciation_digest,
            )
        except PermissionError as exc:
            return self._rejected(request, "MODEL_NOT_APPROVED", str(exc))
        except ValueError as exc:
            return self._rejected(request, "MODEL_ARTIFACT_INVALID", str(exc))
        return self._rejected(
            request,
            "INFERENCE_IMPLEMENTATION_NOT_AVAILABLE",
            "Twelve Hats waveform inference is not implemented.",
        )

    def _validate_artifact(
        self,
        requested_version: str | None = None,
        pronunciation_version: str | None = None,
        pronunciation_digest: str | None = None,
    ) -> None:
        if self.artifact is None:
            raise PermissionError("no Twelve Hats speech model is configured")
        verify_model_manifest(self.artifact)
        if self.artifact.qualification_status is not QualificationStatus.QUALIFIED:
            raise PermissionError("speech model is not qualified")
        if self.artifact.promotion_status is not PromotionStatus.ACCEPTED:
            raise PermissionError("speech model is not accepted")
        if requested_version is not None and requested_version != self.artifact.model_version:
            raise PermissionError("requested speech model version is not active")
        if self.artifact_bytes_digests != self.artifact.artifact_hashes:
            raise ValueError("speech model artifact hash verification failed")
        if self.pronunciation_authority is None:
            raise PermissionError("approved pronunciation authority is not configured")
        verify_pronunciation_authority(self.pronunciation_authority)
        if self.pronunciation_authority.status is not PronunciationAuthorityStatus.ACCEPTED:
            raise PermissionError("pronunciation authority is not accepted")
        if (
            self.artifact.pronunciation_authority_version
            != self.pronunciation_authority.authority_version
            or self.artifact.pronunciation_authority_digest
            != self.pronunciation_authority.manifest_digest
        ):
            raise ValueError("model and pronunciation authority do not match")
        if pronunciation_version is not None and pronunciation_version != self.pronunciation_authority.authority_version:
            raise PermissionError("request pronunciation version is not active")
        if pronunciation_digest is not None and pronunciation_digest != self.pronunciation_authority.manifest_digest:
            raise PermissionError("request pronunciation digest is not active")

    @staticmethod
    def _rejected(
        request: SpeechInferenceRequest, failure_code: str, warning: str
    ) -> SpeechInferenceResult:
        return SpeechInferenceResult(
            request_id=request.request_id,
            status=InferenceStatus.REJECTED,
            renderer_version=RENDERER_VERSION,
            warnings=(warning,),
            failure_code=failure_code,
        )
