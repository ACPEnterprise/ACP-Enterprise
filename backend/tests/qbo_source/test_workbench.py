from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.qbo_source.handoff import (
    IntelligenceActor,
    IntelligenceEvidenceStep,
    IntelligenceProvingChain,
    MigrationHandoff,
)
from app.qbo_source.reconciliation import ReconciliationState
from app.qbo_source.workbench import (
    AmexActivityEvidence,
    AmexActivityKind,
    AssertionSource,
    EvidenceAssertion,
    ReconciliationWorkbench,
)


def assertion(
    *, source: AssertionSource, evidence_id: str, fact: str, value: str | Decimal
) -> EvidenceAssertion:
    return EvidenceAssertion(
        source=source,
        evidence_id=evidence_id,
        subject_key="invoice:synthetic-1",
        fact_name=fact,
        value=value,
    )


def test_qbo_open_and_independent_paid_remain_separate_exception() -> None:
    qbo = assertion(
        source=AssertionSource.QBO,
        evidence_id="qbo-envelope:open",
        fact="payment_status",
        value="open",
    )
    hcp = assertion(
        source=AssertionSource.HCP,
        evidence_id="hcp-assertion:paid",
        fact="payment_status",
        value="paid",
    )

    finding = ReconciliationWorkbench.compare(
        finding_id="finding:status-conflict", source=qbo, control=hcp
    )

    assert finding.state == ReconciliationState.EXCEPTION
    assert finding.source_assertion == qbo
    assert finding.control_assertion == hcp
    assert finding.winner is None
    assert qbo.value == "open"


def test_qbo_actual_zero_ap_is_preserved_and_missing_is_not_zero() -> None:
    qbo_zero = EvidenceAssertion(
        AssertionSource.QBO, "qbo:ap", "ap:total", "balance", Decimal(0)
    )
    control_zero = EvidenceAssertion(
        AssertionSource.CONTROL_REPORT,
        "control:ap",
        "ap:total",
        "balance",
        Decimal(0),
    )
    matched = ReconciliationWorkbench.compare(
        finding_id="finding:ap-zero", source=qbo_zero, control=control_zero
    )
    missing = ReconciliationWorkbench.compare(
        finding_id="finding:ap-missing", source=None, control=control_zero
    )

    assert matched.state == ReconciliationState.MATCHED
    assert matched.source_assertion is not None
    assert matched.source_assertion.value == Decimal(0)
    assert missing.state == ReconciliationState.MISSING_SOURCE_EVIDENCE
    assert missing.source_assertion is None


def test_amex_preserves_suspect_classification_and_missing_attribution() -> None:
    activity = AmexActivityEvidence(
        qbo_native_type="purchase",
        qbo_native_id="synthetic-purchase",
        envelope_sha256="a" * 64,
        account_id="synthetic-amex",
        activity_kind=AmexActivityKind.CHARGE,
        amount_as_reported=Decimal("91.25"),
        transaction_date=date(2026, 8, 20),
        posting_or_source_date_as_reported=None,
        payee_or_vendor_id="synthetic-vendor",
        qbo_classification_id="suspect-account-as-reported",
        memo_or_reference="synthetic memo",
        native_link_ids=("VendorRef:synthetic-vendor",),
        qbo_job_or_customer_id=None,
        material_attribution_id=None,
        reconciliation_state=ReconciliationState.EXCEPTION,
    )

    assert activity.qbo_classification_id == "suspect-account-as-reported"
    assert activity.missing_job_attribution
    assert activity.missing_material_attribution


def test_migration_handoff_keeps_source_lineage_after_correction() -> None:
    handoff = MigrationHandoff(
        source_manifest_sha256="a" * 64,
        source_envelope_sha256="b" * 64,
        transformation_version="synthetic-v1",
        source_reported_record_id="enterprise-source:synthetic",
        reconciliation_finding_ids=("finding:classification",),
        finance_disposition_id="finance:approved-reclass",
        accounting_correction_id="journal:reclassification",
    )

    assert handoff.source_envelope_sha256 == "b" * 64
    assert handoff.accounting_correction_id == "journal:reclassification"


def test_intelligence_chain_retains_evidence_and_only_accounting_posts() -> None:
    evidence = ("qbo:purchase", "finding:classification")
    chain = IntelligenceProvingChain(
        (
            IntelligenceEvidenceStep(
                IntelligenceActor.BUSINESS_ECONOMICS,
                "economics:inconsistency",
                evidence,
                "identify economic inconsistency",
            ),
            IntelligenceEvidenceStep(
                IntelligenceActor.BEACON,
                "beacon:signal",
                evidence,
                "raise evidence-bound signal",
            ),
            IntelligenceEvidenceStep(
                IntelligenceActor.LUMINARY,
                "luminary:recommendation",
                evidence,
                "explain likely cause and options",
            ),
            IntelligenceEvidenceStep(
                IntelligenceActor.LIA,
                "lia:guided-choice",
                evidence,
                "guide authorized resolution",
            ),
            IntelligenceEvidenceStep(
                IntelligenceActor.ACCOUNTING,
                "accounting:journal",
                evidence,
                "record authorized correction",
                posts_accounting_correction=True,
            ),
        )
    )

    assert chain.steps[-1].posts_accounting_correction
    with pytest.raises(ValueError, match="only Accounting"):
        IntelligenceEvidenceStep(
            IntelligenceActor.LUMINARY,
            "bad",
            evidence,
            "post",
            posts_accounting_correction=True,
        )
