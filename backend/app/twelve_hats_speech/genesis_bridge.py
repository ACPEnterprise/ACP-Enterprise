"""Fail-closed admission bridge from Voice Genesis to speech training authority.

The bridge validates metadata only. It does not read audio, alter either source
manifest, start training, or make the speech engine inference-ready.
"""

from __future__ import annotations

from datetime import datetime

from app.lia.voice_genesis import (
    AdmissionStatus,
    DatasetManifest,
    QualityStatus,
    RightsApprovalStatus,
    RightsLedgerAsset,
)

from .contracts import (
    DatasetAdmissionState,
    DatasetRightsStatus,
    SpeechDatasetVersion,
)
from .governance import canonical_digest


def qualify_genesis_dataset(
    *,
    manifest: DatasetManifest,
    rights_ledger: tuple[RightsLedgerAsset, ...],
    dataset_id: str,
    language: str,
    admitted_at: datetime,
) -> SpeechDatasetVersion:
    """Produce engine authority only for an exact, fully admitted Genesis dataset."""
    if not manifest.assets:
        raise ValueError("speech dataset cannot be qualified without admitted assets")
    if admitted_at.tzinfo is None or admitted_at.utcoffset() is None:
        raise ValueError("speech dataset admission time must be timezone-aware")

    ledger_by_id = {entry.asset_id: entry for entry in rights_ledger}
    if len(ledger_by_id) != len(rights_ledger):
        raise ValueError("rights ledger asset IDs must be unique")

    manifest_ids = {asset.asset_id for asset in manifest.assets}
    if set(ledger_by_id) != manifest_ids:
        raise ValueError("rights ledger must exactly cover the dataset assets")

    for asset in manifest.assets:
        entry = ledger_by_id[asset.asset_id]
        if entry.dataset_version != manifest.dataset_version:
            raise ValueError(f"asset {asset.asset_id} is not bound to this dataset version")
        if entry.source_file_digest != asset.source_file_digest:
            raise ValueError(f"asset {asset.asset_id} source digest disagrees with rights ledger")
        if entry.transcript_digest != asset.transcript_digest:
            raise ValueError(f"asset {asset.asset_id} transcript digest disagrees with rights ledger")
        if (
            entry.admission_status is not AdmissionStatus.ADMITTED
            or entry.approval_status is not RightsApprovalStatus.APPROVED
            or entry.quality_status is not QualityStatus.PASSED
        ):
            raise PermissionError(f"asset {asset.asset_id} is not fully admitted")
        if entry.recording_owner != "TWELVE_HATS":
            raise PermissionError(f"asset {asset.asset_id} is not Twelve Hats owned")
        if entry.exclusivity_status != "EXCLUSIVE_TWELVE_HATS":
            raise PermissionError(f"asset {asset.asset_id} lacks exclusive Twelve Hats rights")

    ordered_ledger = tuple(
        ledger_by_id[asset_id] for asset_id in sorted(ledger_by_id)
    )
    rights_evidence_digest = canonical_digest(
        {
            "contract": "LIA_VOICE_RIGHTS_EVIDENCE.v1",
            "dataset_version": manifest.dataset_version,
            "assets": [entry.model_dump(mode="json") for entry in ordered_ledger],
        }
    )
    provenance_digest = canonical_digest(
        {
            "contract": "TWELVE_HATS_SPEECH_GENESIS_PROVENANCE.v1",
            "genesis_manifest_digest": manifest.manifest_digest,
            "rights_evidence_digest": rights_evidence_digest,
            "corpus_version": manifest.corpus_version,
            "pronunciation_version": manifest.pronunciation_version,
            "asset_ids": sorted(manifest_ids),
        }
    )

    return SpeechDatasetVersion(
        dataset_id=dataset_id,
        dataset_version=manifest.dataset_version,
        manifest_digest=_bare_sha256(manifest.manifest_digest),
        admission_state=DatasetAdmissionState.QUALIFIED,
        rights_status=DatasetRightsStatus.TWELVE_HATS_OWNED,
        rights_evidence_digest=rights_evidence_digest,
        provenance_digest=provenance_digest,
        language=language,
        admitted_at=admitted_at,
    )


def _bare_sha256(value: str) -> str:
    prefix = "sha256:"
    if not value.startswith(prefix):
        raise ValueError("Genesis digest must use the sha256 prefix")
    return value.removeprefix(prefix)
