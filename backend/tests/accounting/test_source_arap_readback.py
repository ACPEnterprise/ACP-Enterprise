from decimal import Decimal
from uuid import uuid4

import pytest
from app.accounting.source_arap_readback import (
    SourceOpenItem,
    SourceTotal,
    project_source_arap,
)
from app.source_history.registration import SourceRegistration

DIGEST = "a" * 64


def registration(*, provider: str = "quickbooks_online") -> SourceRegistration:
    return SourceRegistration(
        "registration-1",
        provider,
        uuid4(),
        DIGEST,
        "b" * 64,
        3,
        {"custody": "sanitized_fixture"},
    )


def item(source_id: str, kind: str, amount: str, **changes: object) -> SourceOpenItem:
    values = {
        "source_id": source_id,
        "account_kind": kind,
        "counterparty_source_id": f"party-{source_id}",
        "counterparty_label": "Sanitized counterparty",
        "transaction_date": "2025-01-15",
        "original_amount": Decimal(amount),
        "open_amount": Decimal(amount),
        "evidence_digest": DIGEST,
        "known_exception": None,
    }
    values.update(changes)
    return SourceOpenItem(**values)  # type: ignore[arg-type]


def test_projects_source_backed_ar_and_ap_without_native_admission() -> None:
    records = (
        item("invoice-1", "accounts_receivable", "125.40"),
        item("bill-1", "accounts_payable", "80.00"),
    )
    result = project_source_arap(
        registration(),
        records,
        (
            SourceTotal("accounts_receivable", Decimal("125.40")),
            SourceTotal("accounts_payable", Decimal("80.00")),
        ),
    )

    assert result.items == records
    assert result.calculated_totals["accounts_receivable"] == Decimal("125.40")
    assert result.calculated_totals["accounts_payable"] == Decimal("80.00")
    assert result.exceptions == ()
    assert result.read_only is True
    assert result.admitted_as_native is False
    assert result.mutation_authority == "none"


def test_preserves_known_exception_and_reports_total_mismatch() -> None:
    result = project_source_arap(
        registration(),
        (
            item(
                "invoice-2",
                "accounts_receivable",
                "50.00",
                known_exception="customer reference absent from sanitized packet",
            ),
        ),
        (SourceTotal("accounts_receivable", Decimal("55.00")),),
    )

    assert result.source_totals["accounts_receivable"] == Decimal("55.00")
    assert result.calculated_totals["accounts_receivable"] == Decimal("50.00")
    assert result.items[0].counterparty_source_id == "party-invoice-2"
    assert any("customer reference absent" in value for value in result.exceptions)
    assert any(
        "reported=55.00 calculated=50.00" in value for value in result.exceptions
    )
    assert "source total unavailable: accounts_payable" in result.exceptions


def test_rejects_non_qbo_or_untraceable_input() -> None:
    with pytest.raises(ValueError, match="QuickBooks"):
        project_source_arap(registration(provider="hcp"), (), ())
    with pytest.raises(ValueError, match="invalid evidence digest"):
        project_source_arap(
            registration(),
            (item("bill-2", "accounts_payable", "10", evidence_digest="bad"),),
            (),
        )
