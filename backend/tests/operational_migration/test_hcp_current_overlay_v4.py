from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from app.operational_migration.hcp_current_overlay import OverlayKey
from app.operational_migration.hcp_current_overlay_v4 import (
    EXPECTED_COUNTS,
    V4ExecutableOverlay,
    preflight_v4,
)
from app.operational_migration.hcp_current_overlay_v4_command import (
    EXECUTOR_VERSION,
    V4ExecutionAuthority,
)

DIGEST = "a" * 64
ACQUIRED = "2026-09-12T16:49:00+00:00"


def _canonical_digest(value: dict[str, object]) -> str:
    unsigned = {key: item for key, item in value.items() if key != "digest"}
    return hashlib.sha256(
        (json.dumps(unsigned, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()


def _record(domain: str, number: int, successor: str) -> dict[str, object]:
    evidence: dict[str, object] = {
        "source_identity_present": False,
        "target_native_id": None,
    }
    if successor in {"REUSE_EXISTING", "UPDATE_EXISTING"}:
        evidence = {
            "exact_legacy_successor_evidence_digest": hashlib.sha256(
                f"evidence:{domain}:{number}".encode()
            ).hexdigest(),
            "target_native_id": str(uuid4()),
        }
    return {
        "domain": domain,
        "source_id": f"{domain}_{number:04d}",
        "source_digest": hashlib.sha256(
            f"source:{domain}:{number}".encode()
        ).hexdigest(),
        "acquired_at": ACQUIRED,
        "payload": {} if successor == "HOLD" else {"id": f"{domain}_{number:04d}"},
        "parent_keys": [],
        "original_assertion": "update" if successor == "UPDATE_EXISTING" else "create",
        "runtime_result": "NATIVE_SUCCESSOR_MISSING",
        "successor_assertion": successor,
        "reason": "qualified_test_evidence",
        "baseline_evidence": evidence,
    }


def _packet() -> dict[str, object]:
    current_spec = (
        [("customer", "CREATE_NEW")] * 7
        + [("customer", "REUSE_EXISTING")]
        + [("customer", "UPDATE_EXISTING")] * 3
        + [("service_location", "CREATE_NEW")] * 8
        + [("service_location", "REUSE_EXISTING")] * 3
        + [("job", "CREATE_NEW")] * 15
        + [("appointment", "CREATE_NEW")] * 18
    )
    records = [
        _record(domain, number, disposition)
        for number, (domain, disposition) in enumerate(current_spec)
    ]
    remaining = dict(EXPECTED_COUNTS)
    for _, disposition in current_spec:
        remaining[disposition] -= 1
    number = len(records)
    for disposition, count in remaining.items():
        for _ in range(count):
            records.append(_record("customer", number, disposition))
            number += 1
    value: dict[str, object] = {
        "contract": "hcp-current-overlay-merge-packet/v4",
        "record_count": 522,
        "disposition_counts": EXPECTED_COUNTS,
        "base_source4_digest": "b" * 64,
        "company_id": str(uuid4()),
        "branch_id": str(uuid4()),
        "complete_current_graph_digest": "c" * 64,
        "v3_predecessor_digest": "d" * 64,
        "original_overlay_manifest_digest": "e" * 64,
        "hold_packet_sha256": "f" * 64,
        "update_cohort_authority_digest": "1" * 64,
        "runtime_inventory_sha256": "2" * 64,
        "preview_baseline_sha256": "3" * 64,
        "preview_baseline_semantic_digest": "4" * 64,
        "records": records,
        "current_graph": copy.deepcopy(records[:55]),
    }
    value["digest"] = _canonical_digest(value)
    return value


def _write_packet(path: Path, packet: dict[str, object]) -> None:
    path.write_text(json.dumps(packet, sort_keys=True, separators=(",", ":")) + "\n")
    os.chmod(path, 0o600)


def test_v4_loads_all_522_explicit_successor_assertions(tmp_path: Path) -> None:
    path = tmp_path / "v4.json"
    _write_packet(path, _packet())

    overlay = V4ExecutableOverlay.load(path)

    assert len(overlay.manifest.records) == 522
    assert len(overlay.current_keys) == 55
    assert len(overlay.qualified_targets) == 9
    assert (
        sum(value == "HOLD" for value in overlay.successor_assertions.values()) == 339
    )


@pytest.mark.parametrize("failure", ("contract", "cardinality", "semantic"))
def test_v4_rejects_wrong_version_cardinality_or_digest(
    tmp_path: Path, failure: str
) -> None:
    packet = _packet()
    if failure == "contract":
        packet["contract"] = "hcp-current-overlay-native-execution/v2"
        packet["digest"] = _canonical_digest(packet)
    elif failure == "cardinality":
        packet["record_count"] = 503
        packet["digest"] = _canonical_digest(packet)
    else:
        packet["records"][0]["reason"] = "tampered"  # type: ignore[index]
    path = tmp_path / "v4.json"
    _write_packet(path, packet)
    with pytest.raises(ValueError):
        V4ExecutableOverlay.load(path)


class _Native:
    pass


class _Services:
    def __init__(self, targets: dict[OverlayKey, UUID]) -> None:
        self.targets = targets

    async def qualified_native(self, _session, _domain: str, native_id: UUID):
        return _Native() if native_id in self.targets.values() else None

    async def source_native_id(self, _session, key: OverlayKey):
        return self.targets.get(key)

    async def source_exists(self, _session, _key: OverlayKey) -> bool:
        return False

    async def fingerprint_owners(
        self, _session, _domain: str, _fingerprint: str
    ) -> tuple[str, ...]:
        return ()


@pytest.mark.asyncio
async def test_v4_full_preflight_reports_complete_ready_sweep(tmp_path: Path) -> None:
    path = tmp_path / "v4.json"
    _write_packet(path, _packet())
    overlay = V4ExecutableOverlay.load(path)

    report = await preflight_v4(  # type: ignore[arg-type]
        object(), overlay=overlay, services=_Services(overlay.qualified_targets)
    )

    assert report == {
        "contract": "hcp-current-overlay-v4-preflight/v1",
        "record_count": 522,
        "current_record_count": 55,
        "failure_count": 0,
        "failures": [],
        "ready": True,
    }


@pytest.mark.asyncio
async def test_v4_preflight_aggregates_all_target_failures(tmp_path: Path) -> None:
    path = tmp_path / "v4.json"
    _write_packet(path, _packet())
    overlay = V4ExecutableOverlay.load(path)

    with pytest.raises(ValueError) as error:
        await preflight_v4(  # type: ignore[arg-type]
            object(), overlay=overlay, services=_Services({})
        )

    report = json.loads(str(error.value))
    assert report["failure_count"] == 9
    assert len(report["failures"]) == 9


def test_v3_execution_authority_does_not_accept_v2_contract(tmp_path: Path) -> None:
    value = {
        "contract": "hcp-current-overlay-native-execution/v2",
        "protected_sha": "a" * 40,
        "deployed_sha": "a" * 40,
        "schema_head": "head",
        "expected_database": "preview",
        "company_id": str(uuid4()),
        "branch_id": str(uuid4()),
        "actor_id": str(uuid4()),
        "overlay_path": "/private/overlay",
        "overlay_file_sha256": DIGEST,
        "overlay_semantic_digest": DIGEST,
        "complete_current_graph_digest": DIGEST,
        "source4_package_path": "/private/source4",
        "source4_package_file_sha256": DIGEST,
        "source4_package_digest": DIGEST,
        "v3_predecessor_path": "/private/v3",
        "v3_predecessor_file_sha256": DIGEST,
        "v3_predecessor_digest": DIGEST,
        "original_overlay_path": "/private/v2",
        "original_overlay_file_sha256": DIGEST,
        "original_overlay_digest": DIGEST,
        "hold_packet_path": "/private/holds",
        "hold_packet_digest": DIGEST,
        "update_cohort_path": "/private/cohort",
        "update_cohort_file_sha256": DIGEST,
        "update_cohort_digest": DIGEST,
        "runtime_inventory_path": "/private/runtime",
        "runtime_inventory_digest": DIGEST,
        "preview_baseline_path": "/private/baseline",
        "preview_baseline_sha256": DIGEST,
        "preview_baseline_semantic_digest": DIGEST,
        "backup_path": "/private/backup",
        "backup_digest": DIGEST,
        "restore_receipt_path": "/private/restore",
        "restore_receipt_digest": DIGEST,
        "idempotency_identity": DIGEST,
        "executor_version": EXECUTOR_VERSION,
    }
    path = tmp_path / "authority.json"
    path.write_text(json.dumps(value))
    os.chmod(path, 0o600)

    with pytest.raises(ValueError, match="contract mismatch"):
        V4ExecutionAuthority.load(path)
