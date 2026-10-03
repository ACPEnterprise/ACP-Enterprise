"""Whole-HCP historical, metadata, Employee, and retirement closure evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.operational_migration.models import (
    HcpCutoverClosureEvidence,
    HcpMigrationMasterRun,
)
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import MigrationPermission

CONTRACT: Final = "hcp-deep-closure-evidence/v1"
REQUIRED_SOURCE_FAMILIES: Final = frozenset(
    {
        "customers",
        "locations",
        "jobs",
        "appointments",
        "estimates",
        "invoices",
        "payments",
        "refunds",
        "attachments",
        "notes",
        "employees",
        "tags",
        "lead_sources",
        "business_units",
        "job_types",
        "service_references",
    }
)
MetadataState = Literal["HISTORICAL_ONLY", "NATIVE_MAPPED", "CONFLICT", "UNKNOWN"]


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _sha(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


@dataclass(frozen=True, slots=True)
class HistoricalDomainEvidence:
    source_family: str
    source_population: int
    acquired_population: int
    admitted_bound: int
    history_only: int
    held: int
    conflict: int
    unknown: int
    unexplained: int
    as_of: datetime
    source_digest: str
    replay_digest: str

    def validate(self) -> None:
        _sha(self.source_digest, "source_digest")
        _sha(self.replay_digest, "replay_digest")
        values = (
            self.source_population,
            self.acquired_population,
            self.admitted_bound,
            self.history_only,
            self.held,
            self.conflict,
            self.unknown,
            self.unexplained,
        )
        if not self.source_family.strip() or any(value < 0 for value in values):
            raise ValueError("historical domain evidence is invalid")
        explained_acquired = (
            self.admitted_bound
            + self.history_only
            + self.held
            + self.conflict
            + self.unknown
        )
        if self.acquired_population != explained_acquired:
            raise ValueError("acquired population is not fully classified")
        if self.source_population != self.acquired_population + self.unexplained:
            raise ValueError("source population has an unexplained cardinality drift")


@dataclass(frozen=True, slots=True)
class MetadataEvidence:
    kind: str
    source_parent_family: str
    source_parent_id: str
    provider_id: str | None
    source_label: str
    state: MetadataState
    native_reference: str | None
    source_digest: str

    def validate(self) -> None:
        _sha(self.source_digest, "metadata source_digest")
        if (
            not all(
                value.strip()
                for value in (
                    self.kind,
                    self.source_parent_family,
                    self.source_parent_id,
                )
            )
            or not self.source_label.strip()
        ):
            raise ValueError("metadata identity and label are required")
        if self.state == "NATIVE_MAPPED" and not self.native_reference:
            raise ValueError("native metadata mapping requires exact authority")
        if self.state != "NATIVE_MAPPED" and self.native_reference is not None:
            raise ValueError("historical metadata cannot imply a native mapping")


@dataclass(frozen=True, slots=True)
class EmployeeSourceEvidence:
    provider_employee_id: str
    source_email_digest: str | None
    source_version: int
    source_status: Literal["active", "terminated", "historical", "unknown"]
    user_id: UUID | None
    membership_id: UUID | None
    employee_id: UUID | None
    branch_id: UUID | None
    owner_certification: str | None
    duplicate_state: Literal["NONE", "CONFLICT", "UNKNOWN"]
    source_digest: str

    def validate(self) -> None:
        if not self.provider_employee_id.startswith("pro_") or self.source_version < 1:
            raise ValueError("exact versioned HCP Employee identity is required")
        _sha(self.source_digest, "Employee source_digest")
        if self.source_email_digest is not None:
            _sha(self.source_email_digest, "Employee source_email_digest")
        if self.source_status == "terminated" and any(
            value is not None for value in (self.user_id, self.membership_id)
        ):
            raise ValueError("terminated historical Employee cannot imply login access")


@dataclass(frozen=True, slots=True)
class CutoverReceipt:
    source_cutoff: datetime
    provider_source_digest: str
    per_domain_counts: dict[str, dict[str, int]]
    create_count: int
    update_count: int
    replay_count: int
    conflict_count: int
    quarantines: tuple[str, ...]
    unresolved: tuple[str, ...]
    owner_decisions: tuple[str, ...]
    external_gaps: tuple[str, ...]
    final_replay_result: Literal["IDENTICAL", "DRIFT", "NOT_RUN"]
    unexplained_gap_count: int
    retirement_state: Literal["BLOCKED", "RETIREMENT_READY"]
    digest: str

    def verify(self) -> None:
        payload = asdict(self)
        observed = payload.pop("digest")
        _sha(self.provider_source_digest, "provider_source_digest")
        if observed != _digest(payload):
            raise ValueError("cutover receipt digest mismatch")
        blockers = bool(
            self.unexplained_gap_count
            or self.conflict_count
            or self.quarantines
            or self.unresolved
            or self.owner_decisions
            or self.external_gaps
            or self.final_replay_result != "IDENTICAL"
        )
        if (self.retirement_state == "RETIREMENT_READY") == blockers:
            raise ValueError("retirement state contradicts cutover evidence")


@dataclass(frozen=True, slots=True)
class DeepClosurePacket:
    contract: str
    as_of: datetime
    source_digest: str
    domains: tuple[HistoricalDomainEvidence, ...]
    metadata: tuple[MetadataEvidence, ...]
    employees: tuple[EmployeeSourceEvidence, ...]
    receipt: CutoverReceipt
    replay_digest: str

    def verify(self) -> None:
        if self.contract != CONTRACT:
            raise ValueError("unsupported HCP closure contract")
        _sha(self.source_digest, "source_digest")
        _sha(self.replay_digest, "replay_digest")
        families = {item.source_family for item in self.domains}
        if len(families) != len(self.domains):
            raise ValueError("duplicate source family")
        if families != REQUIRED_SOURCE_FAMILIES:
            raise ValueError("whole-HCP source family coverage is incomplete")
        for domain in self.domains:
            domain.validate()
            if domain.as_of > self.as_of:
                raise ValueError("domain evidence is newer than manifest as-of")
        for metadata_item in self.metadata:
            metadata_item.validate()
        for employee in self.employees:
            employee.validate()
        self.receipt.verify()
        payload = asdict(self)
        observed = payload.pop("replay_digest")
        if observed != _digest(payload):
            raise ValueError("HCP closure replay digest mismatch")


def build_packet(
    *,
    as_of: datetime,
    source_digest: str,
    domains: tuple[HistoricalDomainEvidence, ...],
    metadata: tuple[MetadataEvidence, ...],
    employees: tuple[EmployeeSourceEvidence, ...],
    source_cutoff: datetime,
    create_count: int,
    update_count: int,
    replay_count: int,
    quarantines: tuple[str, ...] = (),
    unresolved: tuple[str, ...] = (),
    owner_decisions: tuple[str, ...] = (),
    external_gaps: tuple[str, ...] = (),
    final_replay_result: Literal["IDENTICAL", "DRIFT", "NOT_RUN"] = "NOT_RUN",
) -> DeepClosurePacket:
    for item in domains:
        item.validate()
    unexplained = sum(item.unexplained for item in domains)
    conflicts = (
        sum(item.conflict for item in domains)
        + sum(item.state == "CONFLICT" for item in metadata)
        + sum(item.duplicate_state == "CONFLICT" for item in employees)
    )
    per_domain = {
        item.source_family: {
            "source_population": item.source_population,
            "acquired_population": item.acquired_population,
            "admitted_bound": item.admitted_bound,
            "history_only": item.history_only,
            "held": item.held,
            "conflict": item.conflict,
            "unknown": item.unknown,
            "unexplained": item.unexplained,
        }
        for item in sorted(domains, key=lambda value: value.source_family)
    }
    blocked = bool(
        unexplained
        or conflicts
        or quarantines
        or unresolved
        or owner_decisions
        or external_gaps
        or final_replay_result != "IDENTICAL"
    )
    receipt_payload: dict[str, object] = {
        "source_cutoff": source_cutoff,
        "provider_source_digest": source_digest,
        "per_domain_counts": per_domain,
        "create_count": create_count,
        "update_count": update_count,
        "replay_count": replay_count,
        "conflict_count": conflicts,
        "quarantines": tuple(sorted(set(quarantines))),
        "unresolved": tuple(sorted(set(unresolved))),
        "owner_decisions": tuple(sorted(set(owner_decisions))),
        "external_gaps": tuple(sorted(set(external_gaps))),
        "final_replay_result": final_replay_result,
        "unexplained_gap_count": unexplained,
        "retirement_state": "BLOCKED" if blocked else "RETIREMENT_READY",
    }
    receipt = CutoverReceipt(**receipt_payload, digest=_digest(receipt_payload))  # type: ignore[arg-type]
    packet_payload: dict[str, object] = {
        "contract": CONTRACT,
        "as_of": as_of,
        "source_digest": source_digest,
        "domains": [asdict(item) for item in domains],
        "metadata": [asdict(item) for item in metadata],
        "employees": [asdict(item) for item in employees],
        "receipt": asdict(receipt),
    }
    packet = DeepClosurePacket(
        contract=CONTRACT,
        as_of=as_of,
        source_digest=source_digest,
        domains=domains,
        metadata=metadata,
        employees=employees,
        receipt=receipt,
        replay_digest=_digest(packet_payload),
    )
    packet.verify()
    return packet


def metadata_from_source(source_root: Path) -> tuple[MetadataEvidence, ...]:
    """Extract provider metadata without manufacturing native mappings."""
    evidence: dict[tuple[str, str, str, str], MetadataEvidence] = {}
    for family in ("customers", "jobs", "estimates", "invoices"):
        for path in sorted((source_root / "raw" / family).glob("page-*.json")):
            for row in json.loads(path.read_bytes())[family]:
                parent_id = str(row["id"])
                row_digest = _digest(row)

                def preserve(
                    kind: str,
                    raw: Any,
                    source_family: str,
                    source_parent_id: str,
                    source_digest: str,
                ) -> None:
                    if raw in (None, "", []):
                        return
                    values = raw if isinstance(raw, list) else [raw]
                    for value in values:
                        if isinstance(value, dict):
                            provider_id = value.get("id")
                            label = (
                                value.get("name") or value.get("label") or provider_id
                            )
                        else:
                            provider_id, label = None, value
                        if label in (None, ""):
                            continue
                        item = MetadataEvidence(
                            kind=kind,
                            source_parent_family=source_family,
                            source_parent_id=source_parent_id,
                            provider_id=str(provider_id) if provider_id else None,
                            source_label=str(label),
                            state="HISTORICAL_ONLY",
                            native_reference=None,
                            source_digest=source_digest,
                        )
                        item.validate()
                        evidence[
                            (
                                kind,
                                source_family,
                                source_parent_id,
                                str(provider_id or label),
                            )
                        ] = item

                preserve("tag", row.get("tags"), family, parent_id, row_digest)
                preserve(
                    "lead_source", row.get("lead_source"), family, parent_id, row_digest
                )
                fields = row.get("job_fields") or row.get("estimate_fields") or {}
                if isinstance(fields, dict):
                    preserve(
                        "business_unit",
                        fields.get("business_unit"),
                        family,
                        parent_id,
                        row_digest,
                    )
                    preserve(
                        "job_type",
                        fields.get("job_type"),
                        family,
                        parent_id,
                        row_digest,
                    )
                preserve(
                    "service_reference", row.get("items"), family, parent_id, row_digest
                )
                preserve(
                    "pricebook_reference",
                    row.get("options"),
                    family,
                    parent_id,
                    row_digest,
                )
    return tuple(evidence[key] for key in sorted(evidence))


async def persist_packet(
    session: AsyncSession,
    *,
    context: AuthorizationContext,
    master_run_id: UUID,
    packet: DeepClosurePacket,
) -> HcpCutoverClosureEvidence:
    packet.verify()
    if not context.has_permission(MigrationPermission.EXECUTE_REHEARSAL):
        raise ValueError("Migration execution authority is required")
    if context.active_branch is None:
        raise ValueError("active Branch authority is required")
    master = await session.scalar(
        select(HcpMigrationMasterRun).where(
            HcpMigrationMasterRun.id == master_run_id,
            HcpMigrationMasterRun.company_id == context.company.id,
            HcpMigrationMasterRun.branch_id == context.active_branch.id,
            HcpMigrationMasterRun.package_digest == packet.source_digest,
        )
    )
    if master is None:
        raise ValueError("matching HCP master authority is required")
    existing = await session.scalar(
        select(HcpCutoverClosureEvidence).where(
            HcpCutoverClosureEvidence.company_id == context.company.id,
            HcpCutoverClosureEvidence.master_run_id == master_run_id,
            HcpCutoverClosureEvidence.replay_digest == packet.replay_digest,
        )
    )
    if existing is not None:
        return existing
    record = HcpCutoverClosureEvidence(
        company_id=context.company.id,
        branch_id=context.active_branch.id,
        master_run_id=master_run_id,
        source_cutoff=packet.receipt.source_cutoff,
        as_of=packet.as_of,
        provider_source_digest=packet.source_digest,
        packet=json.loads(json.dumps(asdict(packet), default=str)),
        unexplained_gap_count=packet.receipt.unexplained_gap_count,
        replay_digest=packet.replay_digest,
        status=packet.receipt.retirement_state,
    )
    session.add(record)
    await session.flush()
    return record
