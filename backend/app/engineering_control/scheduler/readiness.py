"""Deterministic, read-only reconciliation of BANK.2 against current authority."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from importlib.resources import files
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .bank import (
    PRIORITY_ORDER,
    BankModel,
    BankPriority,
    MilestoneBank,
    MilestoneBankRecord,
    load_milestone_bank,
)

CurrentReadiness = Literal[
    "PLANNED_READY",
    "ACTIVE_OWNED",
    "COMPLETE",
    "EXECUTABLE",
    "BLOCKED_DEPENDENCY",
    "BLOCKED_OWNER_DECISION",
    "BLOCKED_FINANCE_DECISION",
    "BLOCKED_EXTERNAL",
    "BLOCKED_COLLISION",
    "STALE_BANK_STATE",
    "INVALID_AUTHORITY",
]
GateKind = Literal["OWNER", "FINANCE", "EXTERNAL"]


class ReadinessEvaluationError(ValueError):
    """Current authority cannot be reconciled safely."""


class AuthorityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CompletionEvidence(AuthorityModel):
    bank_milestone_id: str = Field(pattern=r"^BANK\.[A-Z0-9]+\.[0-9]{3}$")
    canonical_milestone_id: str = Field(min_length=2)
    evidence_kind: Literal[
        "OWNER_ACCEPTED_EXTERNAL_ADOPTION",
        "AUTHORITATIVE_INTEGRATION_ACCEPTANCE",
    ]
    authoritative_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    evidence_reference: str = Field(min_length=8)


class GateResolution(AuthorityModel):
    bank_milestone_id: str = Field(pattern=r"^BANK\.[A-Z0-9]+\.[0-9]{3}$")
    gate_kind: GateKind
    gate_name: str = Field(min_length=1)
    evidence_reference: str = Field(min_length=8)


class OwnershipEvidence(AuthorityModel):
    bank_milestone_id: str = Field(pattern=r"^BANK\.[A-Z0-9]+\.[0-9]{3}$")
    owner_reference: str = Field(min_length=3)
    collision_domain: str = Field(pattern=r"^[a-z0-9_]+$")


class IdentityReconciliationRequirement(AuthorityModel):
    bank_milestone_id: str = Field(pattern=r"^BANK\.[A-Z0-9]+\.[0-9]{3}$")
    candidate_canonical_ids: tuple[str, ...] = Field(min_length=2)
    reason: str = Field(min_length=8)

    @model_validator(mode="after")
    def candidates_are_distinct(self) -> IdentityReconciliationRequirement:
        if len(self.candidate_canonical_ids) != len(set(self.candidate_canonical_ids)):
            raise ValueError("identity reconciliation candidates must be unique")
        return self


class MilestoneAuthoritySnapshot(AuthorityModel):
    schema_version: Literal["1.0"]
    authority_id: Literal["BANK.DF.002.AUTHORITY"]
    bank_id: Literal["BANK.2"]
    bank_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    authoritative_repository_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    repository_ref: Literal["origin/customer-management-v1"]
    completion_inventory_scope: Literal["ALL_BANK_MILESTONES"]
    completion_evidence: tuple[CompletionEvidence, ...]
    identity_reconciliation_required: tuple[IdentityReconciliationRequirement, ...]
    gate_resolutions: tuple[GateResolution, ...]
    active_ownership: tuple[OwnershipEvidence, ...]
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def reject_contradictions(self) -> MilestoneAuthoritySnapshot:
        completed = [item.bank_milestone_id for item in self.completion_evidence]
        if len(completed) != len(set(completed)):
            raise ValueError("completion identity mapping is ambiguous")
        owned = [item.bank_milestone_id for item in self.active_ownership]
        if len(owned) != len(set(owned)):
            raise ValueError("ownership evidence conflicts")
        overlap = set(completed) & set(owned)
        if overlap:
            raise ValueError(
                f"completed milestones cannot be active: {sorted(overlap)}"
            )
        ambiguous = [
            item.bank_milestone_id for item in self.identity_reconciliation_required
        ]
        if len(ambiguous) != len(set(ambiguous)):
            raise ValueError("identity reconciliation requirements conflict")
        mapped_ambiguous = set(completed) & set(ambiguous)
        if mapped_ambiguous:
            raise ValueError(
                f"completed identity remains ambiguous: {sorted(mapped_ambiguous)}"
            )
        gates = [
            (item.bank_milestone_id, item.gate_kind, item.gate_name)
            for item in self.gate_resolutions
        ]
        if len(gates) != len(set(gates)):
            raise ValueError("gate resolution evidence conflicts")
        return self


class CurrentMilestoneProjection(BankModel):
    milestone_id: str
    canonical_milestone_id: str | None
    name: str
    domain: str
    priority: BankPriority
    bank_readiness_state: str
    planning_state: Literal["PLANNED_READY", "PLANNED_BLOCKED"]
    current_state: CurrentReadiness
    blocked_reasons: tuple[str, ...]
    collision_domain: str
    owner_decision_required: bool
    finance_decision_required: bool
    external_gate: str
    completion_commit_sha: str | None


class CurrentReadinessProjection(BankModel):
    bank_id: Literal["BANK.2"]
    bank_fingerprint: str
    authority_fingerprint: str
    authoritative_repository_sha: str
    milestones: tuple[CurrentMilestoneProjection, ...]
    fingerprint: str

    def count_by_state(self) -> dict[str, int]:
        return dict(
            sorted(Counter(item.current_state for item in self.milestones).items())
        )

    @property
    def executable_milestone_ids(self) -> tuple[str, ...]:
        return tuple(
            item.milestone_id
            for item in self.milestones
            if item.current_state == "EXECUTABLE"
        )

    @property
    def ambiguous_identity_mappings(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                item.milestone_id
                for item in self.milestones
                if item.current_state == "INVALID_AUTHORITY"
            )
        )


def authority_fingerprint(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def ingest_authority_snapshot(
    raw: Mapping[str, object], bank: MilestoneBank
) -> MilestoneAuthoritySnapshot:
    payload = dict(raw)
    fingerprint = payload.pop("fingerprint", None)
    if not isinstance(fingerprint, str) or fingerprint != authority_fingerprint(
        payload
    ):
        raise ReadinessEvaluationError("authority snapshot fingerprint mismatch")
    try:
        authority = MilestoneAuthoritySnapshot.model_validate(
            {**payload, "fingerprint": fingerprint}
        )
    except ValidationError as error:
        raise ReadinessEvaluationError(
            f"invalid authority snapshot: {error}"
        ) from error
    if authority.bank_fingerprint != bank.fingerprint:
        raise ReadinessEvaluationError("authority snapshot does not cover this bank")
    bank_ids = {item.milestone_id for item in bank.milestones}
    referenced_ids = {
        *(item.bank_milestone_id for item in authority.completion_evidence),
        *(
            item.bank_milestone_id
            for item in authority.identity_reconciliation_required
        ),
        *(item.bank_milestone_id for item in authority.gate_resolutions),
        *(item.bank_milestone_id for item in authority.active_ownership),
    }
    unknown = referenced_ids - bank_ids
    if unknown:
        raise ReadinessEvaluationError(
            f"authority references unknown milestones: {sorted(unknown)}"
        )
    by_id = {item.milestone_id: item for item in bank.milestones}
    for item in authority.active_ownership:
        if item.collision_domain != by_id[item.bank_milestone_id].collision_domain:
            raise ReadinessEvaluationError(
                f"ownership collision domain contradicts bank for {item.bank_milestone_id}"
            )
    return authority


def load_authority_snapshot(bank: MilestoneBank) -> MilestoneAuthoritySnapshot:
    path = files("app.engineering_control.scheduler").joinpath(
        "milestone-authority.v1.json"
    )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReadinessEvaluationError(
            "authority provenance cannot be established"
        ) from error
    if not isinstance(raw, dict):
        raise ReadinessEvaluationError("authority snapshot root must be an object")
    return ingest_authority_snapshot(raw, bank)


def evaluate_readiness(
    bank: MilestoneBank, authority: MilestoneAuthoritySnapshot
) -> CurrentReadinessProjection:
    if authority.bank_fingerprint != bank.fingerprint:
        raise ReadinessEvaluationError("bank provenance is invalid")
    records = {item.milestone_id: item for item in bank.milestones}
    completions = {
        item.bank_milestone_id: item for item in authority.completion_evidence
    }
    ownership = {item.bank_milestone_id: item for item in authority.active_ownership}
    ambiguous = {
        item.bank_milestone_id: item
        for item in authority.identity_reconciliation_required
    }
    resolved_gates = {
        (item.bank_milestone_id, item.gate_kind, item.gate_name)
        for item in authority.gate_resolutions
    }
    active_domains = {item.collision_domain for item in authority.active_ownership}
    projected: dict[str, CurrentMilestoneProjection] = {}
    for milestone_id in _topological_ids(records):
        item = records[milestone_id]
        projected[milestone_id] = _evaluate_record(
            item,
            projected,
            completions,
            ambiguous,
            ownership,
            resolved_gates,
            active_domains,
        )
    milestones = tuple(
        sorted(
            projected.values(),
            key=lambda item: (PRIORITY_ORDER[item.priority], item.milestone_id),
        )
    )
    body = {
        "bank_id": bank.bank_id,
        "bank_fingerprint": bank.fingerprint,
        "authority_fingerprint": authority.fingerprint,
        "authoritative_repository_sha": authority.authoritative_repository_sha,
        "milestones": [item.model_dump(mode="json") for item in milestones],
    }
    return CurrentReadinessProjection(
        bank_id=bank.bank_id,
        bank_fingerprint=bank.fingerprint,
        authority_fingerprint=authority.fingerprint,
        authoritative_repository_sha=authority.authoritative_repository_sha,
        milestones=milestones,
        fingerprint=authority_fingerprint(body),
    )


def load_current_readiness_projection() -> CurrentReadinessProjection:
    bank = load_milestone_bank()
    return evaluate_readiness(bank, load_authority_snapshot(bank))


def _evaluate_record(
    item: MilestoneBankRecord,
    prior: Mapping[str, CurrentMilestoneProjection],
    completions: Mapping[str, CompletionEvidence],
    ambiguous: Mapping[str, IdentityReconciliationRequirement],
    ownership: Mapping[str, OwnershipEvidence],
    resolved_gates: set[tuple[str, GateKind, str]],
    active_domains: set[str],
) -> CurrentMilestoneProjection:
    completion = completions.get(item.milestone_id)
    canonical_id = completion.canonical_milestone_id if completion else None
    reasons: list[str] = []
    if item.milestone_id in ambiguous:
        state: CurrentReadiness = "INVALID_AUTHORITY"
        candidates = ",".join(ambiguous[item.milestone_id].candidate_canonical_ids)
        reasons.append(f"ambiguous_identity_mapping:{candidates}")
    elif completion:
        state = "COMPLETE"
        if item.readiness_state == "READY":
            reasons.append("bank_ready_but_authoritatively_complete")
    elif item.milestone_id in ownership:
        state = "ACTIVE_OWNED"
        reasons.append("active_ownership")
    else:
        unresolved = [
            dependency
            for dependency in item.dependencies
            if prior[dependency].current_state != "COMPLETE"
        ]
        owner_open = (
            item.owner_decision_required
            and (
                item.milestone_id,
                "OWNER",
                "owner_decision_required",
            )
            not in resolved_gates
        )
        finance_open = (
            item.finance_decision_required
            and (
                item.milestone_id,
                "FINANCE",
                "finance_decision_required",
            )
            not in resolved_gates
        )
        external_open = (
            item.external_gate != "none"
            and (
                item.milestone_id,
                "EXTERNAL",
                item.external_gate,
            )
            not in resolved_gates
        )
        if unresolved:
            state = "BLOCKED_DEPENDENCY"
            reasons.extend(f"dependency_not_complete:{value}" for value in unresolved)
        elif finance_open and item.readiness_state == "BLOCKED_FINANCE_DECISION":
            state = "BLOCKED_FINANCE_DECISION"
            reasons.append("finance_decision_required")
        elif external_open and item.readiness_state == "BLOCKED_EXTERNAL":
            state = "BLOCKED_EXTERNAL"
            reasons.append(f"external_gate:{item.external_gate}")
        elif owner_open:
            state = "BLOCKED_OWNER_DECISION"
            reasons.append("owner_decision_required")
        elif finance_open:
            state = "BLOCKED_FINANCE_DECISION"
            reasons.append("finance_decision_required")
        elif external_open:
            state = "BLOCKED_EXTERNAL"
            reasons.append(f"external_gate:{item.external_gate}")
        elif item.collision_domain in active_domains:
            state = "BLOCKED_COLLISION"
            reasons.append(f"active_collision_domain:{item.collision_domain}")
        elif item.readiness_state == "DEFERRED":
            state = "STALE_BANK_STATE"
            reasons.append("deferred_requires_authoritative_release")
        else:
            state = "EXECUTABLE"
            if item.readiness_state != "READY":
                reasons.append(f"bank_state_advanced_from:{item.readiness_state}")
    return CurrentMilestoneProjection(
        milestone_id=item.milestone_id,
        canonical_milestone_id=canonical_id,
        name=item.name,
        domain=item.domain,
        priority=item.priority,
        bank_readiness_state=item.readiness_state,
        planning_state=(
            "PLANNED_READY" if item.readiness_state == "READY" else "PLANNED_BLOCKED"
        ),
        current_state=state,
        blocked_reasons=tuple(reasons),
        collision_domain=item.collision_domain,
        owner_decision_required=item.owner_decision_required,
        finance_decision_required=item.finance_decision_required,
        external_gate=item.external_gate,
        completion_commit_sha=(
            completion.authoritative_commit_sha if completion else None
        ),
    )


def _topological_ids(records: Mapping[str, MilestoneBankRecord]) -> tuple[str, ...]:
    result: list[str] = []
    visited: set[str] = set()

    def visit(milestone_id: str) -> None:
        if milestone_id in visited:
            return
        for dependency in sorted(records[milestone_id].dependencies):
            visit(dependency)
        visited.add(milestone_id)
        result.append(milestone_id)

    for milestone_id in sorted(records):
        visit(milestone_id)
    return tuple(result)


__all__ = [
    "CurrentReadinessProjection",
    "MilestoneAuthoritySnapshot",
    "ReadinessEvaluationError",
    "authority_fingerprint",
    "evaluate_readiness",
    "ingest_authority_snapshot",
    "load_authority_snapshot",
    "load_current_readiness_projection",
]
