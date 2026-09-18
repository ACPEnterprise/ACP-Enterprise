from dataclasses import replace

import pytest
from app.payroll.federal_tax_rules_2026 import (
    TaxDeductionCalculationError,
    florida_state_income_tax_applicability,
)
from app.payroll.tax_reconciliation_2026 import (
    OFFICIAL_SOURCE_DIGESTS,
    REFERENCE_CASES,
    build_lianne_readiness_packet,
    reconcile_2026_reference_cases,
    validate_florida_reference_case,
)


def test_every_independent_reference_case_has_zero_variance() -> None:
    results = reconcile_2026_reference_cases()
    assert len(results) == len(REFERENCE_CASES) == 22
    assert all(item.passed for item in results)
    assert all(item.exact_variance == 0 for item in results)
    assert all(
        item.acp_taxable_basis == item.expected_taxable_basis for item in results
    )
    assert len({item.evidence_digest for item in results}) == len(results)


def test_reconciliation_detects_material_variance() -> None:
    altered = replace(
        REFERENCE_CASES[0], expected_result=REFERENCE_CASES[0].expected_result + 1
    )
    from app.payroll.tax_reconciliation_2026 import _reconcile

    result = _reconcile(altered)
    assert not result.passed
    assert result.exact_variance == -1


def test_official_sources_have_sha256_digests() -> None:
    assert all(len(value) == 64 for value in OFFICIAL_SOURCE_DIGESTS)
    assert all(
        set(value) <= set("0123456789abcdef") for value in OFFICIAL_SOURCE_DIGESTS
    )


def test_florida_requires_both_explicit_jurisdictions() -> None:
    assert validate_florida_reference_case().passed
    with pytest.raises(TaxDeductionCalculationError, match="explicit US-FL"):
        florida_state_income_tax_applicability(
            work_jurisdiction="US-FL", residence_jurisdiction="UNKNOWN"
        )


def test_real_employee_packet_never_invents_lianne_inputs() -> None:
    packet = build_lianne_readiness_packet()
    assert packet.state == "BLOCKED_PENDING_AUTHORIZED_REAL_INPUTS"
    assert any(
        "W-4 election entered and approved" in item for item in packet.prerequisites
    )
    assert any(
        "do not infer missing YTD" in item for item in packet.prohibited_inferences
    )
    assert "READY_FOR_PAYROLL" in packet.execution_steps[1]
