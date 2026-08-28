"""Fail-closed ingestion for planning-only milestone bank artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from importlib.resources import files
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

BankPriority = Literal["P0", "P1", "P2", "P3"]
BankReadiness = Literal[
    "READY",
    "BLOCKED_DEPENDENCY",
    "BLOCKED_OWNER_DECISION",
    "BLOCKED_FINANCE_DECISION",
    "BLOCKED_EXTERNAL",
    "DEFERRED",
]
BankOwnership = Literal["UNOWNED", "ACTIVE_OWNED", "RESERVED_FUTURE"]
MigrationRisk = Literal["LOW", "MEDIUM", "HIGH"]

MILESTONE_ID_PATTERN = re.compile(r"^BANK\.[A-Z0-9]+\.[0-9]{3}$")
COLLISION_DOMAIN_PATTERN = re.compile(r"^[a-z0-9_]+$")
PRIORITY_ORDER: dict[BankPriority, int] = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


class MilestoneBankIngestionError(ValueError):
    """The planning artifact is not safe to ingest."""


class BankModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MilestoneBankRecord(BankModel):
    milestone_id: str = Field(pattern=r"^BANK\.[A-Z0-9]+\.[0-9]{3}$")
    name: str = Field(min_length=3)
    domain: str = Field(min_length=2)
    objective: str = Field(min_length=20)
    priority: BankPriority
    readiness_state: BankReadiness
    ownership_state: BankOwnership
    dependencies: tuple[str, ...]
    repository_evidence: tuple[str, ...] = Field(min_length=1)
    dependency_type: Literal["HARD_ALL"]
    readiness_conditions: tuple[str, ...] = Field(min_length=1)
    implementation_boundary: str = Field(min_length=20)
    excluded_scope: tuple[str, ...] = Field(min_length=1)
    likely_repository_areas: tuple[str, ...] = Field(min_length=1)
    collision_domain: str = Field(pattern=r"^[a-z0-9_]+$")
    owner_decision_required: bool
    finance_decision_required: bool
    external_gate: str = Field(min_length=1)
    schema_migration_risk: MigrationRisk
    production_risk: Literal["PROHIBITED_UNTIL_SEPARATE_AUTHORIZATION"]
    validation_contract: tuple[str, ...] = Field(min_length=1)
    completion_evidence: tuple[str, ...] = Field(min_length=1)
    successor_ids: tuple[str, ...]

    @model_validator(mode="after")
    def validate_readiness_and_ownership(self) -> MilestoneBankRecord:
        if len(self.dependencies) != len(set(self.dependencies)):
            raise ValueError("dependencies must be unique")
        if len(self.successor_ids) != len(set(self.successor_ids)):
            raise ValueError("successor_ids must be unique")
        if self.readiness_state == "READY":
            if self.dependencies:
                raise ValueError("READY milestone has unresolved dependencies")
            if self.ownership_state != "UNOWNED":
                raise ValueError("READY milestone cannot be actively owned or reserved")
            if (
                self.owner_decision_required
                or self.finance_decision_required
                or self.external_gate != "none"
            ):
                raise ValueError("READY milestone has an unresolved gate")
        if (
            self.readiness_state == "BLOCKED_DEPENDENCY"
            and not self.dependencies
        ):
            raise ValueError("dependency-blocked milestone has no dependency")
        if self.ownership_state == "ACTIVE_OWNED":
            if not self.owner_decision_required:
                raise ValueError("active ownership lacks an owner release gate")
            if self.readiness_state == "READY":
                raise ValueError("active ownership contradicts READY")
        if (
            self.readiness_state == "BLOCKED_OWNER_DECISION"
            and not self.owner_decision_required
        ):
            raise ValueError("owner-blocked milestone has no owner gate")
        if (
            self.readiness_state == "BLOCKED_FINANCE_DECISION"
            and not self.finance_decision_required
        ):
            raise ValueError("Finance-blocked milestone has no Finance gate")
        if (
            self.readiness_state == "BLOCKED_EXTERNAL"
            and self.external_gate == "none"
        ):
            raise ValueError("externally blocked milestone has no external gate")
        return self


class MilestoneBank(BankModel):
    schema_version: Literal["2.0"]
    bank_id: Literal["BANK.2"]
    purpose: str = Field(min_length=1)
    authoritative_start_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    generated_on: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    activation_semantics: Literal["NONE_PLANNING_ONLY"]
    canonical_runtime_manifest: str = Field(min_length=1)
    integration_rule: str = Field(min_length=1)
    active_ownership: dict[str, str]
    milestones: tuple[MilestoneBankRecord, ...] = Field(
        min_length=200, max_length=300
    )
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class PlanningMilestoneProjection(BankModel):
    milestone_id: str
    name: str
    domain: str
    priority: BankPriority
    readiness_state: BankReadiness
    blocked_reasons: tuple[str, ...]
    collision_domain: str
    ownership_state: BankOwnership
    owner_decision_required: bool
    finance_decision_required: bool
    external_gate: str
    schema_migration_risk: MigrationRisk
    production_risk: Literal["PROHIBITED_UNTIL_SEPARATE_AUTHORIZATION"]


class MilestoneBankProjection(BankModel):
    bank_id: Literal["BANK.2"]
    bank_fingerprint: str
    authoritative_start_sha: str
    milestones: tuple[PlanningMilestoneProjection, ...]

    @property
    def ready_milestone_ids(self) -> tuple[str, ...]:
        return tuple(
            item.milestone_id
            for item in self.milestones
            if item.readiness_state == "READY"
        )


def bank_fingerprint(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def ingest_milestone_bank(raw: Mapping[str, object]) -> MilestoneBank:
    """Validate one bank artifact without repairing or persisting it."""
    payload = dict(raw)
    fingerprint = payload.pop("fingerprint", None)
    if not isinstance(fingerprint, str) or fingerprint != bank_fingerprint(payload):
        raise MilestoneBankIngestionError("milestone bank fingerprint mismatch")
    try:
        bank = MilestoneBank.model_validate({**payload, "fingerprint": fingerprint})
    except ValidationError as error:
        raise MilestoneBankIngestionError(
            f"milestone bank schema or readiness validation failed: {error}"
        ) from error
    _validate_graph_and_provenance(bank)
    return bank


def load_milestone_bank() -> MilestoneBank:
    """Load the packaged authoritative planning artifact."""
    path = files("app.engineering_control.scheduler").joinpath(
        "milestone-bank.v2.json"
    )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MilestoneBankIngestionError(
            "milestone bank artifact provenance cannot be established"
        ) from error
    if not isinstance(raw, dict):
        raise MilestoneBankIngestionError("milestone bank root must be an object")
    return ingest_milestone_bank(raw)


def project_milestone_bank(bank: MilestoneBank) -> MilestoneBankProjection:
    """Create a deterministic, read-only readiness projection."""
    projections = tuple(
        sorted(
            (_project_record(item) for item in bank.milestones),
            key=lambda item: (PRIORITY_ORDER[item.priority], item.milestone_id),
        )
    )
    return MilestoneBankProjection(
        bank_id=bank.bank_id,
        bank_fingerprint=bank.fingerprint,
        authoritative_start_sha=bank.authoritative_start_sha,
        milestones=projections,
    )


def load_milestone_bank_projection() -> MilestoneBankProjection:
    """Load and project BANK.2 with no scheduler or execution side effect."""
    return project_milestone_bank(load_milestone_bank())


def _validate_graph_and_provenance(bank: MilestoneBank) -> None:
    ids = [item.milestone_id for item in bank.milestones]
    if len(ids) != len(set(ids)):
        raise MilestoneBankIngestionError("duplicate milestone ID")
    names = [item.name.casefold() for item in bank.milestones]
    if len(names) != len(set(names)):
        raise MilestoneBankIngestionError("duplicate milestone name")
    by_id = {item.milestone_id: item for item in bank.milestones}
    expected_evidence = (
        f"origin/customer-management-v1@{bank.authoritative_start_sha}"
    )
    for item in bank.milestones:
        if expected_evidence not in item.repository_evidence:
            raise MilestoneBankIngestionError(
                f"artifact provenance missing for {item.milestone_id}"
            )
        if not MILESTONE_ID_PATTERN.fullmatch(item.milestone_id):
            raise MilestoneBankIngestionError("invalid milestone identity")
        if not COLLISION_DOMAIN_PATTERN.fullmatch(item.collision_domain):
            raise MilestoneBankIngestionError("invalid collision domain")
        for dependency in item.dependencies:
            if dependency not in by_id:
                raise MilestoneBankIngestionError(
                    f"missing dependency {dependency} for {item.milestone_id}"
                )
            if item.milestone_id not in by_id[dependency].successor_ids:
                raise MilestoneBankIngestionError(
                    f"nonreciprocal dependency {dependency} -> {item.milestone_id}"
                )
        for successor in item.successor_ids:
            if successor not in by_id:
                raise MilestoneBankIngestionError(
                    f"missing successor {successor} for {item.milestone_id}"
                )
            if item.milestone_id not in by_id[successor].dependencies:
                raise MilestoneBankIngestionError(
                    f"nonreciprocal successor {item.milestone_id} -> {successor}"
                )
    _reject_cycles(by_id)


def _reject_cycles(by_id: Mapping[str, MilestoneBankRecord]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(milestone_id: str) -> None:
        if milestone_id in visiting:
            raise MilestoneBankIngestionError(
                f"dependency cycle contains {milestone_id}"
            )
        if milestone_id in visited:
            return
        visiting.add(milestone_id)
        for dependency in by_id[milestone_id].dependencies:
            visit(dependency)
        visiting.remove(milestone_id)
        visited.add(milestone_id)

    for milestone_id in sorted(by_id):
        visit(milestone_id)


def _project_record(item: MilestoneBankRecord) -> PlanningMilestoneProjection:
    reasons: list[str] = []
    reasons.extend(f"dependency:{dependency}" for dependency in item.dependencies)
    if item.ownership_state != "UNOWNED":
        reasons.append(f"ownership:{item.ownership_state}")
    if item.owner_decision_required:
        reasons.append("owner_decision_required")
    if item.finance_decision_required:
        reasons.append("finance_decision_required")
    if item.external_gate != "none":
        reasons.append(f"external_gate:{item.external_gate}")
    if item.readiness_state == "DEFERRED":
        reasons.append("deferred")
    return PlanningMilestoneProjection(
        milestone_id=item.milestone_id,
        name=item.name,
        domain=item.domain,
        priority=item.priority,
        readiness_state=item.readiness_state,
        blocked_reasons=tuple(reasons),
        collision_domain=item.collision_domain,
        ownership_state=item.ownership_state,
        owner_decision_required=item.owner_decision_required,
        finance_decision_required=item.finance_decision_required,
        external_gate=item.external_gate,
        schema_migration_risk=item.schema_migration_risk,
        production_risk=item.production_risk,
    )
