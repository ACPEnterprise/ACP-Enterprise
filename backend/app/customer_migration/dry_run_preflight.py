"""MIG.PREP.3 deterministic closure for a future MIG.2 operation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid5

from app.customer_migration.dry_run_readiness import (
    DRY_RUN_NAMESPACE,
    EXCLUDED_ENTITIES,
    INCLUDED_ENTITIES,
    ImmutableInputManifest,
    MappingConformanceResult,
    TeardownPlan,
    validate_teardown_plan,
)

DRY_RUN_PREFLIGHT_VERSION = "representative-dry-run-preflight/v1"
REQUIRED_EXTERNAL_GATES = (
    "mig_1_complete",
    "ic_2_complete",
    "rpt_3_complete",
    "immutable_input_approved",
    "type_c_operation_approved",
)
REQUIRED_AUDIT_EVENTS = (
    "preflight_started",
    "dependencies_verified",
    "environment_verified",
    "input_verified",
    "mapping_verified",
    "identity_verified",
    "teardown_verified",
    "preflight_sealed",
)
REQUIRED_RESUME_CHECKPOINTS = (
    "immutable_input_verified",
    "mapping_verified",
    "identity_validated",
    "transformation_completed",
    "parent_resolution_completed",
    "import_transaction_completed",
    "reconciliation_sealed",
    "teardown_completed",
)


class GateStatus(StrEnum):
    COMPLETE = "complete"
    MISSING = "missing"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ExternalGateEvidence:
    code: str
    status: GateStatus
    evidence_sha256: str | None


@dataclass(frozen=True)
class VerifiedArtifact:
    artifact_id: UUID
    observed_content_sha256: str
    observed_byte_size: int


@dataclass(frozen=True)
class DryRunEnvironmentContract:
    environment_identity: str
    classification: str
    company_id: UUID
    branch_id: UUID
    database_identity_sha256: str
    configuration_digest: str
    isolated_network: bool
    preview_access_enabled: bool
    production_access_enabled: bool
    persistent_after_teardown: bool


@dataclass(frozen=True)
class SourceIdentityPreflightCount:
    entity: str
    input_count: int
    valid_count: int
    missing_count: int
    duplicate_count: int
    ambiguous_count: int
    conflicting_count: int
    unresolved_target_count: int
    owner_disposition_required_count: int


@dataclass(frozen=True)
class OwnerDispositionPreflight:
    required_count: int
    resolved_count: int
    unresolved_count: int
    evidence_digests: tuple[str, ...]


@dataclass(frozen=True)
class ResumeRetryContract:
    run_identity: UUID
    manifest_digest: str
    idempotency_identity: str
    ordered_checkpoints: tuple[str, ...]
    last_verified_checkpoint: str | None
    retry_requires_same_manifest: bool
    retry_requires_same_code_sha: bool
    replay_zero_delta_required: bool


@dataclass(frozen=True)
class AuditTrailContract:
    run_identity: UUID
    actor_identity: UUID
    ordered_event_codes: tuple[str, ...]
    evidence_digests: tuple[str, ...]
    append_only: bool


@dataclass(frozen=True)
class DryRunPreflightInput:
    expected_company_id: UUID
    expected_branch_id: UUID
    expected_code_sha: str
    expected_alembic_head: str
    observed_alembic_heads: tuple[str, ...]
    manifest: ImmutableInputManifest | None
    verified_artifacts: tuple[VerifiedArtifact, ...]
    mapping_conformance: MappingConformanceResult | None
    environment: DryRunEnvironmentContract | None
    identity_counts: tuple[SourceIdentityPreflightCount, ...]
    owner_dispositions: OwnerDispositionPreflight | None
    teardown_plan: TeardownPlan | None
    resume_retry: ResumeRetryContract | None
    audit_trail: AuditTrailContract | None
    external_gates: tuple[ExternalGateEvidence, ...]


@dataclass(frozen=True)
class DryRunPreflightAssessment:
    assessment_id: UUID
    assessment_digest: str
    status: str
    technically_executable: bool
    authorized_to_execute: bool
    completed_gates: tuple[str, ...]
    blockers: tuple[str, ...]
    manifest_digest: str | None
    environment_identity: str | None


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _is_sha256(value: str | None) -> bool:
    return (
        value is not None
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _valid_git_sha(value: str) -> bool:
    return len(value) == 40 and all(
        character in "0123456789abcdef" for character in value
    )


def assess_dry_run_preflight(
    evidence: DryRunPreflightInput,
) -> DryRunPreflightAssessment:
    """Assess evidence only; this function has no import or persistence capability."""
    blockers: set[str] = set()
    completed: set[str] = set()
    if not _valid_git_sha(evidence.expected_code_sha):
        blockers.add("code:invalid_expected_sha")
    if evidence.observed_alembic_heads != (evidence.expected_alembic_head,):
        blockers.add("schema:alembic_head_mismatch")
    else:
        completed.add("alembic_single_head")

    gates = {gate.code: gate for gate in evidence.external_gates}
    if len(gates) != len(evidence.external_gates):
        blockers.add("gate:duplicate_evidence")
    for code in REQUIRED_EXTERNAL_GATES:
        gate = gates.get(code)
        if gate is None:
            blockers.add(f"gate:{code}:missing")
        elif gate.status is not GateStatus.COMPLETE:
            blockers.add(f"gate:{code}:{gate.status.value}")
        elif not _is_sha256(gate.evidence_sha256):
            blockers.add(f"gate:{code}:invalid_evidence")
        else:
            completed.add(code)
    blockers.update(
        f"gate:{code}:unsupported" for code in set(gates) - set(REQUIRED_EXTERNAL_GATES)
    )

    manifest = evidence.manifest
    if manifest is None:
        blockers.add("input:immutable_manifest_missing")
    else:
        if manifest.draft.company_id != evidence.expected_company_id:
            blockers.add("input:company_scope_mismatch")
        if manifest.draft.branch_id != evidence.expected_branch_id:
            blockers.add("input:branch_scope_mismatch")
        if manifest.draft.executing_code_sha != evidence.expected_code_sha:
            blockers.add("input:executing_code_sha_mismatch")
        expected_artifacts = {
            item.artifact_id: item for item in manifest.draft.artifacts
        }
        observed_artifacts = {
            item.artifact_id: item for item in evidence.verified_artifacts
        }
        if len(observed_artifacts) != len(evidence.verified_artifacts):
            blockers.add("input:duplicate_artifact_verification")
        if set(expected_artifacts) != set(observed_artifacts):
            blockers.add("input:artifact_boundary_mismatch")
        for artifact_id, expected in expected_artifacts.items():
            observed = observed_artifacts.get(artifact_id)
            if observed and (
                observed.observed_content_sha256 != expected.content_sha256
                or observed.observed_byte_size != expected.byte_size
            ):
                blockers.add(f"input:artifact_mismatch:{artifact_id}")
        if not any(item.startswith("input:") for item in blockers):
            completed.add("immutable_input_verified")

    mapping = evidence.mapping_conformance
    if mapping is None:
        blockers.add("mapping:conformance_missing")
    elif not mapping.conformant:
        blockers.update(f"mapping:{item}" for item in mapping.violations)
    else:
        completed.add("mapping_conformance_verified")

    environment = evidence.environment
    if environment is None:
        blockers.add("environment:contract_missing")
    else:
        if environment.classification not in {"synthetic", "sanitized_non_production"}:
            blockers.add("environment:not_approved_non_production")
        if environment.company_id != evidence.expected_company_id:
            blockers.add("environment:company_scope_mismatch")
        if environment.branch_id != evidence.expected_branch_id:
            blockers.add("environment:branch_scope_mismatch")
        if not _is_sha256(environment.database_identity_sha256) or not _is_sha256(
            environment.configuration_digest
        ):
            blockers.add("environment:invalid_evidence")
        if not environment.isolated_network:
            blockers.add("environment:network_not_isolated")
        if environment.preview_access_enabled:
            blockers.add("environment:preview_access_prohibited")
        if environment.production_access_enabled:
            blockers.add("environment:production_access_prohibited")
        if environment.persistent_after_teardown:
            blockers.add("environment:rollback_only_required")
        if not any(item.startswith("environment:") for item in blockers):
            completed.add("environment_verified")

    identity_by_entity = {item.entity: item for item in evidence.identity_counts}
    if len(identity_by_entity) != len(evidence.identity_counts):
        blockers.add("identity:duplicate_entity_summary")
    if set(identity_by_entity) != set(INCLUDED_ENTITIES):
        blockers.add("identity:included_entity_boundary_mismatch")
    for entity, item in identity_by_entity.items():
        values = (
            item.input_count,
            item.valid_count,
            item.missing_count,
            item.duplicate_count,
            item.ambiguous_count,
            item.conflicting_count,
            item.unresolved_target_count,
            item.owner_disposition_required_count,
        )
        if entity in EXCLUDED_ENTITIES or any(value < 0 for value in values):
            blockers.add(f"identity:{entity}:invalid_summary")
        if item.input_count != sum(values[1:7]):
            blockers.add(f"identity:{entity}:counts_do_not_reconcile")
        if item.owner_disposition_required_count > item.unresolved_target_count:
            blockers.add(f"identity:{entity}:disposition_count_invalid")
    if identity_by_entity and not any(
        item.startswith("identity:") for item in blockers
    ):
        completed.add("identity_summary_verified")

    disposition = evidence.owner_dispositions
    if disposition is None:
        blockers.add("disposition:summary_missing")
    else:
        if (
            min(
                disposition.required_count,
                disposition.resolved_count,
                disposition.unresolved_count,
            )
            < 0
        ):
            blockers.add("disposition:negative_count")
        if (
            disposition.required_count
            != disposition.resolved_count + disposition.unresolved_count
        ):
            blockers.add("disposition:counts_do_not_reconcile")
        if disposition.resolved_count != len(disposition.evidence_digests):
            blockers.add("disposition:evidence_count_mismatch")
        if tuple(
            sorted(set(disposition.evidence_digests))
        ) != disposition.evidence_digests or any(
            not _is_sha256(item) for item in disposition.evidence_digests
        ):
            blockers.add("disposition:invalid_evidence")
        expected_required = sum(
            item.owner_disposition_required_count for item in evidence.identity_counts
        )
        if disposition.required_count != expected_required:
            blockers.add("disposition:identity_summary_mismatch")
        if disposition.unresolved_count:
            blockers.add("disposition:owner_review_required")
        if not any(item.startswith("disposition:") for item in blockers):
            completed.add("owner_dispositions_verified")

    if evidence.teardown_plan is None:
        blockers.add("teardown:plan_missing")
    else:
        try:
            validate_teardown_plan(evidence.teardown_plan)
        except ValueError:
            blockers.add("teardown:plan_invalid")
        else:
            if (
                evidence.teardown_plan.company_id != evidence.expected_company_id
                or evidence.teardown_plan.branch_id != evidence.expected_branch_id
            ):
                blockers.add("teardown:scope_mismatch")
            else:
                completed.add("teardown_verified")

    resume = evidence.resume_retry
    if resume is None:
        blockers.add("resume:contract_missing")
    else:
        manifest_digest = manifest.manifest_digest if manifest else None
        if resume.manifest_digest != manifest_digest:
            blockers.add("resume:manifest_mismatch")
        if resume.ordered_checkpoints != REQUIRED_RESUME_CHECKPOINTS:
            blockers.add("resume:checkpoint_contract_mismatch")
        if resume.last_verified_checkpoint not in (None, *REQUIRED_RESUME_CHECKPOINTS):
            blockers.add("resume:unknown_checkpoint")
        if not (
            resume.retry_requires_same_manifest
            and resume.retry_requires_same_code_sha
            and resume.replay_zero_delta_required
        ):
            blockers.add("resume:idempotency_requirements_missing")
        if not resume.idempotency_identity:
            blockers.add("resume:idempotency_identity_missing")
        if not any(item.startswith("resume:") for item in blockers):
            completed.add("resume_retry_verified")

    audit = evidence.audit_trail
    if audit is None:
        blockers.add("audit:contract_missing")
    else:
        if resume and audit.run_identity != resume.run_identity:
            blockers.add("audit:run_identity_mismatch")
        if audit.ordered_event_codes != REQUIRED_AUDIT_EVENTS:
            blockers.add("audit:event_contract_mismatch")
        if not audit.append_only:
            blockers.add("audit:append_only_required")
        if len(audit.evidence_digests) != len(audit.ordered_event_codes):
            blockers.add("audit:evidence_count_mismatch")
        if tuple(sorted(set(audit.evidence_digests))) != audit.evidence_digests or any(
            not _is_sha256(item) for item in audit.evidence_digests
        ):
            blockers.add("audit:invalid_evidence")
        if not any(item.startswith("audit:") for item in blockers):
            completed.add("audit_contract_verified")

    external_prefixes = ("gate:",)
    technical_blockers = tuple(
        sorted(item for item in blockers if not item.startswith(external_prefixes))
    )
    authorized = not blockers
    technically_executable = not technical_blockers
    ordered_blockers = tuple(sorted(blockers))
    canonical = (
        DRY_RUN_PREFLIGHT_VERSION,
        evidence,
        tuple(sorted(completed)),
        ordered_blockers,
        technically_executable,
        authorized,
    )
    digest = _digest(canonical)
    return DryRunPreflightAssessment(
        assessment_id=uuid5(DRY_RUN_NAMESPACE, f"preflight:{digest}"),
        assessment_digest=digest,
        status="authorized_for_separate_mig_2_operation" if authorized else "blocked",
        technically_executable=technically_executable,
        authorized_to_execute=authorized,
        completed_gates=tuple(sorted(completed)),
        blockers=ordered_blockers,
        manifest_digest=manifest.manifest_digest if manifest else None,
        environment_identity=environment.environment_identity if environment else None,
    )
