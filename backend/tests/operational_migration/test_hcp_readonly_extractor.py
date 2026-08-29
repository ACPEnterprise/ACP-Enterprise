import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.operational_migration.hcp_readonly_extractor import (
    HcpReadOnlyConfig,
    NativeIdentityRegistry,
    ProtectedEvidenceStore,
    parse_collection,
    qualify_records,
)
from app.operational_migration.hcp_source_acquisition import (
    AcquisitionMechanism,
    SnapshotIdentity,
)


def snap() -> SnapshotIdentity:
    now = datetime(2026, 8, 26, tzinfo=timezone.utc)
    return SnapshotIdentity("fixture", now, AcquisitionMechanism.PUBLIC_API, "fixture", "page=1", now, now, 1, 1, "a" * 64)


def test_config_is_mode_and_host_gated_without_secret_repr(tmp_path: Path) -> None:
    secret = tmp_path / "hcp.env"
    secret.write_text("HOUSECALL_PRO_API_KEY=fixture-secret\nHOUSECALL_PRO_API_BASE=https://api.housecallpro.com\n")
    secret.chmod(0o600)
    config = HcpReadOnlyConfig.load(secret)
    assert "fixture-secret" not in repr(config)
    secret.chmod(0o644)
    with pytest.raises(ValueError, match="0600"):
        HcpReadOnlyConfig.load(secret)


def test_protected_store_is_write_once(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    store = ProtectedEvidenceStore(root)
    artifact = store.write_once("page-1.json", b"{}")
    assert artifact.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        store.write_once("page-1.json", b"changed")


def test_collection_and_envelopes_preserve_missing_relationships() -> None:
    body = json.dumps({"jobs": [{"id": "j1", "work_status": "open", "customer_id": "c1"}], "page": 1, "page_size": 1, "total_items": 1, "total_pages": 1}).encode()
    records, pagination = parse_collection(body, "jobs")
    envelopes = qualify_records(native_entity="job", records=records, snapshot=snap(), status_field="work_status", created_field="created_at", updated_field="updated_at", relationship_fields={"customer": "customer:customer_id", "invoice": "invoice:invoice_id"})
    assert pagination["total_pages"] == 1
    assert envelopes[0].source_status == "open"
    assert [(r.relationship, r.parent_native_id) for r in envelopes[0].relationships] == [("customer", "c1")]
    assert envelopes[0].source_created_at is None


def test_conflicting_duplicate_native_id_is_rejected() -> None:
    first = qualify_records(native_entity="job", records=[{"id": "j1", "work_status": "open"}], snapshot=snap(), status_field="work_status", created_field=None, updated_field=None, relationship_fields={})[0]
    second = qualify_records(native_entity="job", records=[{"id": "j1", "work_status": "completed"}], snapshot=snap(), status_field="work_status", created_field=None, updated_field=None, relationship_fields={})[0]
    registry = NativeIdentityRegistry()
    assert registry.accept(first)
    with pytest.raises(ValueError, match="conflicting duplicate"):
        registry.accept(second)
