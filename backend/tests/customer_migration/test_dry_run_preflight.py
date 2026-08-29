from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.customer_migration.dry_run_preflight import (
    REQUIRED_AUDIT_EVENTS,
    REQUIRED_EXTERNAL_GATES,
    REQUIRED_RESUME_CHECKPOINTS,
    AuditTrailContract,
    DryRunEnvironmentContract,
    DryRunPreflightInput,
    ExternalGateEvidence,
    GateStatus,
    OwnerDispositionPreflight,
    ResumeRetryContract,
    SourceIdentityPreflightCount,
    VerifiedArtifact,
    assess_dry_run_preflight,
)
from app.customer_migration.dry_run_readiness import (
    EXCLUDED_ENTITIES,
    INCLUDED_ENTITIES,
    ArtifactIdentity,
    DatasetClassification,
    DatasetFieldEvidence,
    EntityInputCount,
    ImmutableInputManifestDraft,
    TeardownPlan,
    TeardownStep,
    seal_input_manifest,
    validate_mapping_conformance,
)
from app.customer_migration.launch_mapping import V1_MAPPINGS

COMPANY = UUID(int=1)
BRANCH = UUID(int=2)
RUN = UUID(int=3)
ACTOR = UUID(int=4)
ARTIFACT = UUID(int=5)
DIGEST = "a" * 64
CODE_SHA = "b" * 40
ALEMBIC_HEAD = "e0a6c2d8f351"


def manifest():
    transforms = tuple(
        sorted(
            {
                version
                for entity in INCLUDED_ENTITIES
                for version in V1_MAPPINGS[entity].transformation_versions
            }
        )
    )
    draft = ImmutableInputManifestDraft(
        UUID(int=6),
        "synthetic-provider",
        transforms,
        tuple(
            EntityInputCount(entity, 1)
            for entity in sorted(INCLUDED_ENTITIES + EXCLUDED_ENTITIES)
        ),
        (ArtifactIdentity(ARTIFACT, DIGEST, "c" * 64, 10),),
        datetime(2026, 8, 12, tzinfo=UTC),
        "synthetic-generator/v1",
        COMPANY,
        BRANCH,
        INCLUDED_ENTITIES,
        EXCLUDED_ENTITIES,
        DatasetClassification.SYNTHETIC,
        "d" * 64,
        UUID(int=7),
        "e" * 64,
        CODE_SHA,
    )
    return seal_input_manifest(
        draft, expected_company_id=COMPANY, expected_branch_id=BRANCH
    )


def evidence(**changes: object) -> DryRunPreflightInput:
    sealed = manifest()
    fields = tuple(
        DatasetFieldEvidence(entity, V1_MAPPINGS[entity].required_fields)
        for entity in INCLUDED_ENTITIES
    ) + tuple(DatasetFieldEvidence(entity, ()) for entity in EXCLUDED_ENTITIES)
    base = DryRunPreflightInput(
        COMPANY,
        BRANCH,
        CODE_SHA,
        ALEMBIC_HEAD,
        (ALEMBIC_HEAD,),
        sealed,
        (VerifiedArtifact(ARTIFACT, "c" * 64, 10),),
        validate_mapping_conformance(sealed, fields),
        DryRunEnvironmentContract(
            "isolated-test-a",
            "synthetic",
            COMPANY,
            BRANCH,
            DIGEST,
            "f" * 64,
            True,
            False,
            False,
            False,
        ),
        tuple(
            SourceIdentityPreflightCount(entity, 1, 1, 0, 0, 0, 0, 0, 0)
            for entity in INCLUDED_ENTITIES
        ),
        OwnerDispositionPreflight(0, 0, 0, ()),
        TeardownPlan(
            RUN,
            COMPANY,
            BRANCH,
            "run_identity+source_identity",
            (TeardownStep(1, "all", "company_id+branch_id+run_identity"),),
            ("manifest", "audit"),
            ("zero_run_rows",),
            "run_identity+last_verified_checkpoint",
        ),
        ResumeRetryContract(
            RUN,
            sealed.manifest_digest,
            "manifest+company+branch+run",
            REQUIRED_RESUME_CHECKPOINTS,
            None,
            True,
            True,
            True,
        ),
        AuditTrailContract(
            RUN,
            ACTOR,
            REQUIRED_AUDIT_EVENTS,
            tuple(f"{index:064x}" for index in range(1, 9)),
            True,
        ),
        tuple(
            ExternalGateEvidence(code, GateStatus.COMPLETE, DIGEST)
            for code in REQUIRED_EXTERNAL_GATES
        ),
    )
    return replace(base, **changes)


def test_complete_preflight_is_deterministic_and_separately_authorized() -> None:
    first = assess_dry_run_preflight(evidence())
    assert first == assess_dry_run_preflight(evidence())
    assert first.assessment_id.version == 5
    assert first.technically_executable
    assert first.authorized_to_execute
    assert first.status == "authorized_for_separate_mig_2_operation"


def test_current_known_state_reports_exact_four_external_blockers() -> None:
    gates = (
        ExternalGateEvidence("mig_1_complete", GateStatus.COMPLETE, DIGEST),
        ExternalGateEvidence("ic_2_complete", GateStatus.MISSING, None),
        ExternalGateEvidence("rpt_3_complete", GateStatus.MISSING, None),
        ExternalGateEvidence("immutable_input_approved", GateStatus.MISSING, None),
        ExternalGateEvidence("type_c_operation_approved", GateStatus.MISSING, None),
    )
    result = assess_dry_run_preflight(evidence(external_gates=gates))
    assert result.technically_executable
    assert not result.authorized_to_execute
    assert result.blockers == (
        "gate:ic_2_complete:missing",
        "gate:immutable_input_approved:missing",
        "gate:rpt_3_complete:missing",
        "gate:type_c_operation_approved:missing",
    )


def test_missing_actual_dataset_and_environment_are_truthful_technical_blockers() -> (
    None
):
    result = assess_dry_run_preflight(
        evidence(
            manifest=None,
            verified_artifacts=(),
            mapping_conformance=None,
            environment=None,
            identity_counts=(),
            owner_dispositions=None,
        )
    )
    assert not result.technically_executable
    assert {
        "input:immutable_manifest_missing",
        "mapping:conformance_missing",
        "environment:contract_missing",
        "identity:included_entity_boundary_mismatch",
        "disposition:summary_missing",
    } <= set(result.blockers)


@pytest.mark.parametrize(
    ("change", "blocker"),
    (
        ({"observed_alembic_heads": ("other",)}, "schema:alembic_head_mismatch"),
        (
            {"verified_artifacts": (VerifiedArtifact(ARTIFACT, "f" * 64, 10),)},
            f"input:artifact_mismatch:{ARTIFACT}",
        ),
        ({"environment": None}, "environment:contract_missing"),
        ({"mapping_conformance": None}, "mapping:conformance_missing"),
        ({"identity_counts": ()}, "identity:included_entity_boundary_mismatch"),
        ({"owner_dispositions": None}, "disposition:summary_missing"),
        ({"teardown_plan": None}, "teardown:plan_missing"),
        ({"resume_retry": None}, "resume:contract_missing"),
        ({"audit_trail": None}, "audit:contract_missing"),
    ),
)
def test_technical_preflight_fails_closed(
    change: dict[str, object], blocker: str
) -> None:
    result = assess_dry_run_preflight(evidence(**change))
    assert not result.technically_executable
    assert blocker in result.blockers


def test_identity_duplicates_and_unresolved_dispositions_reconcile_and_block() -> None:
    identities = list(evidence().identity_counts)
    identities[0] = SourceIdentityPreflightCount("customer", 2, 0, 0, 1, 0, 0, 1, 1)
    dispositions = OwnerDispositionPreflight(1, 0, 1, ())
    result = assess_dry_run_preflight(
        evidence(identity_counts=tuple(identities), owner_dispositions=dispositions)
    )
    assert "disposition:owner_review_required" in result.blockers
    assert not result.technically_executable


def test_environment_is_rollback_only_and_cannot_reach_preview_or_production() -> None:
    base = evidence().environment
    assert base is not None
    unsafe = replace(
        base,
        preview_access_enabled=True,
        production_access_enabled=True,
        persistent_after_teardown=True,
    )
    result = assess_dry_run_preflight(evidence(environment=unsafe))
    assert {
        "environment:preview_access_prohibited",
        "environment:production_access_prohibited",
        "environment:rollback_only_required",
    } <= set(result.blockers)


def test_resume_retry_manifest_and_audit_run_identity_must_match() -> None:
    resume = evidence().resume_retry
    audit = evidence().audit_trail
    assert resume is not None and audit is not None
    result = assess_dry_run_preflight(
        evidence(
            resume_retry=replace(resume, manifest_digest="f" * 64),
            audit_trail=replace(audit, run_identity=UUID(int=99)),
        )
    )
    assert "resume:manifest_mismatch" in result.blockers
    assert "audit:run_identity_mismatch" in result.blockers
