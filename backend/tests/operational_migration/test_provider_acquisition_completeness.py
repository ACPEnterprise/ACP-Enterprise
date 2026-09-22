from __future__ import annotations

import hashlib
import json

import pytest
from app.operational_migration.provider_acquisition_completeness import (
    CONTRACT,
    ProviderCompletenessManifest,
)


def test_manifest_rejects_connected_as_complete_shortcut() -> None:
    providers = (
        {
            "provider": "test",
            "environment": "production",
            "final_completeness_disposition": "PARTIAL_SOURCE_ACQUISITION_NOT_MIGRATION_COMPLETE",
        },
    )
    invariants = {"connected_successfully_equals_migration_complete": False}
    payload = {"contract": CONTRACT, "providers": providers, "invariants": invariants}
    manifest = ProviderCompletenessManifest(
        **payload,
        digest=hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    )
    manifest.verify()


def test_manifest_rejects_provider_without_disposition() -> None:
    manifest = ProviderCompletenessManifest(
        contract=CONTRACT,
        providers=({"provider": "test", "environment": "production"},),
        invariants={},
        digest="invalid",
    )
    with pytest.raises(ValueError):
        manifest.verify()
