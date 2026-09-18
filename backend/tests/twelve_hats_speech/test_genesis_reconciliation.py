from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.lia.voice_genesis import (
    AdmissionStatus,
    DatasetAsset,
    DatasetManifest,
    QualityStatus,
    RightsApprovalStatus,
    RightsLedgerAsset,
    dataset_digest,
)
from app.twelve_hats_speech.contracts import SpeechTrainingRun, TrainingRunStatus
from app.twelve_hats_speech.genesis import admit_genesis_dataset_for_training
from app.twelve_hats_speech.governance import authorize_training, canonical_digest

HEX_A = "a" * 64
HEX_B = "b" * 64
DATASET_VERSION = "lia-dataset.test.v1"
NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)


def rights_asset(**overrides: object) -> RightsLedgerAsset:
    values: dict[str, object] = {
        "asset_id": "LIA-AUDIO-OWNED-001",
        "session_id": "LIA-SESSION-OWNED-001",
        "source_person_or_source_class": "SANCTIONED_CONTRIBUTOR_REFERENCE",
        "acquisition_date": date(2026, 9, 17),
        "capture_location_class": "CONTROLLED_RECORDING_ROOM",
        "recording_owner": "TWELVE_HATS",
        "rights_document_reference": "RIGHTS-EVIDENCE-001",
        "synthetic_voice_training_right": True,
        "model_training_right": True,
        "derivative_model_right": True,
        "commercial_use_right": True,
        "perpetual_use_right": True,
        "exclusivity_status": "EXCLUSIVE_TWELVE_HATS",
        "revocation_constraints": "PER_RIGHTS_REFERENCE",
        "territorial_scope": "WORLDWIDE",
        "data_retention_rule": "PER_RIGHTS_REFERENCE",
        "deletion_rule": "FUTURE_APPROVED_WORKFLOW_REQUIRED",
        "approval_status": RightsApprovalStatus.APPROVED,
        "approver": "APPROVER-REFERENCE",
        "checksum": f"sha256:{HEX_A}",
        "source_file_digest": f"sha256:{HEX_A}",
        "transcript_digest": f"sha256:{HEX_B}",
        "quality_status": QualityStatus.PASSED,
        "quarantine_reason": None,
        "dataset_version": DATASET_VERSION,
        "admission_status": AdmissionStatus.ADMITTED,
    }
    values.update(overrides)
    return RightsLedgerAsset.model_validate(values)


def manifest(asset: RightsLedgerAsset | None = None) -> DatasetManifest:
    rights = asset or rights_asset()
    dataset_asset = DatasetAsset(
        asset_id=rights.asset_id,
        source_file_digest=rights.source_file_digest,
        transcript_digest=rights.transcript_digest,
        rights_status=rights.approval_status,
        quality_status=rights.quality_status,
        admission_status=rights.admission_status,
    )
    digest = dataset_digest(
        dataset_version=DATASET_VERSION,
        corpus_version="lia-recording-corpus.v1",
        pronunciation_version="lia-pronunciation.v1",
        assets=(dataset_asset,),
    )
    return DatasetManifest(
        dataset_version=DATASET_VERSION,
        corpus_version="lia-recording-corpus.v1",
        pronunciation_version="lia-pronunciation.v1",
        assets=(dataset_asset,),
        manifest_digest=digest,
    )


def training_run() -> SpeechTrainingRun:
    config = {"architecture": "unselected", "batch_size": 8}
    return SpeechTrainingRun(
        training_run_id="training-run-1",
        code_revision="c" * 40,
        dataset_version=DATASET_VERSION,
        model_architecture_version="unselected.v1",
        exact_config=config,
        config_digest=canonical_digest(config),
        random_seeds=(42,),
        hardware_profile="not allocated",
        status=TrainingRunStatus.PLANNED,
        metrics_schema_version="speech-training-metrics.v1",
    )


def test_exact_genesis_evidence_projects_to_training_admission() -> None:
    rights = rights_asset()
    admitted = admit_genesis_dataset_for_training(
        manifest=manifest(rights), rights_assets=(rights,), admitted_at=NOW
    )

    assert admitted.dataset_version == DATASET_VERSION
    assert admitted.manifest_digest == manifest(rights).manifest_digest.removeprefix(
        "sha256:"
    )
    assert admitted.rights_evidence_digest is not None
    authorize_training(admitted, training_run())


def test_rights_projection_is_order_independent() -> None:
    first = rights_asset()
    second = rights_asset(
        asset_id="LIA-AUDIO-OWNED-002",
        session_id="LIA-SESSION-OWNED-002",
        checksum=f"sha256:{HEX_B}",
        source_file_digest=f"sha256:{HEX_B}",
        transcript_digest=f"sha256:{HEX_A}",
    )
    assets = tuple(
        DatasetAsset(
            asset_id=value.asset_id,
            source_file_digest=value.source_file_digest,
            transcript_digest=value.transcript_digest,
            rights_status=value.approval_status,
            quality_status=value.quality_status,
            admission_status=value.admission_status,
        )
        for value in (first, second)
    )
    current_manifest = DatasetManifest(
        dataset_version=DATASET_VERSION,
        corpus_version="lia-recording-corpus.v1",
        pronunciation_version="lia-pronunciation.v1",
        assets=assets,
        manifest_digest=dataset_digest(
            dataset_version=DATASET_VERSION,
            corpus_version="lia-recording-corpus.v1",
            pronunciation_version="lia-pronunciation.v1",
            assets=assets,
        ),
    )

    forward = admit_genesis_dataset_for_training(
        manifest=current_manifest, rights_assets=(first, second), admitted_at=NOW
    )
    reverse = admit_genesis_dataset_for_training(
        manifest=current_manifest, rights_assets=(second, first), admitted_at=NOW
    )
    assert forward == reverse


@pytest.mark.parametrize(
    "rights_override",
    (
        {"dataset_version": "another-dataset.v1"},
        {"source_file_digest": f"sha256:{HEX_B}"},
        {"transcript_digest": f"sha256:{HEX_A}"},
    ),
)
def test_mismatched_binding_fails_closed(rights_override: dict[str, object]) -> None:
    canonical = rights_asset()
    current_manifest = manifest(canonical)
    contradictory = rights_asset(**rights_override)
    with pytest.raises((PermissionError, ValueError)):
        admit_genesis_dataset_for_training(
            manifest=current_manifest,
            rights_assets=(contradictory,),
            admitted_at=NOW,
        )


def test_missing_extra_duplicate_or_unbound_rights_fail_closed() -> None:
    rights = rights_asset()
    current_manifest = manifest(rights)
    with pytest.raises(PermissionError, match="bind exactly"):
        admit_genesis_dataset_for_training(
            manifest=current_manifest, rights_assets=(), admitted_at=NOW
        )
    with pytest.raises(ValueError, match="duplicate"):
        admit_genesis_dataset_for_training(
            manifest=current_manifest,
            rights_assets=(rights, rights),
            admitted_at=NOW,
        )
    with pytest.raises(PermissionError, match="bind exactly"):
        admit_genesis_dataset_for_training(
            manifest=current_manifest,
            rights_assets=(
                rights,
                rights_asset(
                    asset_id="LIA-AUDIO-OWNED-002",
                    session_id="LIA-SESSION-OWNED-002",
                ),
            ),
            admitted_at=NOW,
        )


def test_naive_admission_timestamp_is_rejected() -> None:
    rights = rights_asset()
    with pytest.raises(ValueError, match="timezone-aware"):
        admit_genesis_dataset_for_training(
            manifest=manifest(rights),
            rights_assets=(rights,),
            admitted_at=NOW.replace(tzinfo=None),
        )
