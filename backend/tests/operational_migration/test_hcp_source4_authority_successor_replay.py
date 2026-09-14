from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from app.customers.models import Customer
from app.operational_migration.hcp_current_overlay import OverlayJournalEntry
from app.operational_migration.hcp_source4_authority_successor_replay import (
    CONTRACT,
    PURPOSE,
    VERIFIER_VERSION,
    ReplaySuccessorAuthority,
    ReplayVerificationError,
    _row_snapshot,
    _verify_records,
    schema_semantic_digest,
)

from backend.tests.operational_migration.test_hcp_current_overlay_v4 import (
    _packet,
    _write_packet,
)

DIGEST = "9" * 64


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _authority(tmp_path: Path) -> ReplaySuccessorAuthority:
    os.chmod(tmp_path, 0o700)
    packet = _packet()
    v4 = tmp_path / "v4.json"
    _write_packet(v4, packet)
    original = {
        "contract": "hcp-current-overlay-native-execution/v3",
        "protected_sha": "a" * 40,
        "deployed_sha": "a" * 40,
        "executor_version": "migration.hcp.current.overlay.v4.executor.1",
        "schema_head": "h8j0l2n4p6r8",
        "overlay_file_sha256": _file_digest(v4),
        "overlay_semantic_digest": packet["digest"],
        "complete_current_graph_digest": packet["complete_current_graph_digest"],
        "source4_package_digest": packet["base_source4_digest"],
        "v3_predecessor_digest": packet["v3_predecessor_digest"],
        "original_overlay_digest": packet["original_overlay_manifest_digest"],
        "hold_packet_digest": packet["hold_packet_sha256"],
        "update_cohort_digest": packet["update_cohort_authority_digest"],
        "runtime_inventory_digest": packet["runtime_inventory_sha256"],
        "preview_baseline_semantic_digest": packet["preview_baseline_semantic_digest"],
        "company_id": packet["company_id"],
        "branch_id": packet["branch_id"],
        "idempotency_identity": "8" * 64,
        "backup_digest": "7" * 64,
        "restore_receipt_digest": "6" * 64,
    }
    original_path = tmp_path / "original-authority.json"
    original_path.write_text(json.dumps(original))
    os.chmod(original_path, 0o600)
    return ReplaySuccessorAuthority(
        purpose=PURPOSE,
        original_protected_sha=original["protected_sha"],
        original_deployed_sha=original["deployed_sha"],
        original_executor_version=original["executor_version"],
        original_schema_head=original["schema_head"],
        original_execution_authority_path=original_path,
        original_execution_authority_sha256=_file_digest(original_path),
        original_backup_digest=original["backup_digest"],
        original_restore_receipt_digest=original["restore_receipt_digest"],
        original_execution_timestamp="2026-09-14T20:00:00+00:00",
        original_receipt_digest=DIGEST,
        successor_protected_sha="b" * 40,
        successor_deployed_sha="b" * 40,
        successor_executor_version=VERIFIER_VERSION,
        current_schema_head="h8j0l2n4p6r8",
        schema_semantic_digest=schema_semantic_digest(),
        expected_database="acp_enterprise_preview",
        company_id=UUID(str(packet["company_id"])),
        branch_id=UUID(str(packet["branch_id"])),
        actor_id=uuid4(),
        v4_path=v4,
        v4_file_sha256=_file_digest(v4),
        v4_semantic_digest=packet["digest"],
        complete_current_graph_digest=packet["complete_current_graph_digest"],
        source4_package_digest=packet["base_source4_digest"],
        predecessor_overlay_digest=packet["v3_predecessor_digest"],
        original_overlay_digest=packet["original_overlay_manifest_digest"],
        hold_digest=packet["hold_packet_sha256"],
        cohort_digest=packet["update_cohort_authority_digest"],
        runtime_inventory_digest=packet["runtime_inventory_sha256"],
        preview_baseline_digest=packet["preview_baseline_semantic_digest"],
        idempotency_identity=original["idempotency_identity"],
        source_binding_digest=DIGEST,
        native_post_state_digest=DIGEST,
        hold_state_digest=DIGEST,
        business_event_digest=DIGEST,
        business_event_count=100,
        child_lineage_digest=DIGEST,
    )


def test_authority_successor_preserves_version_separation_and_all_bindings(
    tmp_path: Path,
) -> None:
    authority = _authority(tmp_path)
    packet = json.loads(authority.v4_path.read_bytes())
    object.__setattr__(authority, "company_id", uuid4())
    with pytest.raises(ReplayVerificationError) as error:
        authority.verify_files()
    assert any(
        failure["reason"] == "company_id_mismatch" for failure in error.value.failures
    )
    object.__setattr__(authority, "company_id", UUID(str(packet["company_id"])))
    object.__setattr__(authority, "branch_id", UUID(str(packet["branch_id"])))
    assert len(authority.verify_files().manifest.records) == 522


def test_authority_loader_rejects_mutation_authority_contract(tmp_path: Path) -> None:
    path = tmp_path / "authority.json"
    path.write_text(json.dumps({"contract": "hcp-current-overlay-native-execution/v3"}))
    os.chmod(path, 0o600)
    with pytest.raises(ValueError, match="contract mismatch"):
        ReplaySuccessorAuthority.load(path)


class _ReadOnlyServices:
    def __init__(self, states: dict[object, object]) -> None:
        self.states = states

    async def persisted_source_state(self, _session, key):
        return self.states.get(key)


@pytest.mark.asyncio
async def test_complete_record_verification_is_non_mutating_and_aggregates(
    tmp_path: Path,
) -> None:
    authority = _authority(tmp_path)
    packet = json.loads(authority.v4_path.read_bytes())
    object.__setattr__(authority, "company_id", UUID(str(packet["company_id"])))
    object.__setattr__(authority, "branch_id", UUID(str(packet["branch_id"])))
    overlay = authority.verify_files()
    states = {}
    journal = []
    for number, record in enumerate(overlay.manifest.records):
        successor = overlay.successor_assertions[record.key]
        native_id = None if successor == "HOLD" else str(uuid4())
        outcome = {
            "CREATE_NEW": "created",
            "REUSE_EXISTING": "idempotent_replay",
            "UPDATE_EXISTING": "updated",
            "HOLD": "held",
        }[successor]
        journal.append(
            OverlayJournalEntry(
                record.key,
                record.assertion,
                outcome,
                None,
                record.source_digest,
                native_id,
            )
        )
        if native_id:
            states[record.key] = SimpleNamespace(
                native_id=native_id, source_digest=record.source_digest
            )
    first = next(iter(states))
    states[first] = SimpleNamespace(native_id=str(uuid4()), source_digest="0" * 64)
    failures: list[dict[str, str]] = []

    await _verify_records(  # type: ignore[arg-type]
        object(), tuple(journal), overlay, _ReadOnlyServices(states), failures
    )

    first_failures = [
        item
        for item in failures
        if item["scope"] == f"{first.domain}:{first.source_id}"
    ]
    assert {item["reason"] for item in first_failures} == {
        "native_target_mismatch",
        "source_digest_mismatch",
    }


def test_schema_semantic_compatibility_digest_is_deterministic() -> None:
    assert schema_semantic_digest() == schema_semantic_digest()
    assert len(schema_semantic_digest()) == 64
    assert CONTRACT == "hcp-source4-authority-successor-replay/v1"


def test_row_snapshot_uses_mapped_attribute_keys_for_renamed_columns() -> None:
    customer = Customer()
    for attribute in Customer.__mapper__.column_attrs:
        setattr(customer, attribute.key, None)
    customer.marketing_source = "source-value"

    snapshot = _row_snapshot(customer)

    assert snapshot["marketing_source"] == "source-value"
    assert "source" not in snapshot
