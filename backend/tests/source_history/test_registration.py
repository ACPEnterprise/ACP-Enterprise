from dataclasses import replace
from uuid import UUID

import pytest
from app.source_history.registration import (
    SealedSourceManifest,
    canonical_manifest_digest,
    register_sealed_source,
)

COMPANY = UUID("10000000-0000-0000-0000-000000000001")
OTHER_COMPANY = UUID("10000000-0000-0000-0000-000000000002")


def manifest() -> SealedSourceManifest:
    draft = SealedSourceManifest(
        "housecall_pro", COMPANY, "a" * 64, 12, "2026-11-25T00:00:00Z", True, ""
    )
    return replace(draft, manifest_digest=canonical_manifest_digest(draft))


def test_registers_sealed_source_with_provenance_and_no_native_admission() -> None:
    first = register_sealed_source(manifest(), expected_company_id=COMPANY)
    second = register_sealed_source(manifest(), expected_company_id=COMPANY)
    assert first == second
    assert first.read_only is True
    assert first.admitted_as_native is False
    assert first.provenance["custody"] == "sealed_manifest"


def test_registration_is_tenant_scoped() -> None:
    with pytest.raises(PermissionError, match="tenant binding"):
        register_sealed_source(manifest(), expected_company_id=OTHER_COMPANY)


def test_missing_or_changed_manifest_fails_closed() -> None:
    with pytest.raises(ValueError, match="unavailable"):
        register_sealed_source(None, expected_company_id=COMPANY)
    with pytest.raises(ValueError, match="checksum mismatch"):
        register_sealed_source(
            replace(manifest(), object_count=13), expected_company_id=COMPANY
        )
