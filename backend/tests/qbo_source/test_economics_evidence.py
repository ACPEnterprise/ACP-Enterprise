from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.qbo_source.contracts import QboSourceEnvelope, SnapshotIdentity
from app.qbo_source.economics_evidence import (
    EconomicsEvidenceCategory,
    EconomicsEvidenceState,
    ProfitabilityComponent,
    assess_qbo_economics_evidence,
)


def _envelope(
    kind: str, native_id: str, payload: dict[str, object]
) -> QboSourceEnvelope:
    return QboSourceEnvelope.from_native(
        snapshot=SnapshotIdentity(
            snapshot_id="synthetic-snapshot",
            realm_id="synthetic-realm",
            environment="production",
            accounting_date_cutoff=date(2026, 8, 25),
            cutoff_timezone="America/New_York",
            started_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
            api_minor_version=75,
        ),
        native_entity_type=kind,
        native_id=native_id,
        payload=payload,
        source_status="open",
        source_accounting_meaning={
            key: payload[key]
            for key in ("TxnDate", "TotalAmt", "Balance")
            if key in payload
        },
    )


def test_source_reported_invoice_remains_partial_and_unaccepted() -> None:
    invoice = _envelope(
        "invoice", "invoice-1", {"Id": "invoice-1", "TotalAmt": 125, "Balance": 125}
    )
    result = assess_qbo_economics_evidence(
        source_manifest_sha256="a" * 64,
        source_manifest_state="complete",
        envelopes=(("b" * 64, invoice),),
    )

    assertion = result.assertions[0]
    assert assertion.category is EconomicsEvidenceCategory.REVENUE_ASSERTION
    assert assertion.state is EconomicsEvidenceState.PARTIAL
    assert assertion.acceptance_status == "unreconciled_not_enterprise_accepted"
    assert assertion.reported_fields["Balance"] == 125
    assert "revenue_recognition_not_finance_accepted" in assertion.limitations
    revenue = next(
        item
        for item in result.profitability_readiness
        if item.component is ProfitabilityComponent.REVENUE
    )
    assert revenue.state is EconomicsEvidenceState.PARTIAL
    assert "finance_accepted_revenue_basis" in revenue.missing_requirements


def test_amex_purchase_is_unassigned_and_never_becomes_job_material_cost() -> None:
    purchase = _envelope(
        "purchase",
        "purchase-1",
        {"Id": "purchase-1", "TotalAmt": 80, "PaymentType": "CreditCard"},
    )
    result = assess_qbo_economics_evidence(
        source_manifest_sha256="a" * 64,
        source_manifest_state="complete",
        envelopes=(("c" * 64, purchase),),
    )

    assertion = result.assertions[0]
    assert assertion.category is EconomicsEvidenceCategory.PROCUREMENT_ASSERTION
    assert "job_attribution_unknown" in assertion.limitations
    assert "material_consumption_not_proven" in assertion.limitations
    materials = next(
        item
        for item in result.profitability_readiness
        if item.component is ProfitabilityComponent.DIRECT_MATERIAL
    )
    assert materials.state is EconomicsEvidenceState.PARTIAL
    assert "job_consumption_linkage" in materials.missing_requirements


def test_missing_profitability_sources_are_unknown_never_zero() -> None:
    result = assess_qbo_economics_evidence(
        source_manifest_sha256="a" * 64,
        source_manifest_state="complete",
        envelopes=(),
    )

    assert all(
        item.state is EconomicsEvidenceState.UNKNOWN
        for item in result.profitability_readiness
    )
    assert all(not item.evidence_ids for item in result.profitability_readiness)


def test_partial_manifest_downgrades_even_present_evidence_to_unknown() -> None:
    invoice = _envelope("invoice", "invoice-1", {"Id": "invoice-1", "TotalAmt": 10})
    result = assess_qbo_economics_evidence(
        source_manifest_sha256="a" * 64,
        source_manifest_state="partial",
        envelopes=(("b" * 64, invoice),),
    )
    revenue = next(
        item
        for item in result.profitability_readiness
        if item.component is ProfitabilityComponent.REVENUE
    )
    assert revenue.state is EconomicsEvidenceState.UNKNOWN
    assert "complete_source_manifest" in revenue.missing_requirements


def test_assessment_is_deterministic_and_preserves_source_order_independence() -> None:
    invoice = _envelope("invoice", "invoice-1", {"Id": "invoice-1", "TotalAmt": 10})
    purchase = _envelope("purchase", "purchase-1", {"Id": "purchase-1", "TotalAmt": 4})
    first = assess_qbo_economics_evidence(
        source_manifest_sha256="a" * 64,
        source_manifest_state="complete",
        envelopes=(("b" * 64, invoice), ("c" * 64, purchase)),
    )
    second = assess_qbo_economics_evidence(
        source_manifest_sha256="a" * 64,
        source_manifest_state="complete",
        envelopes=(("c" * 64, purchase), ("b" * 64, invoice)),
    )
    assert first == second


def test_invalid_or_unsealed_manifest_is_rejected() -> None:
    with pytest.raises(ValueError, match="sealed complete or partial"):
        assess_qbo_economics_evidence(
            source_manifest_sha256="a" * 64,
            source_manifest_state="in_progress",
            envelopes=(),
        )
