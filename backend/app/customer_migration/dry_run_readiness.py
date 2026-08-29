"""Synthetic-only MIG.PREP.2 representative dry-run readiness contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid5

from app.customer_migration.launch_mapping import (
    MAPPING_CONTRACT_VERSION,
    V1_MAPPING_REGISTRY,
    EntityDisposition,
)

DRY_RUN_READINESS_VERSION = "representative-dry-run-readiness/v1"
DRY_RUN_NAMESPACE = UUID("7106214c-4448-5d5e-b0aa-22f0b9888fc2")
INCLUDED_ENTITIES = (
    "customer",
    "contact",
    "service_location",
    "job",
    "appointment",
    "invoice",
    "payment",
)
EXCLUDED_ENTITIES = ("estimate", "note", "attachment")


class DatasetClassification(StrEnum):
    SYNTHETIC = "synthetic"
    SANITIZED_NON_PRODUCTION = "sanitized_non_production"


class ExceptionDomain(StrEnum):
    DATA_MAPPING = "data_mapping"
    APPLICATION_ENVIRONMENT = "application_environment"


class ExceptionCode(StrEnum):
    MISSING_SOURCE_IDENTITY = "missing_source_identity"
    DUPLICATE_SOURCE_IDENTITY = "duplicate_source_identity"
    AMBIGUOUS_IDENTITY = "ambiguous_identity"
    UNRESOLVED_ENTERPRISE_TARGET = "unresolved_enterprise_target"
    MISSING_PARENT = "missing_parent"
    CONFLICTING_PARENT = "conflicting_parent"
    TRANSFORMATION_REJECTION = "transformation_rejection"
    UNSUPPORTED_LIFECYCLE = "unsupported_lifecycle"
    OWNER_DISPOSITION_REQUIRED = "owner_disposition_required"
    COMPANY_MISMATCH = "company_mismatch"
    BRANCH_MISMATCH = "branch_mismatch"
    MONETARY_MISMATCH = "monetary_mismatch"
    EVIDENCE_MISMATCH = "evidence_mismatch"
    UNSUPPORTED_OPTIONAL_FIELD = "unsupported_optional_field"
    EXCLUDED_V1_ENTITY = "excluded_v1_entity"
    REPLAY_CONFLICT = "replay_conflict"
    APPLICATION_INVARIANT_FAILURE = "application_invariant_failure"
    DATABASE_FAILURE = "database_failure"
    TRANSACTION_FAILURE = "transaction_failure"
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"
    UNAVAILABLE_DEPENDENCY = "unavailable_dependency"
    ENVIRONMENT_CONFIGURATION_FAILURE = "environment_configuration_failure"
    INTERRUPTION = "interruption"
    TEARDOWN_FAILURE = "teardown_failure"


DATA_MAPPING_EXCEPTIONS = frozenset(tuple(ExceptionCode)[:16])
APPLICATION_ENVIRONMENT_EXCEPTIONS = frozenset(tuple(ExceptionCode)[16:])


@dataclass(frozen=True)
class ArtifactIdentity:
    artifact_id: UUID
    filename_sha256: str
    content_sha256: str
    byte_size: int


@dataclass(frozen=True)
class EntityInputCount:
    entity: str
    count: int


@dataclass(frozen=True)
class ImmutableInputManifestDraft:
    dataset_identity: UUID
    provider_identity: str
    transformation_contract_versions: tuple[str, ...]
    entity_counts: tuple[EntityInputCount, ...]
    artifacts: tuple[ArtifactIdentity, ...]
    created_at: datetime
    source_provenance: str
    company_id: UUID
    branch_id: UUID
    included_entity_classes: tuple[str, ...]
    excluded_entity_classes: tuple[str, ...]
    classification: DatasetClassification
    sanitization_evidence_sha256: str
    owner_approval_identity: UUID
    owner_approval_evidence_sha256: str
    executing_code_sha: str
    mapping_contract_version: str = MAPPING_CONTRACT_VERSION


@dataclass(frozen=True)
class ImmutableInputManifest:
    manifest_id: UUID
    manifest_digest: str
    draft: ImmutableInputManifestDraft


@dataclass(frozen=True)
class DatasetFieldEvidence:
    entity: str
    populated_fields: tuple[str, ...]


@dataclass(frozen=True)
class MappingConformanceResult:
    conformant: bool
    mapping_contract_version: str
    violations: tuple[str, ...]
    evidence_digest: str


@dataclass(frozen=True)
class ExceptionRecord:
    entity: str
    code: ExceptionCode
    source_evidence_sha256: str

    @property
    def domain(self) -> ExceptionDomain:
        if self.code in DATA_MAPPING_EXCEPTIONS:
            return ExceptionDomain.DATA_MAPPING
        return ExceptionDomain.APPLICATION_ENVIRONMENT


@dataclass(frozen=True)
class EntityReconciliationCount:
    entity: str
    input_count: int
    included_count: int
    accepted_count: int
    rejected_count: int
    excluded_count: int
    unresolved_count: int
    parent_resolved_count: int
    parent_unresolved_count: int
    duplicate_count: int
    ambiguity_count: int
    owner_disposition_count: int


@dataclass(frozen=True)
class MonetaryReconciliation:
    entity: str
    input_amount: Decimal
    accepted_amount: Decimal
    rejected_amount: Decimal
    excluded_amount: Decimal
    unresolved_amount: Decimal


@dataclass(frozen=True)
class TimingEvidence:
    total_elapsed_ns: int
    per_entity_elapsed_ns: tuple[tuple[str, int], ...]
    identity_resolution_ns: int
    transformation_ns: int
    persistence_ns: int
    reconciliation_ns: int
    teardown_ns: int
    processed_records: int
    replay_elapsed_ns: int

    @property
    def records_per_second(self) -> Decimal | None:
        if not self.total_elapsed_ns:
            return None
        return (
            Decimal(self.processed_records)
            * Decimal(1_000_000_000)
            / Decimal(self.total_elapsed_ns)
        )


@dataclass(frozen=True)
class ReconciliationReportDraft:
    manifest_digest: str
    entity_counts: tuple[EntityReconciliationCount, ...]
    monetary_reconciliation: tuple[MonetaryReconciliation, ...]
    exception_ledger: tuple[ExceptionRecord, ...]
    timing: TimingEvidence
    retry_replay_result: str
    teardown_result: str


@dataclass(frozen=True)
class ReconciliationReport:
    evidence_digest: str
    exception_ledger_digest: str
    result_digest: str
    draft: ReconciliationReportDraft


@dataclass(frozen=True)
class RepeatabilityEvidence:
    input_manifest_digest: str
    mapping_contract_version: str
    transformation_contract_versions: tuple[str, ...]
    executing_code_sha: str
    environment_identity: str
    entity_counts_digest: str
    reconciliation_digest: str
    exception_ledger_digest: str
    output_result_digest: str
    timing_evidence_digest: str
    teardown_evidence_digest: str

    @property
    def deterministic_comparison_digest(self) -> str:
        return _digest(
            (
                self.input_manifest_digest,
                self.mapping_contract_version,
                self.transformation_contract_versions,
                self.executing_code_sha,
                self.environment_identity,
                self.entity_counts_digest,
                self.reconciliation_digest,
                self.exception_ledger_digest,
                self.output_result_digest,
                self.teardown_evidence_digest,
            )
        )


@dataclass(frozen=True)
class TeardownStep:
    order: int
    entity: str
    selector: str


@dataclass(frozen=True)
class TeardownPlan:
    run_identity: UUID
    company_id: UUID
    branch_id: UUID
    created_aggregate_identity_contract: str
    ordered_steps: tuple[TeardownStep, ...]
    retained_evidence: tuple[str, ...]
    completion_verification: tuple[str, ...]
    resume_identity: str


@dataclass(frozen=True)
class DryRunExecutionStep:
    order: int
    code: str
    operational: bool


DRY_RUN_EXECUTION_PLAN = tuple(
    DryRunExecutionStep(index, code, code == "representative_non_production_import")
    for index, code in enumerate(
        (
            "dependency_verification",
            "environment_verification",
            "immutable_input_verification",
            "mapping_contract_verification",
            "identity_validation",
            "transformation",
            "parent_resolution",
            "representative_non_production_import",
            "reconciliation",
            "exception_classification",
            "timing_throughput_measurement",
            "result_sealing",
            "teardown",
            "owner_review",
        ),
        start=1,
    )
)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def seal_input_manifest(
    draft: ImmutableInputManifestDraft,
    *,
    expected_company_id: UUID,
    expected_branch_id: UUID,
) -> ImmutableInputManifest:
    """Validate and seal metadata for an already owner-approved non-production input."""
    if draft.mapping_contract_version != MAPPING_CONTRACT_VERSION:
        raise ValueError("mapping contract version is not MIG.1")
    if draft.company_id != expected_company_id:
        raise ValueError("manifest Company scope does not match approved scope")
    if draft.branch_id != expected_branch_id:
        raise ValueError("manifest Branch scope does not match approved scope")
    if draft.included_entity_classes != INCLUDED_ENTITIES:
        raise ValueError("included entity classes do not match MIG.1")
    if draft.excluded_entity_classes != EXCLUDED_ENTITIES:
        raise ValueError("excluded entity classes do not match MIG.1")
    if draft.classification not in DatasetClassification:
        raise ValueError("dataset classification is unsupported")
    if draft.created_at.tzinfo is None or draft.created_at.utcoffset() is None:
        raise ValueError("manifest creation timestamp must be timezone-aware")
    if not draft.provider_identity or not draft.source_provenance:
        raise ValueError("provider identity and source provenance are required")
    if len(draft.executing_code_sha) != 40 or any(
        character not in "0123456789abcdef" for character in draft.executing_code_sha
    ):
        raise ValueError("executing code SHA must be a full Git SHA")
    digest_values = (
        draft.sanitization_evidence_sha256,
        draft.owner_approval_evidence_sha256,
        *(artifact.filename_sha256 for artifact in draft.artifacts),
        *(artifact.content_sha256 for artifact in draft.artifacts),
    )
    if any(not _is_sha256(value) for value in digest_values):
        raise ValueError("manifest evidence contains an invalid SHA-256 digest")
    if any(item.count < 0 for item in draft.entity_counts):
        raise ValueError("entity counts cannot be negative")
    if any(artifact.byte_size < 0 for artifact in draft.artifacts):
        raise ValueError("artifact byte size cannot be negative")
    if len({artifact.artifact_id for artifact in draft.artifacts}) != len(
        draft.artifacts
    ):
        raise ValueError("artifact identities must be unique")
    if tuple(str(artifact.artifact_id) for artifact in draft.artifacts) != tuple(
        sorted(str(artifact.artifact_id) for artifact in draft.artifacts)
    ):
        raise ValueError("artifacts must use canonical identity ordering")
    if len({item.entity for item in draft.entity_counts}) != len(draft.entity_counts):
        raise ValueError("entity counts must be unique")
    if {item.entity for item in draft.entity_counts} != set(INCLUDED_ENTITIES) | set(
        EXCLUDED_ENTITIES
    ):
        raise ValueError("entity counts must cover the complete MIG.1 boundary")
    if tuple(item.entity for item in draft.entity_counts) != tuple(
        sorted(item.entity for item in draft.entity_counts)
    ):
        raise ValueError("entity counts must use canonical ordering")
    transforms = tuple(sorted(set(draft.transformation_contract_versions)))
    if not transforms or transforms != draft.transformation_contract_versions:
        raise ValueError("transformation contract versions must be unique and sorted")
    digest = _digest((DRY_RUN_READINESS_VERSION, asdict(draft)))
    return ImmutableInputManifest(uuid5(DRY_RUN_NAMESPACE, digest), digest, draft)


def validate_mapping_conformance(
    manifest: ImmutableInputManifest,
    field_evidence: tuple[DatasetFieldEvidence, ...],
) -> MappingConformanceResult:
    """Fail closed when future input metadata violates the frozen MIG.1 registry."""
    violations: set[str] = set()
    declared_transforms = set(manifest.draft.transformation_contract_versions)
    by_entity = {item.entity: item for item in field_evidence}
    if len(by_entity) != len(field_evidence):
        violations.add("duplicate_entity_field_evidence")
    for entity in INCLUDED_ENTITIES:
        mapping = V1_MAPPING_REGISTRY.mapping(entity)
        if mapping.disposition is EntityDisposition.EXCLUDED_FROM_V1_BY_OWNER:
            violations.add(f"{entity}:unexpected_exclusion")
        if not set(mapping.transformation_versions) <= declared_transforms:
            violations.add(f"{entity}:missing_transformation_version")
        evidence = by_entity.get(entity)
        if evidence is None:
            violations.add(f"{entity}:missing_field_evidence")
            continue
        fields = set(evidence.populated_fields)
        if len(fields) != len(evidence.populated_fields):
            violations.add(f"{entity}:duplicate_field_evidence")
        unsupported_optional = fields & set(
            mapping.intentionally_unmapped_optional_fields
        )
        if unsupported_optional:
            violations.add(f"{entity}:unsupported_optional_field")
        if set(mapping.required_fields) - fields:
            violations.add(f"{entity}:missing_required_field")
        allowed = set(mapping.required_fields) | set(mapping.optional_fields)
        if fields - allowed:
            violations.add(f"{entity}:unsupported_field")
    for entity in EXCLUDED_ENTITIES:
        mapping = V1_MAPPING_REGISTRY.mapping(entity)
        if mapping.disposition is not EntityDisposition.EXCLUDED_FROM_V1_BY_OWNER:
            violations.add(f"{entity}:owner_exclusion_changed")
        evidence = by_entity.get(entity)
        if evidence and evidence.populated_fields:
            violations.add(f"{entity}:excluded_v1_entity")
    unknown = set(by_entity) - set(INCLUDED_ENTITIES) - set(EXCLUDED_ENTITIES)
    violations.update(f"{entity}:unknown_entity" for entity in unknown)
    ordered = tuple(sorted(violations))
    digest = _digest((manifest.manifest_digest, MAPPING_CONTRACT_VERSION, ordered))
    return MappingConformanceResult(
        not ordered, MAPPING_CONTRACT_VERSION, ordered, digest
    )


def classify_exception(code: ExceptionCode) -> ExceptionDomain:
    if code in DATA_MAPPING_EXCEPTIONS:
        return ExceptionDomain.DATA_MAPPING
    return ExceptionDomain.APPLICATION_ENVIRONMENT


def seal_reconciliation_report(
    draft: ReconciliationReportDraft,
) -> ReconciliationReport:
    if not _is_sha256(draft.manifest_digest):
        raise ValueError("manifest digest is invalid")
    if tuple(item.entity for item in draft.entity_counts) != tuple(
        sorted(item.entity for item in draft.entity_counts)
    ):
        raise ValueError("reconciliation counts must use canonical ordering")
    if len({item.entity for item in draft.entity_counts}) != len(draft.entity_counts):
        raise ValueError("reconciliation entities must be unique")
    for item in draft.entity_counts:
        count_values = (
            item.input_count,
            item.included_count,
            item.accepted_count,
            item.rejected_count,
            item.excluded_count,
            item.unresolved_count,
            item.parent_resolved_count,
            item.parent_unresolved_count,
            item.duplicate_count,
            item.ambiguity_count,
            item.owner_disposition_count,
        )
        if any(value < 0 for value in count_values):
            raise ValueError(f"{item.entity} reconciliation count cannot be negative")
        if item.input_count != item.included_count + item.excluded_count:
            raise ValueError(f"{item.entity} input boundary does not reconcile")
        if item.included_count != (
            item.accepted_count + item.rejected_count + item.unresolved_count
        ):
            raise ValueError(f"{item.entity} disposition totals do not reconcile")
        if (
            item.included_count
            != item.parent_resolved_count + item.parent_unresolved_count
        ):
            raise ValueError(f"{item.entity} parent totals do not reconcile")
        if (
            item.duplicate_count + item.ambiguity_count + item.owner_disposition_count
            > item.unresolved_count
        ):
            raise ValueError(
                f"{item.entity} unresolved categories exceed unresolved total"
            )
    ordered_money = tuple(
        sorted(draft.monetary_reconciliation, key=lambda item: item.entity)
    )
    if len({item.entity for item in ordered_money}) != len(ordered_money):
        raise ValueError("monetary reconciliation entities must be unique")
    for money in ordered_money:
        money_values = (
            money.input_amount,
            money.accepted_amount,
            money.rejected_amount,
            money.excluded_amount,
            money.unresolved_amount,
        )
        if any(not value.is_finite() for value in money_values):
            raise ValueError("monetary evidence must be finite")
        if money.input_amount != sum(money_values[1:], Decimal(0)):
            raise ValueError(f"{money.entity} monetary totals do not reconcile exactly")
    timing_values = (
        draft.timing.total_elapsed_ns,
        draft.timing.identity_resolution_ns,
        draft.timing.transformation_ns,
        draft.timing.persistence_ns,
        draft.timing.reconciliation_ns,
        draft.timing.teardown_ns,
        draft.timing.processed_records,
        draft.timing.replay_elapsed_ns,
        *(value for _, value in draft.timing.per_entity_elapsed_ns),
    )
    if any(value < 0 for value in timing_values):
        raise ValueError("timing evidence cannot be negative")
    ordered_entity_timing = tuple(sorted(draft.timing.per_entity_elapsed_ns))
    if len({entity for entity, _ in ordered_entity_timing}) != len(
        ordered_entity_timing
    ):
        raise ValueError("per-entity timing identities must be unique")
    if any(
        not _is_sha256(item.source_evidence_sha256) for item in draft.exception_ledger
    ):
        raise ValueError("exception evidence digest is invalid")
    ordered_exceptions = tuple(
        sorted(
            draft.exception_ledger,
            key=lambda item: (
                item.entity,
                item.code.value,
                item.source_evidence_sha256,
            ),
        )
    )
    normalized = replace(
        draft,
        monetary_reconciliation=ordered_money,
        exception_ledger=ordered_exceptions,
        timing=replace(draft.timing, per_entity_elapsed_ns=ordered_entity_timing),
    )
    exception_digest = _digest(ordered_exceptions)
    evidence_digest = _digest(
        (
            DRY_RUN_READINESS_VERSION,
            draft.manifest_digest,
            draft.entity_counts,
            ordered_money,
        )
    )
    result_digest = _digest(
        (
            evidence_digest,
            exception_digest,
            draft.retry_replay_result,
            draft.teardown_result,
        )
    )
    return ReconciliationReport(
        evidence_digest, exception_digest, result_digest, normalized
    )


def validate_teardown_plan(plan: TeardownPlan) -> str:
    if not plan.created_aggregate_identity_contract:
        raise ValueError("created aggregate identity contract is required")
    if not plan.ordered_steps or tuple(
        step.order for step in plan.ordered_steps
    ) != tuple(range(1, len(plan.ordered_steps) + 1)):
        raise ValueError("teardown steps must be contiguous and ordered")
    if any("run_identity" not in step.selector for step in plan.ordered_steps):
        raise ValueError("every teardown selector must be bounded by run identity")
    if (
        not plan.retained_evidence
        or not plan.completion_verification
        or not plan.resume_identity
    ):
        raise ValueError(
            "teardown evidence, verification, and resume identity are required"
        )
    return _digest(plan)
