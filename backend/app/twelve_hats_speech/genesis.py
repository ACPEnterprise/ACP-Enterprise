"""Exact adapter from canonical LIA Voice Genesis custody to engine admission."""

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


def admit_genesis_dataset_for_training(
    *,
    manifest: DatasetManifest,
    rights_assets: tuple[RightsLedgerAsset, ...],
    admitted_at: datetime,
) -> SpeechDatasetVersion:
    """Bind one exact admitted Genesis manifest to training eligibility.

    This function neither admits source assets nor grants rights. It only projects
    already-admitted canonical Genesis evidence into the engine contract.
    """
    if not manifest.assets:
        raise PermissionError("speech training dataset must contain admitted assets")
    if admitted_at.tzinfo is None or admitted_at.utcoffset() is None:
        raise ValueError("dataset admission timestamp must be timezone-aware")

    rights_by_id = {asset.asset_id: asset for asset in rights_assets}
    if len(rights_by_id) != len(rights_assets):
        raise ValueError("duplicate rights-ledger asset identity")
    manifest_ids = {asset.asset_id for asset in manifest.assets}
    if set(rights_by_id) != manifest_ids:
        raise PermissionError("dataset manifest and rights ledger do not bind exactly")

    for dataset_asset in manifest.assets:
        rights = rights_by_id[dataset_asset.asset_id]
        if rights.admission_status is not AdmissionStatus.ADMITTED:
            raise PermissionError("rights-ledger asset is not admitted")
        if rights.approval_status is not RightsApprovalStatus.APPROVED:
            raise PermissionError("rights-ledger asset is not rights-approved")
        if rights.quality_status is not QualityStatus.PASSED:
            raise PermissionError("rights-ledger asset did not pass quality")
        if rights.dataset_version != manifest.dataset_version:
            raise PermissionError("rights-ledger asset is not bound to this dataset")
        if rights.source_file_digest != dataset_asset.source_file_digest:
            raise ValueError("source file digest differs from rights authority")
        if rights.transcript_digest != dataset_asset.transcript_digest:
            raise ValueError("transcript digest differs from rights authority")

    ordered_rights = tuple(
        rights_by_id[asset_id] for asset_id in sorted(rights_by_id)
    )
    rights_evidence_digest = canonical_digest(
        {"rights_assets": [asset.model_dump(mode="json") for asset in ordered_rights]}
    )
    provenance_digest = canonical_digest(
        {
            "genesis_manifest_digest": manifest.manifest_digest,
            "rights_evidence_digest": rights_evidence_digest,
            "asset_ids": sorted(manifest_ids),
        }
    )
    return SpeechDatasetVersion(
        dataset_id="lia-voice-genesis",
        dataset_version=manifest.dataset_version,
        manifest_digest=_sha256_value(manifest.manifest_digest),
        admission_state=DatasetAdmissionState.QUALIFIED,
        rights_status=DatasetRightsStatus.TWELVE_HATS_OWNED,
        rights_evidence_digest=rights_evidence_digest,
        provenance_digest=provenance_digest,
        language="en-US",
        admitted_at=admitted_at,
    )


def _sha256_value(value: str) -> str:
    prefix = "sha256:"
    if not value.startswith(prefix):
        raise ValueError("Genesis digest must use the sha256 prefix")
    return value.removeprefix(prefix)
