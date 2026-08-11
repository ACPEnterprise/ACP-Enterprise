import hashlib
import json
from importlib.resources import files
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CapacityIdentity = Literal["OM1", "OM2", "MIG", "ECO", "LAP"]
SchedulerState = Literal[
    "planned",
    "ready",
    "in_progress",
    "waiting_for_owner_review",
    "complete",
    "blocked",
    "reconciliation_required",
]


class SchedulerModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CapacityDefinition(SchedulerModel):
    identity: CapacityIdentity
    display_name: str = Field(min_length=1, max_length=120)


class DependencyEvidence(SchedulerModel):
    milestone_code: str = Field(pattern=r"^[A-Z][A-Z0-9.-]+$")
    state: Literal["complete", "accepted", "verification_required"]
    evidence: str = Field(min_length=1)


class MilestoneDefinition(SchedulerModel):
    milestone_code: str = Field(pattern=r"^[A-Z][A-Z0-9.-]+$")
    title: str = Field(min_length=1, max_length=160)
    workstream: str = Field(min_length=1, max_length=100)
    permanent_capacity_identity: CapacityIdentity
    repository_key: str = Field(min_length=1, max_length=100)
    branch_strategy: str = Field(min_length=1)
    starting_commit_rule: str = Field(min_length=1)
    starting_commit_evidence: dict[str, object]
    implementation_classification: Literal["TYPE_A", "TYPE_B", "TYPE_C"]
    migration_classification: Literal["none", "required", "unknown"]
    shared_contract_classification: Literal["none", "serialized", "unknown"]
    integration_checkpoint: str
    readiness_state: SchedulerState
    dependency_evidence: tuple[DependencyEvidence, ...]
    owner_checkpoint: str = Field(min_length=1)
    completion_evidence: tuple[str, ...] = ()
    legacy_titles: tuple[str, ...] = ()
    superseded_legacy_titles: tuple[str, ...] = ()
    preserve_active_execution: bool = False

    @model_validator(mode="after")
    def validate_legacy_identity(self) -> "MilestoneDefinition":
        if set(self.legacy_titles) & set(self.superseded_legacy_titles):
            raise ValueError("Canonical and superseded legacy titles must be disjoint.")
        if self.title in self.superseded_legacy_titles:
            raise ValueError("The canonical milestone title cannot be superseded.")
        return self


class SchedulerManifest(SchedulerModel):
    schema_version: Literal[1]
    scheduler_version: str = Field(min_length=1, max_length=80)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    authoritative_repository_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_documents: tuple[str, ...] = Field(min_length=1)
    integration_warnings: tuple[str, ...] = ()
    capacities: tuple[CapacityDefinition, ...]
    milestones: tuple[MilestoneDefinition, ...]

    @model_validator(mode="after")
    def validate_identity(self) -> "SchedulerManifest":
        if {item.identity for item in self.capacities} != {
            "OM1",
            "OM2",
            "MIG",
            "ECO",
            "LAP",
        }:
            raise ValueError("The five permanent scheduler capacities are required.")
        codes = [item.milestone_code for item in self.milestones]
        if len(codes) != len(set(codes)):
            raise ValueError("Milestone codes must be unique.")
        superseded_titles = [
            title for item in self.milestones for title in item.superseded_legacy_titles
        ]
        if len(superseded_titles) != len(set(superseded_titles)):
            raise ValueError("Superseded legacy titles must resolve to one milestone.")
        canonical_titles = {
            title for item in self.milestones for title in item.legacy_titles
        }
        overlap = canonical_titles.intersection(superseded_titles)
        if overlap:
            raise ValueError(
                "A superseded legacy title cannot remain canonical for another milestone."
            )
        return self


def manifest_fingerprint(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_scheduler_manifest() -> SchedulerManifest:
    path = files("app.engineering_control.scheduler").joinpath(
        "scheduler-manifest.v1.json"
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    fingerprint = raw.pop("fingerprint", None)
    expected = manifest_fingerprint(raw)
    if fingerprint != expected:
        raise ValueError(
            "Scheduler manifest fingerprint does not match its canonical payload."
        )
    return SchedulerManifest.model_validate({**raw, "fingerprint": fingerprint})
