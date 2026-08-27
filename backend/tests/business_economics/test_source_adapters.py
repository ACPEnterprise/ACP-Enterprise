from datetime import date, datetime, timezone

from app.business_economics.source_adapters import (
    PublicOperationalEvidence,
    adapt_public_operational_evidence,
    adapt_qbo_economics_evidence,
)
from app.business_economics.source_conformance import (
    EconomicComponent,
    EvidenceConfidence,
    assess_source_conformance,
)
from app.qbo_source.contracts import QboSourceEnvelope, SnapshotIdentity
from app.qbo_source.economics_evidence import assess_qbo_economics_evidence


def _qbo_invoice() -> QboSourceEnvelope:
    return QboSourceEnvelope.from_native(
        snapshot=SnapshotIdentity(
            snapshot_id="synthetic",
            realm_id="synthetic",
            environment="production",
            accounting_date_cutoff=date(2026, 8, 25),
            cutoff_timezone="America/New_York",
            started_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
            api_minor_version=75,
        ),
        native_entity_type="invoice",
        native_id="synthetic-invoice",
        payload={"Id": "synthetic-invoice", "Balance": 10},
        source_status="open",
        source_accounting_meaning={"Balance": 10},
    )


def test_qbo_adapter_preserves_source_reported_partial_authority() -> None:
    qbo = assess_qbo_economics_evidence(
        source_manifest_sha256="a" * 64,
        source_manifest_state="complete",
        envelopes=(("b" * 64, _qbo_invoice()),),
    )
    assertions = adapt_qbo_economics_evidence(qbo)
    assert len(assertions) == 1
    assert assertions[0].component is EconomicComponent.REVENUE
    assert assertions[0].confidence is EvidenceConfidence.PARTIAL
    assert assertions[0].source_authority == "quickbooks_online_source_reported"
    assert "revenue_recognition_not_finance_accepted" in assertions[0].limitations


def test_partial_qbo_package_is_unknown_not_zero() -> None:
    qbo = assess_qbo_economics_evidence(
        source_manifest_sha256="a" * 64,
        source_manifest_state="partial",
        envelopes=(("b" * 64, _qbo_invoice()),),
    )
    assert adapt_qbo_economics_evidence(qbo)[0].confidence is EvidenceConfidence.UNKNOWN


def test_public_hcp_handoff_uses_metadata_only_and_can_close_job_identity() -> None:
    public = PublicOperationalEvidence(
        assertion_id="hcp-job-synthetic",
        source_system="housecall_pro",
        source_authority="hcp_authoritative_operational_source",
        component=EconomicComponent.JOB_IDENTITY,
        semantic_key="job:synthetic",
        value_digest="c" * 64,
        evidence_digest="d" * 64,
        package_digest="e" * 64,
        confidence=EvidenceConfidence.AVAILABLE,
        satisfied_requirements=("authoritative_job_identity",),
    )
    assessment = assess_source_conformance(adapt_public_operational_evidence((public,)))
    finding = next(
        item
        for item in assessment.findings
        if item.component is EconomicComponent.JOB_IDENTITY
    )
    assert finding.confidence is EvidenceConfidence.AVAILABLE
    assert finding.missing_requirements == ()


def test_explicit_reconciliation_key_exposes_hcp_qbo_conflict_without_winner() -> None:
    qbo = assess_qbo_economics_evidence(
        source_manifest_sha256="a" * 64,
        source_manifest_state="complete",
        envelopes=(("b" * 64, _qbo_invoice()),),
    )
    qbo_assertion = qbo.assertions[0]
    qbo_adapted = adapt_qbo_economics_evidence(
        qbo, semantic_keys={qbo_assertion.assertion_id: "job:synthetic:revenue"}
    )
    hcp = adapt_public_operational_evidence(
        (
            PublicOperationalEvidence(
                assertion_id="hcp-invoice-synthetic",
                source_system="housecall_pro",
                source_authority="hcp_source_reported",
                component=EconomicComponent.REVENUE,
                semantic_key="job:synthetic:revenue",
                value_digest="c" * 64,
                evidence_digest="d" * 64,
                package_digest="e" * 64,
                confidence=EvidenceConfidence.PARTIAL,
            ),
        )
    )
    finding = next(
        item
        for item in assess_source_conformance((*qbo_adapted, *hcp)).findings
        if item.component is EconomicComponent.REVENUE
    )
    assert finding.confidence is EvidenceConfidence.CONFLICTING
    assert finding.evidence_ids == ("hcp-invoice-synthetic", qbo_assertion.assertion_id)
