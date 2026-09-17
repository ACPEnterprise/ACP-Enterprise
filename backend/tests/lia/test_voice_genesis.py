from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.lia.voice_genesis import (
    AdmissionStatus,
    DatasetAsset,
    DatasetManifest,
    QualityStatus,
    RightsLedgerAsset,
    dataset_digest,
    load_expanded_corpus,
    validate_production_voice_policy,
)

ROOT = Path(__file__).resolve().parents[3]
GENESIS = ROOT / "docs" / "architecture" / "lia" / "voice-genesis"
HEX_A = "a" * 64
HEX_B = "b" * 64


def _json(name: str) -> dict[str, object]:
    return json.loads((GENESIS / name).read_text())


def _rights(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "asset_id": "LIA-AUDIO-SYNTHETIC-001",
        "session_id": "LIA-SESSION-SYNTHETIC-001",
        "source_person_or_source_class": "SANCTIONED_CONTRIBUTOR_REFERENCE",
        "acquisition_date": "2026-09-17",
        "capture_location_class": "CONTROLLED_RECORDING_ROOM",
        "recording_owner": "TWELVE_HATS",
        "rights_document_reference": "RIGHTS-DOC-DIGEST-001",
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
        "approval_status": "APPROVED",
        "approver": "SYNTHETIC-APPROVER-REFERENCE",
        "checksum": f"sha256:{HEX_A}",
        "source_file_digest": f"sha256:{HEX_A}",
        "transcript_digest": f"sha256:{HEX_B}",
        "quality_status": "PASSED",
        "quarantine_reason": None,
        "dataset_version": None,
        "admission_status": "ADMITTED",
    }
    value.update(overrides)
    return value


def _dataset_asset(**overrides: object) -> DatasetAsset:
    value: dict[str, object] = {
        "asset_id": "LIA-AUDIO-SYNTHETIC-001",
        "source_file_digest": f"sha256:{HEX_A}",
        "transcript_digest": f"sha256:{HEX_B}",
        "rights_status": "APPROVED",
        "quality_status": "PASSED",
        "admission_status": "ADMITTED",
    }
    value.update(overrides)
    return DatasetAsset.model_validate(value)


def test_original_corpus_is_expanded_complete_and_non_pii() -> None:
    source = _json("recording-corpus.v1.json")
    items = load_expanded_corpus(source)

    assert len(items) == 64
    assert len({item.corpus_item_id for item in items}) == 64
    assert {
        "GENERAL_ENGLISH",
        "NUMBERS_REFERENCES",
        "FINANCIAL_BUSINESS",
        "TIME_PERIODS",
        "TRADES_SERVICE_BUSINESS",
        "PAYROLL_WORKFORCE",
        "LIA_EVIDENCE_BEHAVIOR",
        "CLARIFICATION_AND_DENIAL",
    } == {item.category for item in items}
    assert source["ownership"] == "ORIGINAL_TWELVE_HATS_TEXT"
    assert source["fictional_non_pii"] is True


def test_malformed_and_duplicate_corpus_items_fail_closed() -> None:
    source = _json("recording-corpus.v1.json")
    first_block = source["blocks"][0]  # type: ignore[index]
    first_item = first_block["items"][0]  # type: ignore[index]
    first_item["required_material_values"] = ["value not present"]  # type: ignore[index]
    with pytest.raises(ValidationError, match="required material values"):
        load_expanded_corpus(source)

    source = _json("recording-corpus.v1.json")
    first_block = source["blocks"][0]  # type: ignore[index]
    first_block["items"].append(dict(first_block["items"][0]))  # type: ignore[index]
    with pytest.raises(ValueError, match="duplicate corpus item ID"):
        load_expanded_corpus(source)


@pytest.mark.parametrize("field", ("asset_id", "checksum", "transcript_digest"))
def test_missing_identity_or_digest_is_inadmissible(field: str) -> None:
    candidate = _rights()
    candidate.pop(field)
    with pytest.raises(ValidationError):
        RightsLedgerAsset.model_validate(candidate)


@pytest.mark.parametrize(
    ("overrides", "message"),
    (
        ({"commercial_use_right": False}, "every enumerated training right"),
        ({"exclusivity_status": "NON_EXCLUSIVE"}, "Twelve Hats exclusivity"),
        ({"exclusivity_status": "AMBIGUOUS"}, "Twelve Hats exclusivity"),
        ({"approval_status": "PENDING"}, "approved rights evidence"),
        ({"quality_status": "CALIBRATION_PENDING"}, "passed technical quality"),
    ),
)
def test_admission_requires_complete_rights_and_quality(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        RightsLedgerAsset.model_validate(_rights(**overrides))


def test_quarantined_asset_remains_outside_admitted_dataset() -> None:
    asset = RightsLedgerAsset.model_validate(
        _rights(
            admission_status="QUARANTINED",
            quality_status="FAILED",
            quarantine_reason="SYNTHETIC_TEST_NOISE",
        )
    )
    assert asset.admission_status is AdmissionStatus.QUARANTINED
    assert asset.quality_status is QualityStatus.FAILED


@pytest.mark.parametrize(
    "overrides",
    (
        {"recording_owner": "OUTSIDE_OWNER"},
        {"source_person_or_source_class": "CUSTOMER_CALL"},
        {"source_person_or_source_class": "COMMERCIAL_TTS_SYNTHETIC_AUDIO"},
    ),
)
def test_outside_ownership_or_prohibited_source_cannot_be_admitted(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        RightsLedgerAsset.model_validate(_rights(**overrides))


@pytest.mark.parametrize("status", ("REJECTED", "REVOKED"))
def test_rejected_or_revoked_asset_cannot_enter_dataset(status: str) -> None:
    asset = _dataset_asset(admission_status=status)
    digest = dataset_digest(
        dataset_version="lia-dataset.test.v1",
        corpus_version="lia-corpus.test.v1",
        pronunciation_version="lia-pronunciation.test.v1",
        assets=(asset,),
    )
    with pytest.raises(ValidationError, match="not ADMITTED"):
        DatasetManifest(
            dataset_version="lia-dataset.test.v1",
            corpus_version="lia-corpus.test.v1",
            pronunciation_version="lia-pronunciation.test.v1",
            assets=(asset,),
            manifest_digest=digest,
        )


def test_dataset_identity_is_order_independent_and_reproducible() -> None:
    first = _dataset_asset()
    second = _dataset_asset(
        asset_id="LIA-AUDIO-SYNTHETIC-002",
        source_file_digest=f"sha256:{HEX_B}",
        transcript_digest=f"sha256:{HEX_A}",
    )
    values = {
        "dataset_version": "lia-dataset.test.v1",
        "corpus_version": "lia-recording-corpus.test.v1",
        "pronunciation_version": "lia-pronunciation.test.v1",
    }
    forward = dataset_digest(assets=(first, second), **values)
    reverse = dataset_digest(assets=(second, first), **values)
    assert forward == reverse
    manifest = DatasetManifest(
        **values,
        assets=(second, first),
        manifest_digest=forward,
    )
    assert manifest.manifest_digest == forward
    with pytest.raises(ValidationError, match="not reproducible"):
        DatasetManifest(
            **values,
            assets=(first, second),
            manifest_digest=f"sha256:{HEX_A}",
        )


def test_duplicate_dataset_asset_id_fails_closed() -> None:
    asset = _dataset_asset()
    digest = dataset_digest(
        dataset_version="lia-dataset.test.v1",
        corpus_version="lia-corpus.test.v1",
        pronunciation_version="lia-pronunciation.test.v1",
        assets=(asset, asset),
    )
    with pytest.raises(ValidationError, match="must be unique"):
        DatasetManifest(
            dataset_version="lia-dataset.test.v1",
            corpus_version="lia-corpus.test.v1",
            pronunciation_version="lia-pronunciation.test.v1",
            assets=(asset, asset),
            manifest_digest=digest,
        )


def test_production_policy_has_no_outside_provider_or_runtime_dependency() -> None:
    policy = _json("lia-voice-identity.v1.json")
    validate_production_voice_policy(policy)
    for provider in ("ELEVENLABS", "AZURE_SPEECH", "GOOGLE_TTS", "AMAZON_POLLY"):
        with pytest.raises(ValueError, match="outside speech provider"):
            validate_production_voice_policy(
                {**policy, "runtime_dependencies": [provider]}
            )


def test_all_genesis_json_artifacts_are_parseable_without_secrets() -> None:
    artifacts = tuple(sorted(GENESIS.glob("*.json")))
    assert len(artifacts) >= 7
    combined = ""
    for artifact in artifacts:
        combined += json.dumps(json.loads(artifact.read_text()))
    assert "BEGIN PRIVATE KEY" not in combined
    assert "api_key" not in combined.casefold()
    assert "New Recording.m4a" not in combined or "REFERENCE_MEASUREMENT_PENDING" in combined


def test_pii_injected_into_generated_corpus_fixture_is_rejected() -> None:
    source = _json("recording-corpus.v1.json")
    block = source["blocks"][0]  # type: ignore[index]
    block["items"][0]["text"] = "Send the result to person@example.com."  # type: ignore[index]
    with pytest.raises(ValueError, match="possible PII"):
        load_expanded_corpus(source)
