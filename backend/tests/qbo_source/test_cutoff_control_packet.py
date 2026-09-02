from decimal import Decimal

from app.qbo_source.cutoff_control_packet import (
    _basis_disposition,
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
