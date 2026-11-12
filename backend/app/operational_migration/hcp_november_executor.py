"""Bounded execution for a previously qualified November HCP handoff.

The sealed November bundle is a qualification artifact, not an executable
record packet.  Execution therefore requires a second, privately mounted,
immutable packet containing only admissible native-write assertions.  Holds
must be present in that packet as non-mutating assertions and are checked
against the qualified policy inventory before any transaction begins.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app.operational_migration.hcp_current_overlay import (
    CurrentOverlayExecutor,
    CurrentOverlayManifest,
    OverlayAssertion,
    OverlayKey,
    OverlayRecord,
    OverlayExecutionReceipt,
)
from app.operational_migration.hcp_november_bundle import (
    AUTHORITY_CONTRACT,
    NovemberQualificationAuthority,
    qualification_digest,
)
from app.operational_migration.hcp_migration2_runner import SafeEvidenceError


PACKET_CONTRACT = "hcp-november-preview-execution-packet/v1"
ENVELOPE_CONTRACT = "hcp-november-preview-execution-envelope/v1"
EXECUTOR_CONTRACT = "hcp-november-preview-executor/v1"
HOLD_DISPOSITIONS = frozenset({"HOLD", "HOLD_QUARANTINE"})
WRITE_DISPOSITIONS = frozenset({"CREATE", "UPDATE", "REPLAY"})
# The November packet contains executable assertions for these domains.  The
# native service layer remains responsible for refusing any domain it cannot
# safely apply; the packet contract must nevertheless account for every
# qualified executable assertion before execution begins.
EXECUTABLE_DOMAINS = frozenset(
    {"customer", "service_location", "job", "appointment", "estimate", "invoice", "employee"}
)
PACKET_DISPOSITIONS = WRITE_DISPOSITIONS | HOLD_DISPOSITIONS
FINAL_OPERATIONAL_HOLD_POLICY = {
    "locationless_open_jobs": 23,
    "duplicate_risk_appointments": 13,
    "unresolved_technician_identities": 2,
    "unassigned_appointments": 1,
}


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _fail(code: str, value: object = "") -> None:
    raise SafeEvidenceError(code, _digest(value))


def require_execution_authorization(authorized: bool) -> None:
    if not authorized:
        _fail("explicit_execution_authorization_required")


def validate_runtime_boundary(environment: str, production: bool, preview: bool, external_writes: Mapping[str, str] | None = None) -> None:
    if environment != "preview" or production or not preview:
        _fail("preview_runtime_boundary_invalid")
    for name, value in (external_writes or {}).items():
        if value.lower() != "false":
            _fail("hcp_november_external_write_boundary_invalid", name)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _packet_inventory(records: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    counts = Counter(str(item.get("disposition", "")).upper() for item in records)
    if set(counts) - PACKET_DISPOSITIONS:
        _fail("hcp_november_execution_disposition_inventory_invalid", dict(counts))
    held_keys = {
        (str(item["domain"]), str(item["source_id"]))
        for item in records
        if str(item.get("disposition", "")).upper() in HOLD_DISPOSITIONS
    }
    held_parent_edges = sum(
        1
        for item in records
        if str(item.get("disposition", "")).upper() in WRITE_DISPOSITIONS
        for parent in item.get("parent_keys", [])
        if (str(parent["domain"]), str(parent["source_id"])) in held_keys
    )
    return {
        "counts": {
            "CREATE": counts.get("CREATE", 0),
            "UPDATE": counts.get("UPDATE", 0),
            "REPLAY": counts.get("REPLAY", 0),
            "HOLD": counts.get("HOLD", 0),
            "HOLD_QUARANTINE": counts.get("HOLD_QUARANTINE", 0),
        },
        "total": len(records),
        "executable": sum(counts.get(key, 0) for key in WRITE_DISPOSITIONS),
        "total_held": sum(counts.get(key, 0) for key in HOLD_DISPOSITIONS),
        "held_parent_executable_edges": held_parent_edges,
        "held_keys": held_keys,
    }


@dataclass(frozen=True)
class NovemberExecutionPacket:
    qualification_digest: str
    bundle_sha256: str
    policy_digest: str
    reconciliation_digest: str
    company_id: str
    branch_id: str
    actor_id: str
    provider_company_id: str
    repository_sha: str
    schema_head: str
    environment: str
    records: tuple[dict[str, Any], ...]
    digest: str
    overlay_manifest: CurrentOverlayManifest

    @classmethod
    def load(cls, path: Path) -> NovemberExecutionPacket:
        try:
            if not path.is_file() or path.is_symlink():
                _fail("hcp_november_execution_packet_missing", str(path))
            if stat.S_IMODE(path.stat().st_mode) & 0o077:
                _fail("hcp_november_execution_packet_permissions", str(path))
            value = json.loads(path.read_bytes())
            if not isinstance(value, dict) or value.get("contract") != PACKET_CONTRACT:
                _fail("hcp_november_execution_packet_contract", value.get("contract"))
            raw_records = value.get("records")
            if not isinstance(raw_records, list):
                _fail("hcp_november_execution_records_missing", "records")
            records = tuple(dict(item) for item in raw_records)
            overlay_records: list[OverlayRecord] = []
            for item in records:
                disposition = item.get("disposition")
                assertion = item.get("assertion")
                if disposition not in HOLD_DISPOSITIONS | WRITE_DISPOSITIONS:
                    _fail("hcp_november_execution_disposition_invalid", disposition)
                if disposition in HOLD_DISPOSITIONS and assertion != "hold":
                    _fail("hcp_november_execution_hold_mutation", item)
                if disposition in WRITE_DISPOSITIONS:
                    assertion = (
                        str(assertion or "create").lower()
                        if disposition == "REPLAY"
                        else disposition.lower()
                    )
                if assertion not in {"create", "update", "hold"}:
                    _fail("hcp_november_execution_assertion_invalid", assertion)
                parents = tuple(
                    OverlayKey(str(parent["domain"]), str(parent["source_id"]))
                    for parent in item.get("parent_keys", [])
                )
                overlay_records.append(
                    OverlayRecord(
                        domain=str(item["domain"]),
                        source_id=str(item["source_id"]),
                        assertion=OverlayAssertion(assertion),
                        source_digest=str(item["source_digest"]),
                        acquired_at=str(item["acquired_at"]),
                        payload=dict(item.get("payload") or {}),
                        prior_source_digest=item.get("prior_source_digest"),
                        parent_keys=parents,
                        native_fingerprint=item.get("native_fingerprint"),
                        reason=str(item.get("reason", "")),
                    )
                )
            overlay = CurrentOverlayManifest.build(
                base_source4_digest=str(value["bundle_sha256"]),
                delta_digest=str(value["policy_digest"]),
                company_id=str(value["company_id"]),
                branch_id=str(value["branch_id"]),
                acquired_at=str(value["acquired_at"]),
                records=tuple(overlay_records),
            )
            packet = cls(
                qualification_digest=str(value["qualification_digest"]),
                bundle_sha256=str(value["bundle_sha256"]),
                policy_digest=str(value["policy_digest"]),
                reconciliation_digest=str(value["reconciliation_digest"]),
                company_id=str(value["company_id"]),
                branch_id=str(value["branch_id"]),
                actor_id=str(value["actor_id"]),
                provider_company_id=str(value["provider_company_id"]),
                # The source packet is reusable without being regenerated for a
                # repository change.  repository_sha, when present in a legacy
                # packet, is informational; the execution envelope is authoritative.
                repository_sha=str(value.get("repository_sha", "")),
                schema_head=str(value["schema_head"]),
                environment=str(value["environment"]),
                records=records,
                digest=str(value["digest"]),
                overlay_manifest=overlay,
            )
            packet.verify_packet()
            return packet
        except SafeEvidenceError:
            raise
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            _fail("hcp_november_execution_packet_invalid", str(error))
        raise AssertionError("unreachable")

    def verify_packet(self) -> None:
        if self.environment != "preview":
            _fail("hcp_november_execution_environment_invalid", self.environment)
        if self.overlay_manifest.digest != _digest(
            {
                "contract": self.overlay_manifest.contract,
                "source_system": self.overlay_manifest.source_system,
                "base_source4_digest": self.overlay_manifest.base_source4_digest,
                "delta_digest": self.overlay_manifest.delta_digest,
                "company_id": self.overlay_manifest.company_id,
                "branch_id": self.overlay_manifest.branch_id,
                "acquired_at": self.overlay_manifest.acquired_at,
                "records": [asdict(record) for record in self.overlay_manifest.records],
            }
        ):
            _fail("hcp_november_execution_overlay_digest_invalid")
        payload = {
            "contract": PACKET_CONTRACT,
            "qualification_digest": self.qualification_digest,
            "bundle_sha256": self.bundle_sha256,
            "policy_digest": self.policy_digest,
            "reconciliation_digest": self.reconciliation_digest,
            "company_id": self.company_id,
            "branch_id": self.branch_id,
            "actor_id": self.actor_id,
            "provider_company_id": self.provider_company_id,
            "schema_head": self.schema_head,
            "environment": self.environment,
            "records": list(self.records),
            "acquired_at": self.overlay_manifest.acquired_at,
        }
        legacy_payload = dict(payload, repository_sha=self.repository_sha)
        if self.digest not in {_digest(payload), _digest(legacy_payload)}:
            _fail("hcp_november_execution_packet_digest_mismatch", self.digest)
        inventory = _packet_inventory(self.records)
        if len({(str(item.get("domain")), str(item.get("source_id"))) for item in self.records}) != len(self.records):
            _fail("hcp_november_execution_duplicate_source_identity", self.digest)
        for record in self.records:
            if (
                str(record.get("disposition", "")).upper() in WRITE_DISPOSITIONS
                and str(record.get("domain")) not in EXECUTABLE_DOMAINS
            ):
                _fail("hcp_november_execution_executable_domain_unsupported", record.get("domain"))
        if inventory["held_parent_executable_edges"]:
            _fail("hcp_november_execution_held_parent_edge", inventory["held_parent_executable_edges"])

    def verify_against(
        self,
        authority: NovemberQualificationAuthority,
        qualified_packet: dict[str, Any] | None,
    ) -> None:
        self.verify_packet()
        if authority.qualification_status != "PASS" or not authority.qualification_digest:
            _fail("hcp_november_prior_qualification_missing", authority.qualification_status)
        if qualified_packet is not None and authority.qualification_digest != qualification_digest(qualified_packet):
            _fail("hcp_november_qualification_digest_mismatch")
        expected = {
            "bundle_sha256": authority.bundle_sha256,
            "policy_digest": authority.expected_policy_digest,
            "reconciliation_digest": authority.expected_reconciliation_digest,
            "company_id": authority.expected_company_id,
            "branch_id": authority.expected_branch_id,
            "actor_id": authority.expected_actor_id,
            "schema_head": authority.expected_schema_head,
            "environment": authority.expected_environment,
        }
        actual = {
            "bundle_sha256": self.bundle_sha256,
            "policy_digest": self.policy_digest,
            "reconciliation_digest": self.reconciliation_digest,
            "company_id": self.company_id,
            "branch_id": self.branch_id,
            "actor_id": self.actor_id,
            "schema_head": self.schema_head,
            "environment": self.environment,
        }
        if actual != expected:
            _fail("hcp_november_execution_authority_mismatch", {"expected": expected, "actual": actual})
        # Legacy unit fixtures carry the small bundle hold inventory directly.
        # Envelope-bound execution deliberately uses the full packet inventory,
        # not the old 38-record qualification projection.
        if qualified_packet is not None and "hold_source_ids" in qualified_packet:
            qualified_holds = {
                source_id
                for values in qualified_packet.get("hold_source_ids", {}).values()
                for source_id in values
            }
            packet_holds = {
                source_id
                for _domain, source_id in _packet_inventory(self.records)["held_keys"]
            }
            if packet_holds != qualified_holds:
                _fail("hcp_november_execution_hold_inventory_mismatch", {"qualified": sorted(qualified_holds), "packet": sorted(packet_holds)})


@dataclass(frozen=True)
class NovemberExecutionEnvelope:
    """Execution authority around an immutable, reusable source packet."""

    source_packet_path: Path
    source_packet_sha256: str
    source_packet_digest: str
    bundle_sha256: str
    policy_digest: str
    reconciliation_digest: str
    company_id: str
    branch_id: str
    actor_id: str
    provider_company_id: str
    repository_sha: str
    schema_head: str
    environment: str
    packet_counts: dict[str, int]
    total_held: int
    executable_count: int
    unexplained_omissions: int
    lineage_gaps: int
    ambiguous_lineage: int
    held_parent_executable_edges: int
    operational_hold_policy: dict[str, int]
    operational_hold_source_ids: dict[str, tuple[str, ...]]
    authority_digest: str
    packet: NovemberExecutionPacket

    @classmethod
    def load(cls, path: Path) -> NovemberExecutionEnvelope:
        try:
            if not path.is_file() or path.is_symlink():
                _fail("hcp_november_execution_envelope_missing", str(path))
            if stat.S_IMODE(path.stat().st_mode) & 0o077:
                _fail("hcp_november_execution_envelope_permissions", str(path))
            value = json.loads(path.read_bytes())
            if not isinstance(value, dict) or value.get("contract") != ENVELOPE_CONTRACT:
                _fail("hcp_november_execution_envelope_contract", value.get("contract"))
            source_path = Path(str(value["source_packet_path"]))
            if not source_path.is_absolute():
                source_path = path.parent / source_path
            if source_path.is_symlink() or not source_path.is_file():
                _fail("hcp_november_source_packet_missing", str(source_path))
            if stat.S_IMODE(source_path.stat().st_mode) & 0o077:
                _fail("hcp_november_source_packet_permissions", str(source_path))
            source_sha = str(value["source_packet_sha256"])
            if _sha256(source_path) != source_sha:
                _fail("hcp_november_source_packet_sha256_mismatch", str(source_path))
            packet = NovemberExecutionPacket.load(source_path)
            envelope = cls(
                source_packet_path=source_path,
                source_packet_sha256=source_sha,
                source_packet_digest=str(value["source_packet_digest"]),
                bundle_sha256=str(value["bundle_sha256"]),
                policy_digest=str(value["policy_digest"]),
                reconciliation_digest=str(value["reconciliation_digest"]),
                company_id=str(value["company_id"]),
                branch_id=str(value["branch_id"]),
                actor_id=str(value["actor_id"]),
                provider_company_id=str(value["provider_company_id"]),
                repository_sha=str(value["repository_sha"]),
                schema_head=str(value["schema_head"]),
                environment=str(value["environment"]),
                packet_counts={str(key): int(item) for key, item in dict(value["packet_counts"]).items()},
                total_held=int(value["total_held"]),
                executable_count=int(value["executable_count"]),
                unexplained_omissions=int(value["unexplained_omissions"]),
                lineage_gaps=int(value["lineage_gaps"]),
                ambiguous_lineage=int(value["ambiguous_lineage"]),
                held_parent_executable_edges=int(value["held_parent_executable_edges"]),
                operational_hold_policy={str(key): int(item) for key, item in dict(value["operational_hold_policy"]).items()},
                operational_hold_source_ids={
                    str(key): tuple(str(source_id) for source_id in source_ids)
                    for key, source_ids in dict(value["operational_hold_source_ids"]).items()
                },
                authority_digest=str(value["authority_digest"]),
                packet=packet,
            )
            envelope.verify()
            return envelope
        except SafeEvidenceError:
            raise
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            _fail("hcp_november_execution_envelope_invalid", str(error))
        raise AssertionError("unreachable")

    def _authority_payload(self) -> dict[str, Any]:
        return {
            "contract": ENVELOPE_CONTRACT,
            "source_packet_sha256": self.source_packet_sha256,
            "source_packet_digest": self.source_packet_digest,
            "bundle_sha256": self.bundle_sha256,
            "policy_digest": self.policy_digest,
            "reconciliation_digest": self.reconciliation_digest,
            "company_id": self.company_id,
            "branch_id": self.branch_id,
            "actor_id": self.actor_id,
            "provider_company_id": self.provider_company_id,
            "repository_sha": self.repository_sha,
            "schema_head": self.schema_head,
            "environment": self.environment,
            "packet_counts": self.packet_counts,
            "total_held": self.total_held,
            "executable_count": self.executable_count,
            "unexplained_omissions": self.unexplained_omissions,
            "lineage_gaps": self.lineage_gaps,
            "ambiguous_lineage": self.ambiguous_lineage,
            "held_parent_executable_edges": self.held_parent_executable_edges,
            "operational_hold_policy": self.operational_hold_policy,
            "operational_hold_source_ids": self.operational_hold_source_ids,
        }

    def verify(self) -> None:
        if self.environment != "preview":
            _fail("hcp_november_execution_environment_invalid", self.environment)
        if self.packet.digest != self.source_packet_digest:
            _fail("hcp_november_source_packet_digest_mismatch", self.source_packet_digest)
        if self.authority_digest != _digest(self._authority_payload()):
            _fail("hcp_november_execution_authority_digest_mismatch", self.authority_digest)
        inventory = _packet_inventory(self.packet.records)
        if self.packet_counts != inventory["counts"]:
            _fail("hcp_november_execution_packet_counts_mismatch", {"expected": self.packet_counts, "actual": inventory["counts"]})
        for field, inventory_field in (
            ("total_held", "total_held"),
            ("executable_count", "executable"),
            ("held_parent_executable_edges", "held_parent_executable_edges"),
        ):
            if getattr(self, field) != inventory[inventory_field]:
                _fail("hcp_november_execution_packet_inventory_mismatch", field)
        if self.unexplained_omissions or self.lineage_gaps or self.ambiguous_lineage:
            _fail("hcp_november_execution_qualification_gap", self._authority_payload())
        if self.held_parent_executable_edges:
            _fail("hcp_november_execution_held_parent_edge", self.held_parent_executable_edges)
        if self.operational_hold_policy != FINAL_OPERATIONAL_HOLD_POLICY:
            _fail("hcp_november_execution_operational_hold_policy_mismatch", self.operational_hold_policy)
        held_by_key = {
            key: str(item.get("disposition", "")).upper()
            for item in self.packet.records
            for key in ((str(item["domain"]), str(item["source_id"])),)
            if key in inventory["held_keys"]
        }
        expected_domains = {
            "locationless_open_jobs": ("job", "HOLD_QUARANTINE"),
            "duplicate_risk_appointments": ("legacy_appointment", "HOLD"),
            "unresolved_technician_identities": ("technician_reference", "HOLD"),
            "unassigned_appointments": ("appointment", "HOLD"),
        }
        if set(self.operational_hold_source_ids) != set(expected_domains):
            _fail("hcp_november_execution_operational_hold_source_mismatch", self.operational_hold_source_ids)
        classified: set[tuple[str, str]] = set()
        for category, source_ids in self.operational_hold_source_ids.items():
            if category not in expected_domains or len(source_ids) != self.operational_hold_policy.get(category):
                _fail("hcp_november_execution_operational_hold_source_mismatch", category)
            domain, disposition = expected_domains[category]
            for source_id in source_ids:
                key = (domain, source_id)
                if key in classified or held_by_key.get(key) != disposition:
                    _fail("hcp_november_execution_operational_hold_source_mismatch", key)
                classified.add(key)

    def verify_against(self, authority: NovemberQualificationAuthority) -> None:
        self.verify()
        expected = {
            "bundle_sha256": authority.bundle_sha256,
            "policy_digest": authority.expected_policy_digest,
            "reconciliation_digest": authority.expected_reconciliation_digest,
            "company_id": authority.expected_company_id,
            "branch_id": authority.expected_branch_id,
            "actor_id": authority.expected_actor_id,
            "provider_company_id": authority.expected_hcp_provider_company_id,
            "repository_sha": authority.expected_repository_sha,
            "schema_head": authority.expected_schema_head,
            "environment": authority.expected_environment,
        }
        actual = {
            "bundle_sha256": self.bundle_sha256,
            "policy_digest": self.policy_digest,
            "reconciliation_digest": self.reconciliation_digest,
            "company_id": self.company_id,
            "branch_id": self.branch_id,
            "actor_id": self.actor_id,
            "provider_company_id": self.provider_company_id,
            "repository_sha": self.repository_sha,
            "schema_head": self.schema_head,
            "environment": self.environment,
        }
        if actual != expected:
            _fail("hcp_november_execution_authority_mismatch", {"expected": expected, "actual": actual})


class NovemberBoundedExecutor:
    """Execute one qualified packet through the existing atomic overlay boundary."""

    async def execute(
        self,
        repository: Any,
        *,
        authority: NovemberQualificationAuthority,
        packet: NovemberExecutionPacket,
        qualified_packet: dict[str, Any],
        database_identity: str,
        schema_head: str,
        execution_timestamp: str | None = None,
        envelope: NovemberExecutionEnvelope | None = None,
    ) -> OverlayExecutionReceipt:
        if database_identity.split(":", 1)[0] != authority.expected_database:
            _fail("hcp_november_execution_database_mismatch", database_identity)
        if schema_head != authority.expected_schema_head:
            _fail("hcp_november_execution_schema_mismatch", schema_head)
        if not authority.rollback_backup_digest or len(authority.rollback_backup_digest) != 64:
            _fail("hcp_november_execution_backup_authority_missing")
        if envelope is not None:
            envelope.verify_against(authority)
            if envelope.packet is not packet:
                _fail("hcp_november_execution_envelope_packet_mismatch")
            packet.verify_against(authority, None)
        else:
            packet.verify_against(authority, qualified_packet)
        inventory = _packet_inventory(packet.records)
        timestamp = execution_timestamp or datetime.now(timezone.utc).isoformat()

        def receipt_context(receipt: OverlayExecutionReceipt) -> Mapping[str, object]:
            outcomes = Counter(item.outcome for item in receipt.journal)
            return {
                "contract": EXECUTOR_CONTRACT,
                "authority_contract": AUTHORITY_CONTRACT,
                "qualification_digest": authority.qualification_digest,
                "bundle_sha256": authority.bundle_sha256,
                "policy_digest": authority.expected_policy_digest,
                "reconciliation_digest": authority.expected_reconciliation_digest,
                "company_id": authority.expected_company_id,
                "branch_id": authority.expected_branch_id,
                "actor_id": authority.expected_actor_id,
                "repository_sha": authority.expected_repository_sha,
                "schema_head": authority.expected_schema_head,
                "environment": authority.expected_environment,
                "execution_packet_digest": packet.digest,
                "execution_packet_sha256": authority.execution_packet_sha256,
                "database_identity": database_identity,
                "execution_timestamp": timestamp,
                "counts": inventory["counts"],
                "execution_outcomes": {
                    "created": outcomes.get("created", 0),
                    "updated": outcomes.get("updated", 0),
                    "idempotent_replay": outcomes.get("idempotent_replay", 0),
                    "held": outcomes.get("held", 0),
                },
                "packet_record_count": inventory["total"],
                "executable_count": inventory["executable"],
                "total_held": inventory["total_held"],
                "unaccounted_records": inventory["total"] - len(receipt.journal),
                "unexplained_omissions": qualified_packet.get("unexplained_omissions", 0),
                "lineage_gaps": envelope.lineage_gaps if envelope is not None else qualified_packet.get("missing_lineage", 0),
                "ambiguous_lineage": envelope.ambiguous_lineage if envelope is not None else qualified_packet.get("ambiguous_lineage", 0),
                "held_parent_executable_edges": inventory["held_parent_executable_edges"],
                "affected_source_native_ids": [
                    {
                        "domain": item.key.domain,
                        "source_id": item.key.source_id,
                        "native_id": item.native_id,
                        "outcome": item.outcome,
                    }
                    for item in receipt.journal
                ],
            }

        return await CurrentOverlayExecutor().execute(
            repository,
            manifest=packet.overlay_manifest,
            expected_base_source4_digest=authority.bundle_sha256,
            rollback_backup_digest=authority.rollback_backup_digest,
            require_non_mutating_parents=True,
            execution_context=receipt_context,
            executable_domains=EXECUTABLE_DOMAINS,
        )


async def run_november_execution(
    authority: NovemberQualificationAuthority,
    *,
    factory: Any,
) -> dict[str, object]:
    """Run the real local Preview transaction after all authority checks."""
    validate_runtime_boundary(
        os.getenv("TARGET_ENVIRONMENT", ""),
        os.getenv("PRODUCTION_ACCESS_ENABLED", "false").lower() == "true",
        os.getenv("PREVIEW_ACCESS_ENABLED", "false").lower() == "true",
        {
            name: os.getenv(name, "false")
            for name in (
        "HCP_PROVIDER_WRITE_ENABLED",
        "HCP_LIVE_ACCESS_ENABLED",
        "QBO_PRODUCTION_ENABLED",
        "PAYROLL_EXECUTION_ENABLED",
            )
        },
    )
    if authority.execution_packet_path is None or not authority.execution_packet_sha256 or not authority.execution_packet_digest:
        _fail("hcp_november_execution_packet_authority_missing")

    qualified = authority.verify()
    envelope_path = authority.execution_packet_path
    if _sha256(envelope_path) != authority.execution_packet_sha256:
        _fail("hcp_november_execution_packet_sha256_mismatch")
    envelope = NovemberExecutionEnvelope.load(envelope_path)
    if envelope.authority_digest != authority.execution_packet_digest:
        _fail("hcp_november_execution_packet_authority_mismatch")
    envelope.verify_against(authority)
    packet = envelope.packet

    from sqlalchemy import text
    from app.operational_migration.hcp_current_overlay_adapter import (
        SqlAlchemyCurrentOverlayRepository,
    )
    from app.operational_migration.hcp_current_overlay_lineage import (
        CurrentOverlayLineageBinding,
        CurrentOverlayLineageBootstrap,
    )
    from app.operational_migration.hcp_current_overlay_native import (
        HcpCurrentOverlayNativeServices,
    )
    from app.operational_migration.hcp_migration2_command import (
        resolve_rehearsal_context,
    )
    from app.platform.permissions.codes import MigrationPermission
    from app.core.config import settings

    repository_sha = os.getenv("APP_VERSION", "")
    if repository_sha != authority.expected_repository_sha:
        _fail("hcp_november_repository_authority_mismatch", repository_sha)
    if settings.qbo_production_enabled:
        _fail("hcp_november_qbo_production_enabled")

    async with factory() as session:
        context = await resolve_rehearsal_context(session, authority, credentialed=True)
        if (
            context.company.id != authority.company_id
            or context.active_branch is None
            or context.active_branch.id != authority.branch_id
            or context.user.id != authority.actor_id
            or not context.has_permission(MigrationPermission.EXECUTE_REHEARSAL)
        ):
            _fail("hcp_november_execution_scope_invalid")
        schema = tuple((await session.scalars(text("SELECT version_num FROM alembic_version"))).all())
        if schema != (authority.expected_schema_head,):
            _fail("hcp_november_execution_schema_mismatch", schema)
        database_identity = str(
            await session.scalar(
                text("SELECT current_database() || ':' || current_user")
            )
        )
        await session.rollback()
        binding = CurrentOverlayLineageBinding(
            company_id=authority.company_id,
            branch_id=authority.branch_id,
            actor_id=authority.actor_id,
            source4_package_identity="hcp-clean-beta-november",
            base_source4_digest=authority.bundle_sha256,
            overlay_manifest_digest=packet.overlay_manifest.digest,
            overlay_file_digest=authority.execution_packet_sha256,
            hold_digest=authority.expected_policy_digest or "",
            canonical_hold_count=envelope.total_held,
            authority_sha=authority.expected_repository_sha,
            schema_head=authority.expected_schema_head,
        )
        services = HcpCurrentOverlayNativeServices(
            context=context,
            master_run_id=binding.master_run_id,
            customer_run_id=binding.master_run_id,
            operational_run_id=binding.master_run_id,
            package_digest=authority.bundle_sha256,
            base_source_digests={
                record.key: record.prior_source_digest or record.source_digest
                for record in packet.overlay_manifest.records
            },
        )
        bootstrap = CurrentOverlayLineageBootstrap(binding, packet.overlay_manifest)
        repository = SqlAlchemyCurrentOverlayRepository(
            session,
            master_run_id=binding.master_run_id,
            services=services,
            lineage_bootstrap=bootstrap,
            overlay_records=packet.overlay_manifest.records,
            advisory_lock_identity=f"hcp-november:{authority.company_id}:{authority.branch_id}",
            execution_context={
                "execution_packet_digest": packet.digest,
                "execution_packet_sha256": authority.execution_packet_sha256,
            },
        )
        receipt = await NovemberBoundedExecutor().execute(
            repository,
            authority=authority,
            packet=packet,
            qualified_packet=qualified,
            database_identity=database_identity,
            schema_head=schema[0],
            envelope=envelope,
        )
    return {
        "contract": EXECUTOR_CONTRACT,
        "status": "executed",
        "receipt_digest": receipt.digest,
        "receipt": dict(receipt.execution_context),
        "counts": receipt.execution_context.get("counts", {}),
    }
