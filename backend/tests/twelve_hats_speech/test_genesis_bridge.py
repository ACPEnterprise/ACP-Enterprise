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
from app.twelve_hats_speech.contracts import (
    DatasetAdmissionState,
    DatasetRightsStatus,
)
from app.twelve_hats_speech.genesis_bridge import qualify_genesis_dataset

SHA_A = "a" * 64
SHA_B = "b" * 64
NOW = datetime(2026, 9, 17, 14, 0, tzinfo=timezone.utc)


def asset() -> DatasetAsset:
    return DatasetAsset(
        asset_id="LIA-AUDIO-0001",
        source_file_digest=f"sha256:{SHA_A}",
        transcript_digest=f"sha256:{SHA_B}",
        rights_status=RightsApprovalStatus.APPROVED,
        quality_status=QualityStatus.PASSED,
        admission_status=AdmissionStatus.ADMITTED,
    )


def manifest(item: DatasetAsset | None = None) -> DatasetManifest:
    assets = (item or asset(),)
    return DatasetManifest(
        dataset_version="lia-dataset.v1",
        corpus_version="lia-recording-corpus.v1",
        pronunciation_version="lia-pronunciation.v1",
        assets=assets,
        manifest_digest=dataset_digest(
            dataset_version="lia-dataset.v1",
            corpus_version="lia-recording-corpus.v1",
            pronunciation_version="lia-pronunciation.v1",
            assets=assets,
        ),
    )


def ledger(**overrides: object) -> RightsLedgerAsset:
    values: dict[str, object] = {
        "asset_id": "LIA-AUDIO-0001",
        "session_id": "LIA-SESSION-0001",
        "source_person_or_source_class": "SANCTIONED_VOICE_CONTRIBUTOR",
        "acquisition_date": date(2026, 9, 17),
        "capture_location_class": "TWELVE_HATS_CONTROLLED",
        "recording_owner": "TWELVE_HATS",
        "rights_document_reference": "RIGHTS-DOC-REF-001",
        "synthetic_voice_training_right": True,
        "model_training_right": True,
        "derivative_model_right": True,
        "commercial_use_right": True,
        "perpetual_use_right": True,
        "exclusivity_status": "EXCLUSIVE_TWELVE_HATS",
        "revocation_constraints": "CONTRACT_REFERENCE_CONTROLS",
        "territorial_scope": "WORLDWIDE",
        "data_retention_rule": "RIGHTS_POLICY_REFERENCE",
        "deletion_rule": "RIGHTS_POLICY_REFERENCE",
        "approval_status": RightsApprovalStatus.APPROVED,
        "approver": "OWNER-REFERENCE",
        "checksum": f"sha256:{SHA_A}",
        "source_file_digest": f"sha256:{SHA_A}",
        "transcript_digest": f"sha256:{SHA_B}",
        "quality_status": QualityStatus.PASSED,
        "dataset_version": "lia-dataset.v1",
        "admission_status": AdmissionStatus.ADMITTED,
    }
    values.update(overrides)
    return RightsLedgerAsset.model_validate(values)


def qualify(
    *,
    current_manifest: DatasetManifest | None = None,
    entries: tuple[RightsLedgerAsset, ...] | None = None,
    admitted_at: datetime = NOW,
):
    return qualify_genesis_dataset(
        manifest=current_manifest or manifest(),
        rights_ledger=(ledger(),) if entries is None else entries,
        dataset_id="lia-owned-dataset",
        language="en-US",
        admitted_at=admitted_at,
    )


def test_exact_admitted_genesis_dataset_becomes_training_authority() -> None:
    result = qualify()

    assert result.admission_state is DatasetAdmissionState.QUALIFIED
    assert result.rights_status is DatasetRightsStatus.TWELVE_HATS_OWNED
    assert result.manifest_digest == manifest().manifest_digest.removeprefix("sha256:")
    assert result.rights_evidence_digest is not None
    assert result.provenance_digest != result.rights_evidence_digest


def test_bridge_is_deterministic_for_unchanged_evidence() -> None:
    first = qualify()
    second = qualify()

    assert first == second
    assert first.rights_evidence_digest == second.rights_evidence_digest
    assert first.provenance_digest == second.provenance_digest


@pytest.mark.parametrize(
    "entries,match",
    (
        ((), "exactly cover"),
        ((ledger(asset_id="LIA-AUDIO-OTHER"),), "exactly cover"),
        ((ledger(dataset_version="other.v1"),), "not bound"),
        ((ledger(source_file_digest=f"sha256:{'c' * 64}"),), "source digest"),
        ((ledger(transcript_digest=f"sha256:{'c' * 64}"),), "transcript digest"),
    ),
)
def test_bridge_rejects_incomplete_or_disagreeing_lineage(
    entries: tuple[RightsLedgerAsset, ...], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        qualify(entries=entries)


def test_bridge_rejects_duplicate_rights_entries() -> None:
    with pytest.raises(ValueError, match="unique"):
        qualify(entries=(ledger(), ledger()))


def test_bridge_requires_timezone_aware_admission_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        qualify(admitted_at=datetime(2026, 9, 17, 14, 0))  # noqa: DTZ001


def test_bridge_does_not_expose_audio_or_create_runtime_authority() -> None:
    result = qualify()
    payload = result.model_dump()

    assert "audio" not in " ".join(payload).lower()
    assert "provider" not in payload
    assert "model_version" not in payload
