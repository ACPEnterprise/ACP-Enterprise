"""Provider-neutral non-Production migration completion and cutover gating."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum

MODULE_CONTRACT_VERSION = "migration-module-cutover-readiness/v1"
_PHASE_ORDER = {
    "preflight": 0,
    "pre_cutover_acquired": 1,
    "reconciled": 2,
    "owner_ready": 3,
    "source_frozen": 4,
    "final_deltas_acquired": 5,
    "go_no_go": 6,
    "activation_eligible": 7,
}


class CapabilityState(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    BLOCKED_EXTERNAL = "blocked_external"
    NOT_REQUIRED = "not_required"
    SUPERSEDED = "superseded"


class MigrationDisposition(StrEnum):
    MIGRATED = "migrated"
    HELD = "held"
    EXCEPTION = "exception"
    NON_APPLICABLE = "non_applicable"
    DEFERRED_WITH_AUTHORITY = "deferred_with_authority"


class CutoverPhase(StrEnum):
    PREFLIGHT = "preflight"
    PRE_CUTOVER_ACQUIRED = "pre_cutover_acquired"
    RECONCILED = "reconciled"
    OWNER_READY = "owner_ready"
    SOURCE_FROZEN = "source_frozen"
    FINAL_DELTAS_ACQUIRED = "final_deltas_acquired"
    GO_NO_GO = "go_no_go"
    ACTIVATION_ELIGIBLE = "activation_eligible"


@dataclass(frozen=True)
class SourceAuthority:
    provider: str
    environment: str
    manifest_digest: str
    transformation_version: str
    acquisition_complete: bool
    immutable_evidence: bool


@dataclass(frozen=True)
class EntityAccounting:
    entity_type: str
    source: int
    migrated: int = 0
    held: int = 0
    exception: int = 0
    non_applicable: int = 0
    deferred_with_authority: int = 0

    @property
    def reconciled(self) -> bool:
        return self.source == (
            self.migrated
            + self.held
            + self.exception
            + self.non_applicable
            + self.deferred_with_authority
        )


@dataclass(frozen=True)
class HistoricalWindow:
    starts_on: str | None
    ends_on: str
    owner_authority_digest: str | None
    opening_evidence_digest: str | None


@dataclass(frozen=True)
class CutoverAuthority:
    company_id: str
    branch_id: str
    target_environment: str
    repository_sha: str
    actor_id: str
    source_authorities: tuple[SourceAuthority, ...]
    entity_accounting: tuple[EntityAccounting, ...]
    historical_window: HistoricalWindow
    required_owner_decisions: tuple[str, ...]
    resolved_owner_decisions: tuple[str, ...]
    phase: CutoverPhase
    source_freeze_evidence_digest: str | None = None
    final_delta_digest: str | None = None


@dataclass(frozen=True)
class ReadinessResult:
    state: str
    ready_for_non_production_rehearsal: bool
    ready_for_production_cutover: bool
    blocker_codes: tuple[str, ...]
    authority_digest: str
    reconciliation_digest: str


def qualify_cutover(authority: CutoverAuthority) -> ReadinessResult:
    blockers: list[str] = []
    if authority.target_environment == "production":
        blockers.append("production_execution_not_authorized")
    if not authority.company_id or not authority.branch_id or not authority.actor_id:
        blockers.append("scope_authority_incomplete")
    if len(authority.repository_sha) != 40:
        blockers.append("repository_authority_invalid")
    providers = [item.provider for item in authority.source_authorities]
    if len(providers) != len(set(providers)):
        blockers.append("duplicate_source_authority")
    for source in authority.source_authorities:
        if source.environment == "production":
            blockers.append(f"{source.provider}_production_source_gate")
        if not source.acquisition_complete:
            blockers.append(f"{source.provider}_acquisition_incomplete")
        if not source.immutable_evidence:
            blockers.append(f"{source.provider}_evidence_not_immutable")
        if not _sha(source.manifest_digest) or not source.transformation_version:
            blockers.append(f"{source.provider}_source_authority_invalid")
    entity_types = [item.entity_type for item in authority.entity_accounting]
    if len(entity_types) != len(set(entity_types)):
        blockers.append("duplicate_entity_accounting")
    for item in authority.entity_accounting:
        if min(
            item.source,
            item.migrated,
            item.held,
            item.exception,
            item.non_applicable,
            item.deferred_with_authority,
        ) < 0:
            blockers.append(f"{item.entity_type}_negative_count")
        elif not item.reconciled:
            blockers.append(f"{item.entity_type}_unexplained_delta")
    unresolved = sorted(
        set(authority.required_owner_decisions)
        - set(authority.resolved_owner_decisions)
    )
    if unresolved:
        blockers.append("owner_policy_decisions_required")
    window = authority.historical_window
    if window.owner_authority_digest is None:
        blockers.append("historical_window_owner_authority_required")
    if window.starts_on is not None and window.opening_evidence_digest is None:
        blockers.append("historical_opening_evidence_required")
    phase_order = _PHASE_ORDER[authority.phase.value]
    if (
        phase_order >= _PHASE_ORDER[CutoverPhase.SOURCE_FROZEN.value]
        and not _sha(authority.source_freeze_evidence_digest)
    ):
        blockers.append("source_freeze_evidence_required")
    if (
        phase_order >= _PHASE_ORDER[CutoverPhase.FINAL_DELTAS_ACQUIRED.value]
        and not _sha(authority.final_delta_digest)
    ):
        blockers.append("final_delta_evidence_required")
    canonical = {
        "contract_version": MODULE_CONTRACT_VERSION,
        "authority": authority,
    }
    authority_digest = _digest(canonical)
    reconciliation_digest = _digest(
        tuple(sorted((item.entity_type, item.reconciled) for item in authority.entity_accounting))
    )
    non_production_blockers = tuple(
        item
        for item in sorted(set(blockers))
        if item not in {"owner_policy_decisions_required"}
        and not item.endswith("_production_source_gate")
    )
    ready_non_production = not non_production_blockers
    ready_production = not blockers and authority.phase is CutoverPhase.ACTIVATION_ELIGIBLE
    return ReadinessResult(
        state="READY" if ready_non_production else "BLOCKED",
        ready_for_non_production_rehearsal=ready_non_production,
        ready_for_production_cutover=ready_production,
        blocker_codes=tuple(sorted(set(blockers))),
        authority_digest=authority_digest,
        reconciliation_digest=reconciliation_digest,
    )


def _sha(value: str | None) -> bool:
    return bool(
        value
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
