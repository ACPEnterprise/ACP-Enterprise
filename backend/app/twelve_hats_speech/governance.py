from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel

from .contracts import (
    DatasetAdmissionState,
    DatasetRightsStatus,
    SpeechDatasetVersion,
    SpeechModelArtifact,
    SpeechPronunciationAuthority,
    SpeechTrainingRun,
)


def canonical_digest(value: BaseModel | dict[str, Any]) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=_canonical_json_default,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return str(value.value)
    raise TypeError(f"unsupported canonical manifest value: {type(value).__name__}")


def verify_model_manifest(artifact: SpeechModelArtifact) -> None:
    manifest = artifact.model_dump(mode="json", exclude={"manifest_digest"})
    if canonical_digest(manifest) != artifact.manifest_digest:
        raise ValueError("speech model artifact manifest digest mismatch")


def verify_pronunciation_authority(
    authority: SpeechPronunciationAuthority,
) -> None:
    manifest = authority.model_dump(mode="json", exclude={"manifest_digest"})
    if canonical_digest(manifest) != authority.manifest_digest:
        raise ValueError("pronunciation authority manifest digest mismatch")


def authorize_training(
    dataset: SpeechDatasetVersion, run: SpeechTrainingRun
) -> None:
    if dataset.admission_state is not DatasetAdmissionState.QUALIFIED:
        raise PermissionError("speech training requires a qualified dataset")
    if dataset.rights_status not in {
        DatasetRightsStatus.TWELVE_HATS_OWNED,
        DatasetRightsStatus.COMMISSIONED_PERPETUAL_COMMERCIAL,
    }:
        raise PermissionError("speech training requires qualified dataset rights")
    if dataset.rights_evidence_digest is None:
        raise PermissionError("speech training requires rights evidence")
    if run.dataset_version != dataset.dataset_version:
        raise ValueError("training run dataset version does not match admission")
    if canonical_digest(run.exact_config) != run.config_digest:
        raise ValueError("training configuration digest mismatch")
