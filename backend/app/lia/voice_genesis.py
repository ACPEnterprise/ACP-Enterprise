"""Fail-closed contracts for Twelve Hats-owned LIA voice training data.

This module performs metadata validation only. It does not read audio, upload data,
train a model, render speech, or mutate an admitted dataset.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GenesisModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AdmissionStatus(StrEnum):
    PROPOSED = "PROPOSED"
    RIGHTS_PENDING = "RIGHTS_PENDING"
    QUALITY_PENDING = "QUALITY_PENDING"
    ADMITTED = "ADMITTED"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"


class RightsApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"


class QualityStatus(StrEnum):
    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    CALIBRATION_PENDING = "CALIBRATION_PENDING"


class RightsLedgerAsset(GenesisModel):
    schema_version: str = "LIA_VOICE_RIGHTS_LINEAGE.v1"
    asset_id: str = Field(pattern=r"^LIA-AUDIO-[A-Z0-9-]+$")
    session_id: str = Field(pattern=r"^LIA-SESSION-[A-Z0-9-]+$")
    source_person_or_source_class: str
    acquisition_date: date
    capture_location_class: str = Field(min_length=1)
    recording_owner: str = Field(min_length=1)
    rights_document_reference: str = Field(min_length=1)
    synthetic_voice_training_right: bool
    model_training_right: bool
    derivative_model_right: bool
    commercial_use_right: bool
    perpetual_use_right: bool
    exclusivity_status: str
    revocation_constraints: str
    territorial_scope: str
    data_retention_rule: str
    deletion_rule: str
    approval_status: RightsApprovalStatus
    approver: str
    checksum: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    source_file_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    transcript_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    quality_status: QualityStatus
    quarantine_reason: str | None = None
    dataset_version: str | None = None
    admission_status: AdmissionStatus

    @model_validator(mode="after")
    def admitted_assets_are_fully_qualified(self) -> RightsLedgerAsset:
        if self.admission_status is not AdmissionStatus.ADMITTED:
            return self
        rights = (
            self.synthetic_voice_training_right,
            self.model_training_right,
            self.derivative_model_right,
            self.commercial_use_right,
            self.perpetual_use_right,
        )
        if not all(rights):
            raise ValueError("ADMITTED assets require every enumerated training right")
        if self.recording_owner != "TWELVE_HATS":
            raise ValueError("ADMITTED assets require Twelve Hats recording ownership")
        if self.source_person_or_source_class in PROHIBITED_SOURCE_CLASSES:
            raise ValueError("ADMITTED assets cannot use a prohibited source class")
        if self.exclusivity_status != "EXCLUSIVE_TWELVE_HATS":
            raise ValueError("ADMITTED assets require unambiguous Twelve Hats exclusivity")
        if self.approval_status is not RightsApprovalStatus.APPROVED:
            raise ValueError("ADMITTED assets require approved rights evidence")
        if self.quality_status is not QualityStatus.PASSED:
            raise ValueError("ADMITTED assets require passed technical quality")
        if self.quarantine_reason is not None:
            raise ValueError("ADMITTED assets cannot retain a quarantine reason")
        return self


class RecordingCorpusItem(GenesisModel):
    corpus_item_id: str = Field(pattern=r"^LIA-CORPUS-[A-Z0-9-]+$")
    text: str = Field(min_length=2)
    category: str
    intended_delivery: str
    difficulty: str
    important_tokens: tuple[str, ...]
    response_mode: str = Field(pattern=r"^(BRIEF|NORMAL|DETAILED|EVIDENCE)$")
    required_material_values: tuple[str, ...]
    prohibited_distortions: tuple[str, ...]

    @model_validator(mode="after")
    def required_values_exist_verbatim(self) -> RecordingCorpusItem:
        missing = [value for value in self.required_material_values if value not in self.text]
        if missing:
            raise ValueError(f"required material values missing from corpus text: {missing}")
        return self


class DatasetAsset(GenesisModel):
    asset_id: str
    source_file_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    transcript_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    rights_status: RightsApprovalStatus
    quality_status: QualityStatus
    admission_status: AdmissionStatus


class DatasetManifest(GenesisModel):
    schema_version: str = "LIA_VOICE_DATASET_MANIFEST.v1"
    dataset_version: str
    corpus_version: str
    pronunciation_version: str
    assets: tuple[DatasetAsset, ...]
    manifest_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")

    @model_validator(mode="after")
    def only_admitted_unique_assets(self) -> DatasetManifest:
        ids = [asset.asset_id for asset in self.assets]
        if len(ids) != len(set(ids)):
            raise ValueError("dataset asset IDs must be unique")
        for asset in self.assets:
            if asset.admission_status is not AdmissionStatus.ADMITTED:
                raise ValueError("dataset includes an asset that is not ADMITTED")
            if asset.rights_status is not RightsApprovalStatus.APPROVED:
                raise ValueError("dataset includes an asset without approved rights")
            if asset.quality_status is not QualityStatus.PASSED:
                raise ValueError("dataset includes an asset without passed quality")
        expected = dataset_digest(
            dataset_version=self.dataset_version,
            corpus_version=self.corpus_version,
            pronunciation_version=self.pronunciation_version,
            assets=self.assets,
        )
        if self.manifest_digest != expected:
            raise ValueError("dataset manifest digest is not reproducible")
        return self


def dataset_digest(
    *,
    dataset_version: str,
    corpus_version: str,
    pronunciation_version: str,
    assets: tuple[DatasetAsset, ...],
) -> str:
    payload = {
        "dataset_version": dataset_version,
        "corpus_version": corpus_version,
        "pronunciation_version": pronunciation_version,
        "assets": [
            asset.model_dump(mode="json")
            for asset in sorted(assets, key=lambda item: item.asset_id)
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


PII_PATTERNS = (
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"\b(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}\b"),
)


def validate_non_pii_corpus(items: tuple[RecordingCorpusItem, ...]) -> None:
    for item in items:
        if any(pattern.search(item.text) for pattern in PII_PATTERNS):
            raise ValueError(f"possible PII in corpus item {item.corpus_item_id}")


def load_expanded_corpus(source: dict[str, Any]) -> tuple[RecordingCorpusItem, ...]:
    if source.get("schema_version") != "LIA_VOICE_RECORDING_CORPUS.v1":
        raise ValueError("unsupported corpus schema")
    items: list[RecordingCorpusItem] = []
    seen: set[str] = set()
    for block in source.get("blocks", []):
        defaults = {
            "category": block["category"],
            "intended_delivery": block["intended_delivery"],
            "difficulty": block["difficulty"],
            "response_mode": block["response_mode"],
            "prohibited_distortions": tuple(block["prohibited_distortions"]),
        }
        for raw in block["items"]:
            item = RecordingCorpusItem.model_validate({**defaults, **raw})
            if item.corpus_item_id in seen:
                raise ValueError(f"duplicate corpus item ID: {item.corpus_item_id}")
            seen.add(item.corpus_item_id)
            items.append(item)
    result = tuple(items)
    validate_non_pii_corpus(result)
    return result


DISALLOWED_PRODUCTION_PROVIDERS = frozenset(
    {"ELEVENLABS", "AZURE_SPEECH", "GOOGLE_TTS", "AMAZON_POLLY"}
)

PROHIBITED_SOURCE_CLASSES = frozenset(
    {
        "SCRAPED_VOICE",
        "CELEBRITY_OR_PERSONALITY_RECORDING",
        "CUSTOMER_CALL",
        "EMPLOYEE_CALL",
        "VOICEMAIL",
        "MEETING_RECORDING",
        "PRODUCTION_TELEPHONE_AUDIO",
        "UNSANCTIONED_PERSONAL_RECORDING",
        "FOUND_ON_DEVICE_REFERENCE_AUDIO",
        "COMMERCIAL_TTS_SYNTHETIC_AUDIO",
    }
)


def validate_production_voice_policy(policy: dict[str, Any]) -> None:
    if policy.get("production_engine") != "TWELVE_HATS_SPEECH":
        raise ValueError("production voice engine must be TWELVE_HATS_SPEECH")
    dependencies = {str(value).upper() for value in policy.get("runtime_dependencies", [])}
    if dependencies & DISALLOWED_PRODUCTION_PROVIDERS:
        raise ValueError("production voice policy contains an outside speech provider")
    if policy.get("external_runtime_speech_dependency") is not False:
        raise ValueError("production voice must not depend on external speech runtime")
