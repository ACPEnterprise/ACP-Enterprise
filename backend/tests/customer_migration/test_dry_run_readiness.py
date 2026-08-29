from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from app.customer_migration.dry_run_readiness import (
    APPLICATION_ENVIRONMENT_EXCEPTIONS,
    DATA_MAPPING_EXCEPTIONS,
    DRY_RUN_EXECUTION_PLAN,
    EXCLUDED_ENTITIES,
    INCLUDED_ENTITIES,
    ArtifactIdentity,
    DatasetClassification,
    DatasetFieldEvidence,
    EntityInputCount,
    EntityReconciliationCount,
    ExceptionCode,
    ExceptionDomain,
    ExceptionRecord,
    ImmutableInputManifestDraft,
    MonetaryReconciliation,
    ReconciliationReportDraft,
    RepeatabilityEvidence,
    TeardownPlan,
    TeardownStep,
    TimingEvidence,
    classify_exception,
    seal_input_manifest,
    seal_reconciliation_report,
    validate_mapping_conformance,
    validate_teardown_plan,
)
from app.customer_migration.launch_mapping import MAPPING_CONTRACT_VERSION, V1_MAPPINGS

COMPANY = UUID(int=1)
BRANCH = UUID(int=2)
DIGEST = "a" * 64
CODE_SHA = "b" * 40


def manifest_draft() -> ImmutableInputManifestDraft:
    transforms = tuple(
        sorted(
            {
                version
                for entity in INCLUDED_ENTITIES
                for version in V1_MAPPINGS[entity].transformation_versions
            }
        )
    )
    return ImmutableInputManifestDraft(
        dataset_identity=UUID(int=3),
        provider_identity="synthetic-provider",
        transformation_contract_versions=transforms,
        entity_counts=tuple(
            EntityInputCount(entity, 1)
            for entity in sorted(INCLUDED_ENTITIES + EXCLUDED_ENTITIES)
        ),
        artifacts=(ArtifactIdentity(UUID(int=4), DIGEST, "b" * 64, 100),),
        created_at=datetime(2026, 8, 11, tzinfo=UTC),
        source_provenance="synthetic-fixture-generator/v1",
        company_id=COMPANY,
        branch_id=BRANCH,
        included_entity_classes=INCLUDED_ENTITIES,
        excluded_entity_classes=EXCLUDED_ENTITIES,
        classification=DatasetClassification.SYNTHETIC,
        sanitization_evidence_sha256="c" * 64,
        owner_approval_identity=UUID(int=5),
        owner_approval_evidence_sha256="d" * 64,
        executing_code_sha=CODE_SHA,
    )


def field_evidence() -> tuple[DatasetFieldEvidence, ...]:
    return tuple(
        DatasetFieldEvidence(entity, V1_MAPPINGS[entity].required_fields)
        for entity in INCLUDED_ENTITIES
    ) + tuple(DatasetFieldEvidence(entity, ()) for entity in EXCLUDED_ENTITIES)


def seal(draft: ImmutableInputManifestDraft | None = None):
    return seal_input_manifest(
        draft or manifest_draft(),
        expected_company_id=COMPANY,
        expected_branch_id=BRANCH,
    )


def test_manifest_is_immutable_deterministic_tenant_scoped_and_complete() -> None:
    draft = manifest_draft()
    first = seal(draft)
    assert first == seal(draft)
    assert first.manifest_id.version == 5
    assert first.draft.company_id == COMPANY
    assert first.draft.branch_id == BRANCH
    assert first.draft.mapping_contract_version == MAPPING_CONTRACT_VERSION
    assert len(first.manifest_digest) == 64


@pytest.mark.parametrize(
    ("change", "message"),
    (
        ({"mapping_contract_version": "wrong/v1"}, "mapping contract"),
        ({"included_entity_classes": INCLUDED_ENTITIES[:-1]}, "included entity"),
        ({"excluded_entity_classes": EXCLUDED_ENTITIES[:-1]}, "excluded entity"),
        ({"executing_code_sha": "short"}, "Git SHA"),
        ({"owner_approval_evidence_sha256": "bad"}, "SHA-256"),
        ({"transformation_contract_versions": ()}, "transformation"),
    ),
)
def test_manifest_fails_closed(change: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        seal(replace(manifest_draft(), **change))


@pytest.mark.parametrize(
    ("company", "branch", "message"),
    ((UUID(int=9), BRANCH, "Company"), (COMPANY, UUID(int=9), "Branch")),
)
def test_manifest_fails_closed_across_company_and_branch_scope(
    company: UUID, branch: UUID, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        seal_input_manifest(
            manifest_draft(), expected_company_id=company, expected_branch_id=branch
        )


def test_mapping_preflight_accepts_all_seven_and_preserves_three_exclusions() -> None:
    result = validate_mapping_conformance(seal(), field_evidence())
    assert result.conformant
    assert not result.violations
    assert tuple(item.entity for item in field_evidence()[:7]) == INCLUDED_ENTITIES
    assert tuple(item.entity for item in field_evidence()[7:]) == EXCLUDED_ENTITIES


def test_mapping_preflight_rejects_unsupported_optional_missing_transform_and_excluded_data() -> (
    None
):
    manifest = seal()
    evidence = list(field_evidence())
    evidence[0] = replace(
        evidence[0], populated_fields=evidence[0].populated_fields + ("is_vip",)
    )
    evidence[-1] = replace(evidence[-1], populated_fields=("payload",))
    result = validate_mapping_conformance(manifest, tuple(evidence))
    assert not result.conformant
    assert "customer:unsupported_optional_field" in result.violations
    assert "attachment:excluded_v1_entity" in result.violations
    missing_transform = seal(
        replace(
            manifest_draft(),
            transformation_contract_versions=("customer-adapter-review/v1",),
        )
    )
    result = validate_mapping_conformance(missing_transform, field_evidence())
    assert "job:missing_transformation_version" in result.violations


def test_exception_taxonomy_is_complete_and_separates_environment_failures() -> None:
    assert len(DATA_MAPPING_EXCEPTIONS) == 16
    assert len(APPLICATION_ENVIRONMENT_EXCEPTIONS) == 8
    assert DATA_MAPPING_EXCEPTIONS | APPLICATION_ENVIRONMENT_EXCEPTIONS == set(
        ExceptionCode
    )
    assert (
        classify_exception(ExceptionCode.MISSING_PARENT) is ExceptionDomain.DATA_MAPPING
    )
    assert (
        classify_exception(ExceptionCode.INFRASTRUCTURE_FAILURE)
        is ExceptionDomain.APPLICATION_ENVIRONMENT
    )


def counts() -> tuple[EntityReconciliationCount, ...]:
    return (
        EntityReconciliationCount("customer", 4, 4, 2, 1, 0, 1, 3, 1, 1, 0, 0),
        EntityReconciliationCount("estimate", 2, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0),
    )


def report_draft() -> ReconciliationReportDraft:
    timing = TimingEvidence(
        1_000_000_000, (("customer", 500),), 100, 200, 300, 400, 500, 6, 600
    )
    return ReconciliationReportDraft(
        DIGEST,
        counts(),
        (
            MonetaryReconciliation(
                "invoice",
                Decimal("10.001"),
                Decimal("8.001"),
                Decimal(1),
                Decimal(0),
                Decimal(1),
            ),
        ),
        (ExceptionRecord("customer", ExceptionCode.DUPLICATE_SOURCE_IDENTITY, DIGEST),),
        timing,
        "zero_delta",
        "verified",
    )


def test_reconciliation_seals_exact_counts_money_timing_and_exceptions() -> None:
    report = seal_reconciliation_report(report_draft())
    assert report == seal_reconciliation_report(report_draft())
    assert report.draft.timing.records_per_second == Decimal(6)
    assert len(report.result_digest) == 64


def test_reconciliation_canonicalizes_exception_money_and_timing_order() -> None:
    draft = report_draft()
    second_money = MonetaryReconciliation(
        "payment", Decimal(2), Decimal(2), Decimal(0), Decimal(0), Decimal(0)
    )
    second_exception = ExceptionRecord(
        "appointment", ExceptionCode.MISSING_PARENT, "b" * 64
    )
    unordered = replace(
        draft,
        monetary_reconciliation=(second_money, *draft.monetary_reconciliation),
        exception_ledger=(*draft.exception_ledger, second_exception),
        timing=replace(
            draft.timing,
            per_entity_elapsed_ns=(("payment", 10), ("customer", 20)),
        ),
    )
    report = seal_reconciliation_report(unordered)
    assert tuple(item.entity for item in report.draft.monetary_reconciliation) == (
        "invoice",
        "payment",
    )
    assert tuple(item.entity for item in report.draft.exception_ledger) == (
        "appointment",
        "customer",
    )
    assert report.draft.timing.per_entity_elapsed_ns == (
        ("customer", 20),
        ("payment", 10),
    )


def test_unexplained_records_and_monetary_difference_fail_closed() -> None:
    broken_count = replace(counts()[0], accepted_count=1)
    with pytest.raises(ValueError, match="disposition totals"):
        seal_reconciliation_report(
            replace(report_draft(), entity_counts=(broken_count, counts()[1]))
        )
    broken_money = replace(
        report_draft().monetary_reconciliation[0], accepted_amount=Decimal(8)
    )
    with pytest.raises(ValueError, match="monetary totals"):
        seal_reconciliation_report(
            replace(report_draft(), monetary_reconciliation=(broken_money,))
        )


def test_repeatability_ignores_wall_clock_timing_but_preserves_timing_evidence() -> (
    None
):
    base = RepeatabilityEvidence(
        DIGEST,
        MAPPING_CONTRACT_VERSION,
        ("v1",),
        CODE_SHA,
        "non-prod-a",
        DIGEST,
        DIGEST,
        DIGEST,
        DIGEST,
        DIGEST,
        DIGEST,
    )
    changed_timing = replace(base, timing_evidence_digest="b" * 64)
    assert (
        base.deterministic_comparison_digest
        == changed_timing.deterministic_comparison_digest
    )
    assert base.timing_evidence_digest != changed_timing.timing_evidence_digest


def test_execution_plan_is_ordered_and_declares_only_future_import_operational() -> (
    None
):
    assert tuple(step.order for step in DRY_RUN_EXECUTION_PLAN) == tuple(range(1, 15))
    assert [step.code for step in DRY_RUN_EXECUTION_PLAN if step.operational] == [
        "representative_non_production_import"
    ]


def teardown() -> TeardownPlan:
    return TeardownPlan(
        UUID(int=8),
        COMPANY,
        BRANCH,
        "migration_run_id+source_identity",
        (
            TeardownStep(1, "payment", "company_id+branch_id+run_identity"),
            TeardownStep(2, "customer", "company_id+branch_id+run_identity"),
        ),
        ("manifest", "reconciliation", "exceptions"),
        ("zero_operational_rows", "foreign_keys_clean"),
        "run_identity+last_completed_step",
    )


def test_teardown_is_bounded_replayable_and_fail_closed() -> None:
    assert validate_teardown_plan(teardown()) == validate_teardown_plan(teardown())
    unsafe = replace(
        teardown(), ordered_steps=(TeardownStep(1, "payment", "company_id"),)
    )
    with pytest.raises(ValueError, match="run identity"):
        validate_teardown_plan(unsafe)
