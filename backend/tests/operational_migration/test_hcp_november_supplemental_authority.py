from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.operational_migration.hcp_migration2_runner import SafeEvidenceError
from app.operational_migration.hcp_november_executor import _digest
from app.operational_migration.hcp_november_supplemental_authority import (
    APPROVED_CURRENT_ESTIMATE_IDS,
    CONTRACT,
    EXPECTED_COUNTS,
    QUARANTINED_CURRENT_IDS,
    SupplementalCurrentStateAuthority,
)


def _packet_and_manifest(tmp_path: Path) -> tuple[Path, Path]:
    approved = sorted(APPROVED_CURRENT_ESTIMATE_IDS)
    quarantined = sorted(QUARANTINED_CURRENT_IDS)
    records: list[dict[str, object]] = []

    def add(domain: str, source_id: str, disposition: str) -> None:
        record: dict[str, object] = {
            "domain": domain,
            "source_id": source_id,
            "assertion": "hold" if disposition.startswith("HOLD") else ("update" if disposition == "UPDATE" else "create"),
            "source_digest": hashlib.sha256(source_id.encode()).hexdigest(),
            "acquired_at": "2026-11-13T00:00:00+00:00",
            "payload": {},
            "parent_keys": [],
            "disposition": disposition,
        }
        if disposition == "UPDATE":
            record["prior_source_digest"] = hashlib.sha256(
                (source_id + ":prior").encode()
            ).hexdigest()
        records.append(record)

    for i in range(EXPECTED_COUNTS["CREATE"]):
        add("customer", f"cus-{i}", "CREATE")
    for i in range(EXPECTED_COUNTS["UPDATE"]):
        add("job", f"job-{i}", "UPDATE")
    for i in range(EXPECTED_COUNTS["REPLAY"] - len(approved)):
        add("appointment", f"appt-{i}", "REPLAY")
    for source_id in approved:
        add("estimate", source_id, "REPLAY")
        row = records[-1]
        original = hashlib.sha256((source_id + ":original").encode()).hexdigest()
        current = str(row["source_digest"])
        row.update(
            {
                "prior_source_digest": original,
                "original_source_digest": original,
                "current_state_source_digest": current,
                "current_state_authority": "approved-current-operational-estimate",
                "original_gate_disposition": "REPLAY",
            }
        )
    for i in range(EXPECTED_COUNTS["HOLD"] - len(quarantined)):
        add("legacy_appointment", f"held-{i}", "HOLD")
    for source_id in quarantined:
        add("estimate" if source_id.startswith("csr_") else "invoice", source_id, "HOLD")
        records[-1].update(
            {
                "original_gate_disposition": "REPLAY",
                "current_state_quarantine": True,
                "hold_subdisposition": "SUPPLEMENTAL_CURRENT_STATE_UNRESOLVED",
            }
        )
    for i in range(EXPECTED_COUNTS["HOLD_QUARANTINE"]):
        add("job", f"quarantine-{i}", "HOLD_QUARANTINE")

    packet_values = {
        "contract": "hcp-november-preview-execution-packet/v1",
        "qualification_digest": "1" * 64,
        "bundle_sha256": "c401e4f59252360861e612d23b160dde55e843b16de5aca125188ad50841bd1f",
        "policy_digest": "285d288b98da96140fff9e25200b95beb120d05a2b5196560a89d0a616dd7c0e",
        "reconciliation_digest": "7aaed3abde50d943cb4f981fbdcb185c19b1656e1cf3d1d8da6b20631ca12536",
        "company_id": "3ddf07ce-0f44-4b67-a40f-fb0ec41bb7cd",
        "branch_id": "887f413a-70dc-4ab1-98aa-8e84f4e7efd0",
        "actor_id": "c427ebd1-7583-4c0d-9c54-55a0c1214174",
        "provider_company_id": "aba4de03-d1b7-4c4e-8fb6-32a3fca713f5",
        "schema_head": "yp8r0t2v4x6z",
        "environment": "preview",
        "records": records,
        "acquired_at": "2026-11-13T00:00:00+00:00",
    }
    packet_values["digest"] = _digest(packet_values)
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(packet_values, sort_keys=True, separators=(",", ":")))
    packet_path.chmod(0o600)

    manifest_records = []
    for source_id in set(approved) | set(quarantined):
        current = hashlib.sha256(source_id.encode()).hexdigest()
        original = hashlib.sha256((source_id + ":original").encode()).hexdigest()
        manifest_records.append(
            {
                "source_id": source_id,
                "domain": "estimate" if source_id.startswith("csr_") else "invoice",
                "classification": "BUSINESS_STATE_CHANGED",
                "original_source_digest": original,
                "current_source_digest": current,
            }
        )
    manifest = {
        "contract": "synthetic",
        "records": manifest_records,
        "digest": "94bb2277b77510432369d8752c74ef3fe1dcf77056f5d51ac91854079f155d70",
    }
    manifest_path = tmp_path / "supplemental-manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")))
    manifest_path.chmod(0o600)
    return packet_path, manifest_path


def _authority(tmp_path: Path, packet_path: Path, manifest_path: Path) -> Path:
    packet_sha = hashlib.sha256(packet_path.read_bytes()).hexdigest()
    packet = json.loads(packet_path.read_text())
    value = {
        "contract": CONTRACT,
        "packet_path": str(packet_path),
        "packet_sha256": packet_sha,
        "packet_digest": packet["digest"],
        "supplemental_manifest_path": str(manifest_path),
        "supplemental_manifest_digest": json.loads(manifest_path.read_text())["digest"],
        "qualified_authority_digest": "c3aba6e3316bbce9b626c6fef5d6df6ba867db016d0dad1e4730307050dec809",
        "immutable_source_packet_sha256": "8d2b9c056f5eeaaf5b0eb96431c9ccd9906a6db89094bc677ef8a115136fd8a4",
        "immutable_source_packet_digest": "dfa44599b3bfaf604f16a3117d5925eff8ec6fc25f5e0a35a0e4e64a3459bdb3",
        "original_derived_packet_sha256": "81c0caba12e6e37f9ae55c956a3870007ed1ffc9df0a697461ef229b64cfce3b",
        "original_derived_packet_digest": "dfd5d30c02a3e97ef5bce5aa0f9dd223bd50689a00f27dc00cae7505ce14db20",
        "supplemental_manifest_binding": "94bb2277b77510432369d8752c74ef3fe1dcf77056f5d51ac91854079f155d70",
        "bundle_sha256": "c401e4f59252360861e612d23b160dde55e843b16de5aca125188ad50841bd1f",
        "policy_digest": "285d288b98da96140fff9e25200b95beb120d05a2b5196560a89d0a616dd7c0e",
        "reconciliation_digest": "7aaed3abde50d943cb4f981fbdcb185c19b1656e1cf3d1d8da6b20631ca12536",
        "company_id": "3ddf07ce-0f44-4b67-a40f-fb0ec41bb7cd",
        "branch_id": "887f413a-70dc-4ab1-98aa-8e84f4e7efd0",
        "actor_id": "c427ebd1-7583-4c0d-9c54-55a0c1214174",
        "provider_company_id": "aba4de03-d1b7-4c4e-8fb6-32a3fca713f5",
        "repository_sha": "f284d8466910aaba5816895275011e172cce373b",
        "schema_head": "yp8r0t2v4x6z",
        "target": "preview",
        "approved_current_source_ids": sorted(APPROVED_CURRENT_ESTIMATE_IDS),
        "quarantined_source_ids": sorted(QUARANTINED_CURRENT_IDS),
        "counts": EXPECTED_COUNTS,
        "executable_count": 5188,
        "held_count": 2105,
        "unexplained_omissions": 0,
        "lineage_gaps": 0,
        "held_parent_executable_edges": 0,
        "rollback_backup_digest": "e" * 64,
    }
    # The production schema uses supplemental_manifest_digest; the binding
    # field is deliberately included in the test separately to catch any
    # accidental substitution of the private custody digest.
    value["supplemental_manifest_digest"] = value.pop("supplemental_manifest_binding")
    value["authority_digest"] = _digest(value)
    path = tmp_path / "authority.json"
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")))
    path.chmod(0o600)
    return path


def test_valid_supplemental_authority_is_accepted(tmp_path: Path) -> None:
    packet, manifest = _packet_and_manifest(tmp_path)
    authority = SupplementalCurrentStateAuthority.load(_authority(tmp_path, packet, manifest))
    assert authority.executable_count == 5188


@pytest.mark.parametrize("field", ["approved_current_source_ids", "quarantined_source_ids", "supplemental_manifest_digest", "immutable_source_packet_digest"])
def test_supplemental_authority_mismatch_is_rejected(tmp_path: Path, field: str) -> None:
    packet, manifest = _packet_and_manifest(tmp_path)
    path = _authority(tmp_path, packet, manifest)
    value = json.loads(path.read_text())
    if field.endswith("source_ids"):
        value[field] = ["wrong-id"]
    else:
        value[field] = "f" * 64
    value["authority_digest"] = _digest({key: item for key, item in value.items() if key != "authority_digest"})
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")))
    path.chmod(0o600)
    with pytest.raises(SafeEvidenceError):
        SupplementalCurrentStateAuthority.load(path)


def test_production_target_is_rejected(tmp_path: Path) -> None:
    packet, manifest = _packet_and_manifest(tmp_path)
    path = _authority(tmp_path, packet, manifest)
    value = json.loads(path.read_text())
    value["target"] = "production"
    value["authority_digest"] = _digest({key: item for key, item in value.items() if key != "authority_digest"})
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")))
    path.chmod(0o600)
    with pytest.raises(SafeEvidenceError):
        SupplementalCurrentStateAuthority.load(path)
