from app.business_economics.source_conformance import (
    EconomicComponent,
    EvidenceAssertion,
    EvidenceConfidence,
    assess_source_conformance,
)


def _assertion(
    identity: str,
    component: EconomicComponent,
    value: str,
    *,
    source: str = "hcp",
    confidence: EvidenceConfidence = EvidenceConfidence.AVAILABLE,
    limitations: tuple[str, ...] = (),
) -> EvidenceAssertion:
    return EvidenceAssertion(
        assertion_id=identity,
        source_system=source,
        source_authority=f"{source}_source_reported",
        component=component,
        semantic_key="job:synthetic-1",
        value_digest=value * 64,
        evidence_digest="e" * 64,
        package_digest="f" * 64,
        confidence=confidence,
        limitations=limitations,
    )


def test_missing_evidence_is_unknown_never_zero() -> None:
    result = assess_source_conformance(())
    assert all(
        item.confidence is EvidenceConfidence.UNKNOWN for item in result.findings
    )
    assert all(not item.evidence_ids for item in result.findings)
    assert not result.beacon_handoff_eligible


def test_hcp_and_qbo_conflict_preserves_both_assertions_without_winner() -> None:
    result = assess_source_conformance(
        (
            _assertion("hcp-paid", EconomicComponent.SETTLEMENT, "a"),
            _assertion("qbo-open", EconomicComponent.SETTLEMENT, "b", source="qbo"),
        )
    )
    finding = next(
        item
        for item in result.findings
        if item.component is EconomicComponent.SETTLEMENT
    )
    assert finding.confidence is EvidenceConfidence.CONFLICTING
    assert finding.evidence_ids == ("hcp-paid", "qbo-open")
    assert finding.source_authorities == ("hcp_source_reported", "qbo_source_reported")
    assert finding.conflict_keys == ("job:synthetic-1",)
    assert result.beacon_handoff_eligible


def test_available_source_without_required_policy_remains_partial() -> None:
    result = assess_source_conformance(
        (
            _assertion(
                "job",
                EconomicComponent.DIRECT_LABOR,
                "a",
                limitations=("satisfies:authoritative_job_time",),
            ),
        )
    )
    finding = next(
        item
        for item in result.findings
        if item.component is EconomicComponent.DIRECT_LABOR
    )
    assert finding.confidence is EvidenceConfidence.PARTIAL
    assert finding.missing_requirements == ("approved_labor_burden",)


def test_complete_public_evidence_can_be_available_without_computing_profit() -> None:
    result = assess_source_conformance(
        (
            _assertion(
                "job",
                EconomicComponent.JOB_IDENTITY,
                "a",
                limitations=("satisfies:authoritative_job_identity",),
            ),
        )
    )
    finding = next(
        item
        for item in result.findings
        if item.component is EconomicComponent.JOB_IDENTITY
    )
    assert finding.confidence is EvidenceConfidence.AVAILABLE
    assert finding.missing_requirements == ()


def test_assessment_is_deterministic_across_input_order() -> None:
    left = _assertion("left", EconomicComponent.REVENUE, "a", source="qbo")
    right = _assertion("right", EconomicComponent.JOB_IDENTITY, "b")
    assert assess_source_conformance((left, right)) == assess_source_conformance(
        (right, left)
    )
