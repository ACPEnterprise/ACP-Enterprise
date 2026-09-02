from decimal import Decimal

from app.qbo_source.cutoff_control_packet import (
    _basis_disposition,
    _identity_disposition,
    legacy_control_gap_register,
)


def test_basis_mismatch_fails_closed() -> None:
    assert (
        _basis_disposition({"embedded_basis": "accrual"}, "cash")
        == "REJECTED_BASIS_MISMATCH"
    )
    assert _basis_disposition({"embedded_basis": "cash"}, "cash") == "ACCEPTED"


def test_ar_variance_remains_explicit_decimal() -> None:
    assert Decimal("479029.48") - Decimal("479879.48") == Decimal("-850.00")


def test_legacy_gaps_never_fabricate_history() -> None:
    gaps = legacy_control_gap_register()
    assert gaps["undeposited_funds"]["state"] == "LEGACY_CONTROL_NOT_MAINTAINED"
    assert gaps["company_credit_cards"]["native"] == "START_NATIVE_AT_CUTOVER"
    assert "FABRICATION" in gaps["inventory_valuation"]["reconstruction"]


def test_successor_requires_embedded_identity_basis_and_period() -> None:
    metrics = {
        "embedded_basis": "cash",
        "strings": {"Trial Balance", "As of Aug 31, 2026"},
    }
    assert (
        _identity_disposition(metrics, "Trial Balance", "cash", "As of Aug 31, 2026")
        == "ACCEPTED_SUCCESSOR_CONTROL"
    )
    assert (
        _identity_disposition(metrics, "Trial Balance", "accrual", "As of Aug 31, 2026")
        == "REJECTED_IDENTITY_BASIS_OR_PERIOD_MISMATCH"
    )
