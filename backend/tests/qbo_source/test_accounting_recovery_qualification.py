import os
from pathlib import Path

import pytest
from scripts.qualify_qbo_accounting_recovery import qualify

ARCHIVE = Path(os.environ.get("QBO_MANUAL_ARCHIVE_TEST_ROOT", "/unavailable"))
CUSTODY_SHA256 = "f6640c0d531eaa8a822e82f697b3aaead65c8ae7b52a3c527e9616642c4d4f4a"


@pytest.mark.skipif(
    not ARCHIVE.is_dir(), reason="sealed laptop custody package unavailable"
)
def test_recovery_receipt_preserves_unresolved_ar_and_unposted_bank_evidence() -> None:
    receipt = qualify(ARCHIVE, CUSTODY_SHA256)

    assert receipt["ar_bridge"] == {
        "invoice_open_balance": "500584.34",
        "balance_sheet_accounts_receivable": "399782.43",
        "difference": "100801.91",
        "provider_unapplied_amount": "87544.91",
        "unlinked_payment_count": 73,
        "unlinked_payment_total": "85414.91",
        "provider_unapplied_minus_unlinked": "2130.00",
        "bridge_minus_provider_unapplied": "13257.00",
        "state": "UNRESOLVED_SOURCE_CROSSWALK",
    }
    assert receipt["bank_feed"] == {
        "pending_rows": 102,
        "exact_duplicate_rows": 4,
        "authoritative_amount_total": "29272.51",
        "duplicate_incremental_amount": "-872.76",
        "disposition": "UNPOSTED_SOURCE_EVIDENCE",
        "automatic_expense_creation_allowed": False,
    }
    assert receipt["accepted_as_native_accounting"] is False
    assert receipt["external_mutations"] == 0
