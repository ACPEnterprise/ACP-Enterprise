from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.beacon.catalog import (
    BANK_BEA_007A_DEFINITIONS,
    NATIVE_FINANCIAL_SIGNAL_CATALOG,
    SignalClassification,
)
from app.beacon.escalation import BEACON_ESCALATION_REGISTRY, EscalationEligibility
from app.beacon.native_financial import (
    NativeFinancialEvidenceConflict,
    NativeFinancialFact,
    NativeFinancialSource,
    native_financial_signal_evaluator,
)
from app.beacon.operational_prioritization import operational_signal_prioritizer
from app.beacon.quality import EvidenceFreshnessState
from app.beacon.router import financial_control_signal_catalog

NOW = datetime(2026, 8, 28, 16, 0, tzinfo=timezone.utc)
DIGEST = "a" * 64


CASES = (
    (
        "financial.invoice.workflow_exception",
        NativeFinancialSource.INVOICE_AR,
        {"accounting_status": "reconciliation_required"},
        None,
        None,
    ),
    (
        "financial.receivable.strict_past_due",
        NativeFinancialSource.INVOICE_AR,
        {"invoice_state": "issued", "due_date": "2026-08-27", "open_amount": "1.00"},
        None,
        None,
    ),
    (
        "financial.payment.evidence_inconsistency",
        NativeFinancialSource.PAYMENTS,
        {"durable_reconciliation_exception": True},
        None,
        None,
    ),
    (
        "financial.payment.application_mismatch",
        NativeFinancialSource.PAYMENTS,
        {"invariant_failed": True},
        "payment-application:1",
        None,
    ),
    (
        "financial.payment.unapplied",
        NativeFinancialSource.PAYMENTS,
        {"receipt_state": "unapplied", "available_amount": "0.01"},
        None,
        None,
    ),
    (
        "financial.ap.bill_workflow_exception",
        NativeFinancialSource.ACCOUNTS_PAYABLE,
        {"bill_state": "rejected"},
        None,
        None,
    ),
    (
        "accounting.posting.failure",
        NativeFinancialSource.ACCOUNTING_POSTING,
        {"durable_failure": True},
        "posting:1",
        None,
    ),
    (
        "accounting.journal.rejected_or_integrity_failed",
        NativeFinancialSource.ACCOUNTING_CORE,
        {"durable_failure": True, "journal_state": "rejected"},
        None,
        None,
    ),
    (
        "accounting.reconciliation.exception",
        NativeFinancialSource.ACCOUNTING_CORE,
        {"reconciliation_state": "unreconciled"},
        "reconciliation:1",
        "cutoff:1",
    ),
    (
        "accounting.report.completeness_failure",
        NativeFinancialSource.FINANCIAL_REPORTING,
        {"report_produced": True, "completeness": "incomplete"},
        None,
        "report-cutoff:1",
    ),
    (
        "accounting.report.integrity_failure",
        NativeFinancialSource.FINANCIAL_REPORTING,
        {"durable_failure": True, "integrity": "failed"},
        None,
        None,
    ),
    (
        "accounting.period.control_violation",
        NativeFinancialSource.ACCOUNTING_CORE,
        {"durable_rejection": True, "violation_code": "closed_period"},
        None,
        None,
    ),
)


def _fact(case=CASES[0], *, company_id=None, branch_id=None) -> NativeFinancialFact:
    definition_id, source, attributes, reconciliation, cutoff = case
    subject_id = uuid4()
    return NativeFinancialFact(
        definition_id=definition_id,
        company_id=company_id or uuid4(),
        branch_id=branch_id,
        subject_id=subject_id,
        source=source,
        source_aggregate_id=subject_id,
        evidence_identities=(f"{source.value}:{subject_id}",),
        evidence_digest=DIGEST,
        observed_at=NOW,
        as_of=NOW,
        attributes=attributes,
        reconciliation_identity=reconciliation,
        cutoff_identity=cutoff,
    )


def test_catalog_contains_exact_approved_definitions_and_classifications() -> None:
    assert len(BANK_BEA_007A_DEFINITIONS) == 12
    assert len(NATIVE_FINANCIAL_SIGNAL_CATALOG.definitions) == 12
    assert {item.signal_classification for item in BANK_BEA_007A_DEFINITIONS} == {
        SignalClassification.NATIVE_FINANCIAL_WORKFLOW,
        SignalClassification.ACCOUNTING_CONTROL,
    }


@pytest.mark.parametrize("case", CASES)
def test_each_accepted_native_fact_produces_deterministic_signal(case) -> None:
    fact = _fact(case)
    first = native_financial_signal_evaluator.evaluate(fact)
    replay = native_financial_signal_evaluator.evaluate(fact)
    assert first.condition_met
    assert first.signal == replay.signal
    assert first.signal is not None
    assert first.signal.id == replay.signal.id
    assert first.signal.evidence_quality is not None
    assert first.signal.evidence_quality.conclusion_admissible
    assert (
        first.signal.evidence_quality.freshness is EvidenceFreshnessState.NOT_APPLICABLE
    )
    assert all("amount" not in item.name for item in first.signal.supporting_facts)


@pytest.mark.parametrize("case", CASES)
def test_missing_or_cleared_condition_does_not_signal(case) -> None:
    fact = replace(_fact(case), attributes={})
    result = native_financial_signal_evaluator.evaluate(fact)
    assert result.signal is None
    assert not result.condition_met


def test_conflicting_evidence_fails_closed() -> None:
    fact = replace(_fact(), conflict_identities=("invoice:a", "invoice:b"))
    with pytest.raises(NativeFinancialEvidenceConflict):
        native_financial_signal_evaluator.evaluate(fact)


def test_company_branch_and_evidence_bind_identity() -> None:
    company = uuid4()
    branch = uuid4()
    fact = _fact(company_id=company, branch_id=branch)
    first = native_financial_signal_evaluator.evaluate(fact).signal
    assert first is not None
    other_company = native_financial_signal_evaluator.evaluate(
        replace(fact, company_id=uuid4())
    ).signal
    other_branch = native_financial_signal_evaluator.evaluate(
        replace(fact, branch_id=uuid4())
    ).signal
    assert other_company is not None and other_company.id != first.id
    assert other_branch is not None and other_branch.id != first.id


def test_amount_never_changes_priority_or_ranking() -> None:
    low = _fact(CASES[1])
    high = replace(
        low,
        subject_id=uuid4(),
        source_aggregate_id=uuid4(),
        evidence_identities=("invoice:high",),
        evidence_digest="b" * 64,
        attributes={
            "invoice_state": "issued",
            "due_date": "2026-08-27",
            "open_amount": "100000.00",
        },
    )
    signals = (
        native_financial_signal_evaluator.evaluate(low).signal,
        native_financial_signal_evaluator.evaluate(high).signal,
    )
    admitted = tuple(item for item in signals if item is not None)
    queue = operational_signal_prioritizer.prioritize(
        admitted, company_id=low.company_id, branch_id=None, evaluated_at=NOW
    )
    assert all(item.ranking.urgency_policy_id is None for item in queue.items)
    assert all(
        "time was not ranked" in item.ranking.ranking_reason for item in queue.items
    )


def test_all_financial_escalation_remains_policy_gated() -> None:
    registrations = tuple(
        BEACON_ESCALATION_REGISTRY.registration(item.definition_id)
        for item in BANK_BEA_007A_DEFINITIONS
    )
    assert all(
        item.eligibility is EscalationEligibility.POLICY_MISSING and item.rule is None
        for item in registrations
    )


def test_external_and_economic_sources_are_not_representable() -> None:
    assert {item.value for item in NativeFinancialSource}.isdisjoint(
        {"qbo", "quickbooks", "hcp", "migration", "economics", "eco"}
    )


@pytest.mark.asyncio
async def test_financial_control_catalog_api_is_read_only_and_scoped() -> None:
    company_id = uuid4()
    branch_id = uuid4()
    context = type(
        "Context",
        (),
        {
            "company": type("Company", (), {"id": company_id})(),
            "active_branch": type("Branch", (), {"id": branch_id})(),
        },
    )()
    response = await financial_control_signal_catalog(context)  # type: ignore[arg-type]
    assert response.catalog_id == "BANK.BEA.007A"
    assert response.company_id == company_id
    assert response.active_branch_id == branch_id
    assert len(response.definitions) == 12
    assert all(
        item.signal_classification is not SignalClassification.OPERATIONAL
        for item in response.definitions
    )
