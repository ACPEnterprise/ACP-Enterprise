"""Authority-bound discrepancy quarantine for the November HCP packet.

This derives a private execution packet from the immutable qualified packet.  A
record moved into the discrepancy container is still represented in the
derived packet, but its native assertion is HOLD and its original source
disposition remains in ``source_disposition`` for audit and lineage.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.operational_migration.hcp_migration2_runner import SafeEvidenceError
from app.operational_migration.hcp_november_executor import (
    HOLD_DISPOSITIONS,
    NovemberExecutionPacket,
    PACKET_CONTRACT,
    WRITE_DISPOSITIONS,
    _packet_inventory,
)
from app.operational_migration.hcp_november_supplemental_authority import (
    SupplementalCurrentStateAuthority,
)


CONTRACT = "hcp-november-discrepancy-quarantine-authority/v1"
QUARANTINE_REASON = "estimate_job_lineage_missing"
QUARANTINE_DOMAIN = "estimate"


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fail(code: str, value: object = "") -> None:
    raise SafeEvidenceError(code, _digest(value))


def _private_json(path: Path, code: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        _fail(code, str(path))
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        _fail(f"{code}_permissions", str(path))
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(code, str(error))
    if not isinstance(value, dict):
        _fail(code, value)
    return value


def _packet_payload(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract": PACKET_CONTRACT,
        "qualification_digest": value["qualification_digest"],
        "bundle_sha256": value["bundle_sha256"],
        "policy_digest": value["policy_digest"],
        "reconciliation_digest": value["reconciliation_digest"],
        "company_id": value["company_id"],
        "branch_id": value["branch_id"],
        "actor_id": value["actor_id"],
        "provider_company_id": value["provider_company_id"],
        "schema_head": value["schema_head"],
        "environment": value["environment"],
        "records": value["records"],
        "acquired_at": value["acquired_at"],
    }


def _derive_records(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    derived: list[dict[str, Any]] = []
    quarantined: list[dict[str, str]] = []
    for original in records:
        item = dict(original)
        is_executable_estimate = (
            item.get("domain") == QUARANTINE_DOMAIN
            and str(item.get("disposition", "")).upper() in WRITE_DISPOSITIONS
        )
        has_job_parent = any(
            str(parent.get("domain")) == "job"
            for parent in item.get("parent_keys", [])
        )
        if is_executable_estimate and not has_job_parent:
            original_disposition = str(item["disposition"]).upper()
            # Overlay HOLD assertions are intentionally non-mutating and may
            # not carry a write payload.  Retain the original source body in
            # the private discrepancy evidence envelope instead.
            item["discrepancy_evidence"] = {
                "source_payload": item.get("payload", {}),
                "source_disposition": original_disposition,
                "source_digest": item.get("source_digest"),
            }
            item["payload"] = {}
            item["source_disposition"] = original_disposition
            item["disposition"] = "HOLD"
            item["assertion"] = "hold"
            item["reason"] = QUARANTINE_REASON
            quarantined.append(
                {
                    "domain": QUARANTINE_DOMAIN,
                    "source_id": str(item["source_id"]),
                    "original_disposition": original_disposition,
                    "reason": QUARANTINE_REASON,
                    "source_digest": str(item["source_digest"]),
                }
            )
        derived.append(item)
    return derived, quarantined


@dataclass(frozen=True)
class DiscrepancyQuarantineAuthority:
    authority_path: Path
    packet_path: Path
    packet_sha256: str
    packet_digest: str
    base_authority_path: Path
    base_authority_digest: str
    source_packet_sha256: str
    source_packet_digest: str
    repository_sha: str
    schema_head: str
    target: str
    company_id: str
    branch_id: str
    actor_id: str
    provider_company_id: str
    bundle_sha256: str
    policy_digest: str
    reconciliation_digest: str
    rollback_backup_digest: str
    counts: dict[str, int]
    executable_count: int
    held_count: int
    unexplained_omissions: int
    lineage_gaps: int
    ambiguous_lineage: int
    held_parent_executable_edges: int
    quarantined_records: tuple[dict[str, str], ...]
    authority_digest: str
    packet: NovemberExecutionPacket
    clean_baseline_bootstrap: bool

    @classmethod
    def load(cls, path: Path) -> DiscrepancyQuarantineAuthority:
        value = _private_json(path, "hcp_discrepancy_authority_missing")
        if value.get("contract") != CONTRACT:
            _fail("hcp_discrepancy_authority_contract", value.get("contract"))

        def resolve(key: str) -> Path:
            candidate = Path(str(value[key]))
            return candidate if candidate.is_absolute() else path.parent / candidate

        packet_path = resolve("packet_path")
        packet = NovemberExecutionPacket.load(packet_path)
        authority = cls(
            authority_path=path,
            packet_path=packet_path,
            packet_sha256=str(value["packet_sha256"]),
            packet_digest=str(value["packet_digest"]),
            base_authority_path=resolve("base_authority_path"),
            base_authority_digest=str(value["base_authority_digest"]),
            source_packet_sha256=str(value["source_packet_sha256"]),
            source_packet_digest=str(value["source_packet_digest"]),
            repository_sha=str(value["repository_sha"]),
            schema_head=str(value["schema_head"]),
            target=str(value["target"]),
            company_id=str(value["company_id"]),
            branch_id=str(value["branch_id"]),
            actor_id=str(value["actor_id"]),
            provider_company_id=str(value["provider_company_id"]),
            bundle_sha256=str(value["bundle_sha256"]),
            policy_digest=str(value["policy_digest"]),
            reconciliation_digest=str(value["reconciliation_digest"]),
            rollback_backup_digest=str(value["rollback_backup_digest"]),
            counts={str(k): int(v) for k, v in dict(value["counts"]).items()},
            executable_count=int(value["executable_count"]),
            held_count=int(value["held_count"]),
            unexplained_omissions=int(value["unexplained_omissions"]),
            lineage_gaps=int(value["lineage_gaps"]),
            ambiguous_lineage=int(value["ambiguous_lineage"]),
            held_parent_executable_edges=int(value["held_parent_executable_edges"]),
            quarantined_records=tuple(dict(item) for item in value["quarantined_records"]),
            authority_digest=str(value["authority_digest"]),
            packet=packet,
            clean_baseline_bootstrap=bool(value.get("clean_baseline_bootstrap", True)),
        )
        authority.verify(value)
        return authority

    def _payload(self, value: dict[str, Any]) -> dict[str, Any]:
        return {key: value[key] for key in value if key != "authority_digest"}

    def verify(self, value: dict[str, Any] | None = None) -> None:
        if value is None:
            value = _private_json(self.authority_path, "hcp_discrepancy_authority_missing")
        if self.authority_digest != _digest(self._payload(value)):
            _fail("hcp_discrepancy_authority_digest_mismatch")
        if self.target != "preview" or self.schema_head != "yp8r0t2v4x6z":
            _fail("hcp_discrepancy_runtime_boundary_invalid")
        if len(self.repository_sha) != 40 or any(c not in "0123456789abcdef" for c in self.repository_sha):
            _fail("hcp_discrepancy_repository_sha_invalid")
        if _sha256(self.packet_path) != self.packet_sha256 or self.packet.digest != self.packet_digest:
            _fail("hcp_discrepancy_packet_binding_mismatch")
        base = SupplementalCurrentStateAuthority.load(self.base_authority_path)
        if base.authority_digest != self.base_authority_digest:
            _fail("hcp_discrepancy_base_authority_mismatch")
        for field in ("source_packet_sha256", "source_packet_digest", "bundle_sha256", "policy_digest", "reconciliation_digest", "company_id", "branch_id", "actor_id", "provider_company_id"):
            if getattr(self, field) != getattr(base, "immutable_source_packet_sha256" if field == "source_packet_sha256" else "immutable_source_packet_digest" if field == "source_packet_digest" else field):
                _fail("hcp_discrepancy_base_binding_mismatch", field)
        inventory = _packet_inventory(self.packet.records)
        if self.counts != inventory["counts"] or self.executable_count != inventory["executable"] or self.held_count != inventory["total_held"]:
            _fail("hcp_discrepancy_inventory_mismatch")
        if self.unexplained_omissions or self.lineage_gaps or self.ambiguous_lineage or inventory["held_parent_executable_edges"]:
            _fail("hcp_discrepancy_qualification_gap")
        expected = {item["source_id"] for item in self.quarantined_records}
        actual = {
            str(item["source_id"])
            for item in self.packet.records
            if str(item.get("reason")) == QUARANTINE_REASON
        }
        if expected != actual or any(item.get("domain") != QUARANTINE_DOMAIN for item in self.quarantined_records):
            _fail("hcp_discrepancy_quarantine_inventory_mismatch")
        for item in self.quarantined_records:
            matches = [record for record in self.packet.records if record["source_id"] == item["source_id"]]
            if len(matches) != 1 or matches[0].get("disposition") != "HOLD" or matches[0].get("source_disposition") not in WRITE_DISPOSITIONS:
                _fail("hcp_discrepancy_hold_policy_mismatch", item)
        if any(record.get("disposition") in WRITE_DISPOSITIONS and any(parent.get("source_id") in expected for parent in record.get("parent_keys", [])) for record in self.packet.records):
            _fail("hcp_discrepancy_held_parent_edge")


def build_private_derivation(
    base_authority_path: Path,
    output_dir: Path,
    *,
    repository_sha: str,
) -> Path:
    """Build the deterministic private packet and authority for this policy."""
    base = SupplementalCurrentStateAuthority.load(base_authority_path)
    raw = _private_json(base.packet_path, "hcp_discrepancy_source_packet_missing")
    records, quarantined = _derive_records(list(raw["records"]))
    if not quarantined:
        _fail("hcp_discrepancy_quarantine_empty")
    packet_value = dict(raw)
    packet_value["records"] = records
    packet_value.pop("digest", None)
    packet_value["digest"] = _digest(_packet_payload(packet_value))
    output_dir.mkdir(parents=True, exist_ok=True)
    packet_path = output_dir / "hcp-november-discrepancy-quarantine-packet.json"
    packet_path.write_text(json.dumps(packet_value, sort_keys=True, separators=(",", ":")))
    os.chmod(packet_path, 0o600)
    packet = NovemberExecutionPacket.load(packet_path)
    inventory = _packet_inventory(packet.records)
    authority_value: dict[str, Any] = {
        "contract": CONTRACT,
        "packet_path": str(packet_path),
        "packet_sha256": _sha256(packet_path),
        "packet_digest": packet.digest,
        "base_authority_path": str(base_authority_path),
        "base_authority_digest": base.authority_digest,
        "source_packet_sha256": base.immutable_source_packet_sha256,
        "source_packet_digest": base.immutable_source_packet_digest,
        "repository_sha": repository_sha,
        "schema_head": base.schema_head,
        "target": base.target,
        "company_id": base.company_id,
        "branch_id": base.branch_id,
        "actor_id": base.actor_id,
        "provider_company_id": base.provider_company_id,
        "bundle_sha256": base.bundle_sha256,
        "policy_digest": base.policy_digest,
        "reconciliation_digest": base.reconciliation_digest,
        "rollback_backup_digest": base.rollback_backup_digest,
        "counts": inventory["counts"],
        "executable_count": inventory["executable"],
        "held_count": inventory["total_held"],
        "unexplained_omissions": 0,
        "lineage_gaps": 0,
        "ambiguous_lineage": 0,
        "held_parent_executable_edges": inventory["held_parent_executable_edges"],
        "quarantined_records": quarantined,
        "clean_baseline_bootstrap": True,
    }
    authority_value["authority_digest"] = _digest(authority_value)
    authority_path = output_dir / "authority.json"
    authority_path.write_text(json.dumps(authority_value, sort_keys=True, separators=(",", ":")))
    os.chmod(authority_path, 0o600)
    DiscrepancyQuarantineAuthority.load(authority_path)
    return authority_path
