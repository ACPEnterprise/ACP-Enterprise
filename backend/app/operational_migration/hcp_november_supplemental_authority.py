"""Fail-closed authority validation for approved current-state overlays.

The immutable November packet remains the source classification authority.  A
supplemental authority may change only the payload evidence for explicitly
approved current records and may quarantine explicitly named unresolved
records.  This module does not contact HCP and does not write application data.
"""

from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.operational_migration.hcp_migration2_runner import SafeEvidenceError
from app.operational_migration.hcp_november_executor import (
    NovemberExecutionPacket,
    _packet_inventory,
)


CONTRACT = "hcp-november-supplemental-current-state-authority/v1"
EXPECTED_ENVIRONMENT = "preview"
EXPECTED_SCHEMA = "yp8r0t2v4x6z"
EXPECTED_COMPANY_ID = "3ddf07ce-0f44-4b67-a40f-fb0ec41bb7cd"
EXPECTED_BRANCH_ID = "887f413a-70dc-4ab1-98aa-8e84f4e7efd0"
EXPECTED_ACTOR_ID = "c427ebd1-7583-4c0d-9c54-55a0c1214174"
EXPECTED_PROVIDER_COMPANY_ID = "aba4de03-d1b7-4c4e-8fb6-32a3fca713f5"
EXPECTED_SOURCE_PACKET_SHA256 = "8d2b9c056f5eeaaf5b0eb96431c9ccd9906a6db89094bc677ef8a115136fd8a4"
EXPECTED_SOURCE_PACKET_DIGEST = "dfa44599b3bfaf604f16a3117d5925eff8ec6fc25f5e0a35a0e4e64a3459bdb3"
EXPECTED_DERIVED_PACKET_SHA256 = "81c0caba12e6e37f9ae55c956a3870007ed1ffc9df0a697461ef229b64cfce3b"
EXPECTED_DERIVED_PACKET_DIGEST = "dfd5d30c02a3e97ef5bce5aa0f9dd223bd50689a00f27dc00cae7505ce14db20"
EXPECTED_SUPPLEMENTAL_MANIFEST_DIGEST = "94bb2277b77510432369d8752c74ef3fe1dcf77056f5d51ac91854079f155d70"
EXPECTED_QUALIFIED_AUTHORITY_DIGEST = "c3aba6e3316bbce9b626c6fef5d6df6ba867db016d0dad1e4730307050dec809"
APPROVED_CURRENT_ESTIMATE_IDS = frozenset(
    {
        "csr_1128117a7bee4730a6c3938d84d7efad",
        "csr_af1cd1abcb59420791bea9d661a94365",
    }
)
QUARANTINED_CURRENT_IDS = frozenset(
    {
        "csr_363f6876ab984a849a786d21afa1cbb4",
        "csr_8576605fc85545c48ccaec88b976da94",
        "invoice_938feeeb5730456b8a73ba5f3877aab2",
    }
)
EXPECTED_COUNTS = {
    "CREATE": 511,
    "UPDATE": 823,
    "REPLAY": 3854,
    "HOLD": 2082,
    "HOLD_QUARANTINE": 23,
}


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


def _private_file(path: Path, code: str) -> bytes:
    if not path.is_file() or path.is_symlink():
        _fail(code, str(path))
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        _fail(f"{code}_permissions", str(path))
    try:
        return path.read_bytes()
    except OSError as error:
        _fail(code, str(error))
    raise AssertionError("unreachable")


def _required(value: dict[str, Any], key: str) -> Any:
    if key not in value:
        _fail("hcp_november_supplemental_authority_field_missing", key)
    return value[key]


@dataclass(frozen=True)
class SupplementalCurrentStateAuthority:
    authority_path: Path
    packet_path: Path
    packet_sha256: str
    packet_digest: str
    supplemental_manifest_path: Path
    supplemental_manifest_digest: str
    qualified_authority_digest: str
    immutable_source_packet_sha256: str
    immutable_source_packet_digest: str
    original_derived_packet_sha256: str
    original_derived_packet_digest: str
    bundle_sha256: str
    policy_digest: str
    reconciliation_digest: str
    company_id: str
    branch_id: str
    actor_id: str
    provider_company_id: str
    repository_sha: str
    schema_head: str
    target: str
    approved_current_source_ids: frozenset[str]
    quarantined_source_ids: frozenset[str]
    counts: dict[str, int]
    executable_count: int
    held_count: int
    unexplained_omissions: int
    lineage_gaps: int
    held_parent_executable_edges: int
    rollback_backup_digest: str
    authority_digest: str
    packet: NovemberExecutionPacket

    @classmethod
    def load(cls, path: Path) -> SupplementalCurrentStateAuthority:
        raw = _private_file(path, "hcp_november_supplemental_authority_missing")
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            _fail("hcp_november_supplemental_authority_invalid", str(error))
        if not isinstance(value, dict) or value.get("contract") != CONTRACT:
            _fail("hcp_november_supplemental_authority_contract", value)

        def resolve(name: str) -> Path:
            candidate = Path(str(_required(value, name)))
            return candidate if candidate.is_absolute() else path.parent / candidate

        fields = {
            "authority_path": path,
            "packet_path": resolve("packet_path"),
            "packet_sha256": str(_required(value, "packet_sha256")),
            "packet_digest": str(_required(value, "packet_digest")),
            "supplemental_manifest_path": resolve("supplemental_manifest_path"),
            "supplemental_manifest_digest": str(_required(value, "supplemental_manifest_digest")),
            "qualified_authority_digest": str(_required(value, "qualified_authority_digest")),
            "immutable_source_packet_sha256": str(_required(value, "immutable_source_packet_sha256")),
            "immutable_source_packet_digest": str(_required(value, "immutable_source_packet_digest")),
            "original_derived_packet_sha256": str(_required(value, "original_derived_packet_sha256")),
            "original_derived_packet_digest": str(_required(value, "original_derived_packet_digest")),
            "bundle_sha256": str(_required(value, "bundle_sha256")),
            "policy_digest": str(_required(value, "policy_digest")),
            "reconciliation_digest": str(_required(value, "reconciliation_digest")),
            "company_id": str(_required(value, "company_id")),
            "branch_id": str(_required(value, "branch_id")),
            "actor_id": str(_required(value, "actor_id")),
            "provider_company_id": str(_required(value, "provider_company_id")),
            "repository_sha": str(_required(value, "repository_sha")),
            "schema_head": str(_required(value, "schema_head")),
            "target": str(_required(value, "target")),
            "approved_current_source_ids": frozenset(str(item) for item in _required(value, "approved_current_source_ids")),
            "quarantined_source_ids": frozenset(str(item) for item in _required(value, "quarantined_source_ids")),
            "counts": {str(key): int(item) for key, item in dict(_required(value, "counts")).items()},
            "executable_count": int(_required(value, "executable_count")),
            "held_count": int(_required(value, "held_count")),
            "unexplained_omissions": int(_required(value, "unexplained_omissions")),
            "lineage_gaps": int(_required(value, "lineage_gaps")),
            "held_parent_executable_edges": int(_required(value, "held_parent_executable_edges")),
            "rollback_backup_digest": str(_required(value, "rollback_backup_digest")),
            "authority_digest": str(_required(value, "authority_digest")),
        }
        authority = cls(**fields, packet=NovemberExecutionPacket.load(fields["packet_path"]))
        authority.verify(value)
        return authority

    def _authority_payload(self, value: dict[str, Any]) -> dict[str, Any]:
        return {key: value[key] for key in value if key != "authority_digest"}

    def verify(self, value: dict[str, Any] | None = None) -> None:
        if value is None:
            value = json.loads(self.authority_path.read_bytes())
        if self.authority_digest != _digest(self._authority_payload(value)):
            _fail("hcp_november_supplemental_authority_digest_mismatch", self.authority_digest)
        if (
            self.target != EXPECTED_ENVIRONMENT
            or self.schema_head != EXPECTED_SCHEMA
            or len(self.repository_sha) != 40
            or any(char not in "0123456789abcdef" for char in self.repository_sha)
            or self.company_id != EXPECTED_COMPANY_ID
            or self.branch_id != EXPECTED_BRANCH_ID
            or self.actor_id != EXPECTED_ACTOR_ID
            or self.provider_company_id != EXPECTED_PROVIDER_COMPANY_ID
            or self.immutable_source_packet_sha256 != EXPECTED_SOURCE_PACKET_SHA256
            or self.immutable_source_packet_digest != EXPECTED_SOURCE_PACKET_DIGEST
            or self.original_derived_packet_sha256 != EXPECTED_DERIVED_PACKET_SHA256
            or self.original_derived_packet_digest != EXPECTED_DERIVED_PACKET_DIGEST
            or self.supplemental_manifest_digest != EXPECTED_SUPPLEMENTAL_MANIFEST_DIGEST
            or self.qualified_authority_digest != EXPECTED_QUALIFIED_AUTHORITY_DIGEST
        ):
            _fail("hcp_november_supplemental_runtime_boundary_invalid")
        for digest in (
            self.packet_sha256,
            self.packet_digest,
            self.supplemental_manifest_digest,
            self.immutable_source_packet_sha256,
            self.immutable_source_packet_digest,
            self.original_derived_packet_sha256,
            self.original_derived_packet_digest,
            self.bundle_sha256,
            self.policy_digest,
            self.reconciliation_digest,
            self.rollback_backup_digest,
        ):
            if len(digest) not in (40, 64) or any(char not in "0123456789abcdef" for char in digest):
                _fail("hcp_november_supplemental_digest_invalid", digest)
        if _sha256(self.packet_path) != self.packet_sha256 or self.packet.digest != self.packet_digest:
            _fail("hcp_november_supplemental_packet_binding_mismatch")
        if {
            "bundle_sha256": self.packet.bundle_sha256,
            "policy_digest": self.packet.policy_digest,
            "reconciliation_digest": self.packet.reconciliation_digest,
            "company_id": self.packet.company_id,
            "branch_id": self.packet.branch_id,
            "actor_id": self.packet.actor_id,
            "provider_company_id": self.packet.provider_company_id,
            "schema_head": self.packet.schema_head,
            "environment": self.packet.environment,
        } != {
            "bundle_sha256": self.bundle_sha256,
            "policy_digest": self.policy_digest,
            "reconciliation_digest": self.reconciliation_digest,
            "company_id": self.company_id,
            "branch_id": self.branch_id,
            "actor_id": self.actor_id,
            "provider_company_id": self.provider_company_id,
            "schema_head": self.schema_head,
            "environment": self.target,
        }:
            _fail("hcp_november_supplemental_source_packet_binding_mismatch")
        manifest = json.loads(_private_file(self.supplemental_manifest_path, "hcp_november_supplemental_manifest_missing"))
        if manifest.get("digest") != self.supplemental_manifest_digest:
            _fail("hcp_november_supplemental_manifest_binding_mismatch")
        if self.approved_current_source_ids != APPROVED_CURRENT_ESTIMATE_IDS:
            _fail("hcp_november_supplemental_approved_estimate_set_mismatch", sorted(self.approved_current_source_ids))
        if self.quarantined_source_ids != QUARANTINED_CURRENT_IDS:
            _fail("hcp_november_supplemental_quarantine_set_mismatch", sorted(self.quarantined_source_ids))
        if self.counts != EXPECTED_COUNTS or self.executable_count != 5188 or self.held_count != 2105:
            _fail("hcp_november_supplemental_inventory_mismatch", self.counts)
        if self.unexplained_omissions or self.lineage_gaps or self.held_parent_executable_edges:
            _fail("hcp_november_supplemental_qualification_gap")
        packet = {record["source_id"]: record for record in self.packet.records}
        manifest_records = {record["source_id"]: record for record in manifest.get("records", [])}
        if not self.approved_current_source_ids.issubset(manifest_records) or not self.quarantined_source_ids.issubset(manifest_records):
            _fail("hcp_november_supplemental_manifest_inventory_mismatch")
        for source_id in self.approved_current_source_ids:
            record = packet.get(source_id)
            current = manifest_records[source_id]
            if (
                record is None
                or record.get("domain") != "estimate"
                or record.get("disposition") != "REPLAY"
                or record.get("original_gate_disposition") != "REPLAY"
                or record.get("original_source_digest") != current.get("original_source_digest")
                or record.get("source_digest") != current.get("current_source_digest")
                or record.get("current_state_authority") != "approved-current-operational-estimate"
                or current.get("classification") != "BUSINESS_STATE_CHANGED"
            ):
                _fail("hcp_november_supplemental_approved_record_mismatch", source_id)
        for source_id in self.quarantined_source_ids:
            record = packet.get(source_id)
            current = manifest_records[source_id]
            if (
                record is None
                or record.get("disposition") != "HOLD"
                or record.get("assertion") != "hold"
                or record.get("original_gate_disposition") != "REPLAY"
                or not record.get("current_state_quarantine")
                or current.get("classification") != "BUSINESS_STATE_CHANGED"
            ):
                _fail("hcp_november_supplemental_quarantine_record_mismatch", source_id)
        if _packet_inventory(self.packet.records)["held_parent_executable_edges"] != 0:
            _fail("hcp_november_supplemental_held_parent_edge")

