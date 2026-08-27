from dataclasses import replace

from app.business_economics.findings import (
    FindingState,
    FindingSubject,
    FindingType,
    SubjectKind,
    evaluate_economic_findings,
)
from app.business_economics.source_adapters import (
    PublicOperationalEvidence,
    adapt_public_operational_evidence,
)
from app.business_economics.source_conformance import (
    EconomicComponent,
    EvidenceConfidence,
)


def _evidence(
    identity: str,
    component: EconomicComponent,
    value: str,
    *,
    confidence: EvidenceConfidence = EvidenceConfidence.AVAILABLE,
    authority: str = "hcp_authoritative_operational_source",
    requirements: tuple[str, ...] = (),
) -> PublicOperationalEvidence:
    return PublicOperationalEvidence(
        assertion_id=identity,
        source_system="housecall_pro"
        if authority.startswith("hcp")
        else "quickbooks_online",
        source_authority=authority,
        component=component,
        semantic_key="job:synthetic",
        value_digest=value * 64,
        evidence_digest="e" * 64,
        package_digest="f" * 64,
        confidence=confidence,
        satisfied_requirements=requirements,
    )


def _subject(
    *components: EconomicComponent, kind: SubjectKind = SubjectKind.JOB
) -> FindingSubject:
    return FindingSubject("job-synthetic", kind, "job:synthetic", components)


def _find(findings, finding_type: FindingType):
    return next(item for item in findings if item.finding_type is finding_type)


def test_identical_evidence_produces_identical_findings_and_identity() -> None:
    assertions = adapt_public_operational_evidence(
        (
            _evidence(
                "job",
                EconomicComponent.JOB_IDENTITY,
                "a",
                requirements=("authoritative_job_identity",),
            ),
        )
    )
    first = evaluate_economic_findings(
        subjects=(_subject(EconomicComponent.JOB_IDENTITY),), assertions=assertions
    )
    second = evaluate_economic_findings(
        subjects=(_subject(EconomicComponent.JOB_IDENTITY),), assertions=assertions
    )
    assert first == second
    assert first[0].finding_id.startswith("eco-finding:")
    assert first[0].state is FindingState.READY


def test_missing_labor_is_absent_not_zero_and_yields_no_dollar_claim() -> None:
    findings = evaluate_economic_findings(
        subjects=(_subject(EconomicComponent.DIRECT_LABOR),), assertions=()
    )
    readiness = _find(findings, FindingType.LABOR_EVIDENCE_READINESS)
    leakage = _find(findings, FindingType.POTENTIAL_MARGIN_LEAKAGE)
    assert readiness.state is FindingState.ABSENT
    assert readiness.confidence is EvidenceConfidence.UNKNOWN
    assert "missing_evidence_is_not_zero" in readiness.limitations
    assert "no_dollar_loss_calculated" in leakage.limitations


def test_partial_and_unknown_evidence_remain_distinct() -> None:
    for confidence, expected in (
        (EvidenceConfidence.PARTIAL, FindingState.PARTIAL),
        (EvidenceConfidence.UNKNOWN, FindingState.UNKNOWN),
    ):
        assertions = adapt_public_operational_evidence(
            (
                _evidence(
                    "revenue", EconomicComponent.REVENUE, "a", confidence=confidence
                ),
            )
        )
        finding = _find(
            evaluate_economic_findings(
                subjects=(_subject(EconomicComponent.REVENUE),), assertions=assertions
            ),
            FindingType.REVENUE_INCONSISTENCY,
        )
        assert finding.state is expected


def test_conflicting_sources_preserve_provenance_and_choose_no_winner() -> None:
    assertions = adapt_public_operational_evidence(
        (
            _evidence("hcp-paid", EconomicComponent.SETTLEMENT, "a"),
            _evidence(
                "qbo-open",
                EconomicComponent.SETTLEMENT,
                "b",
                confidence=EvidenceConfidence.PARTIAL,
                authority="quickbooks_online_source_reported",
            ),
        )
    )
    finding = _find(
        evaluate_economic_findings(
            subjects=(_subject(EconomicComponent.SETTLEMENT),), assertions=assertions
        ),
        FindingType.SETTLEMENT_INCONSISTENCY,
    )
    assert finding.state is FindingState.CONFLICTING
    assert finding.source_authorities == (
        "hcp_authoritative_operational_source",
        "quickbooks_online_source_reported",
    )
    assert {item.assertion_id for item in finding.evidence} == {"hcp-paid", "qbo-open"}
    assert "no_source_precedence_applied" in finding.limitations


def test_qbo_unaccepted_evidence_cannot_make_revenue_ready() -> None:
    assertions = adapt_public_operational_evidence(
        (
            _evidence(
                "qbo-invoice",
                EconomicComponent.REVENUE,
                "a",
                confidence=EvidenceConfidence.PARTIAL,
                authority="quickbooks_online_source_reported",
            ),
        )
    )
    finding = _find(
        evaluate_economic_findings(
            subjects=(_subject(EconomicComponent.REVENUE),), assertions=assertions
        ),
        FindingType.REVENUE_INCONSISTENCY,
    )
    assert finding.state is FindingState.PARTIAL
    assert finding.evidence[0].source_authority == "quickbooks_online_source_reported"


def test_no_job_linkage_is_inferred_from_another_semantic_key() -> None:
    evidence = replace(
        _evidence("other-job", EconomicComponent.DIRECT_MATERIAL, "a"),
        semantic_key="job:other",
    )
    findings = evaluate_economic_findings(
        subjects=(_subject(EconomicComponent.DIRECT_MATERIAL),),
        assertions=adapt_public_operational_evidence((evidence,)),
    )
    assert (
        _find(findings, FindingType.MATERIAL_INCONSISTENCY).state is FindingState.ABSENT
    )


def test_service_line_and_overhead_require_explicit_policy_evidence() -> None:
    assertions = adapt_public_operational_evidence(
        (
            _evidence("service", EconomicComponent.SERVICE_LINE, "a"),
            _evidence("overhead", EconomicComponent.OVERHEAD, "b"),
        )
    )
    findings = evaluate_economic_findings(
        subjects=(
            _subject(
                EconomicComponent.SERVICE_LINE,
                EconomicComponent.OVERHEAD,
                kind=SubjectKind.SERVICE_LINE,
            ),
        ),
        assertions=assertions,
    )
    assert (
        _find(findings, FindingType.SERVICE_LINE_READINESS).state
        is FindingState.PARTIAL
    )
    overhead = _find(findings, FindingType.OVERHEAD_READINESS)
    assert overhead.state is FindingState.PARTIAL
    assert "missing:versioned_allocation_policy" in overhead.limitations


def test_handoff_is_explanation_safe_and_contains_no_profit_amount() -> None:
    findings = evaluate_economic_findings(
        subjects=(_subject(EconomicComponent.REVENUE),), assertions=()
    )
    leakage = _find(findings, FindingType.POTENTIAL_MARGIN_LEAKAGE)
    assert leakage.explanation_facts
    assert all("$" not in fact for fact in leakage.explanation_facts)
    assert "no_profit_calculated" not in leakage.measured_condition
