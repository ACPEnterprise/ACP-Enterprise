import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ACCOUNTING = ROOT / "docs" / "architecture" / "accounting"
CONTRACT = ACCOUNTING / "domain-event-posting-contract.md"
PACKET = ACCOUNTING / "acc-post-1.packet.json"


def _packet() -> dict[str, object]:
    return json.loads(PACKET.read_text())


def test_packet_is_machine_closed_and_not_startable() -> None:
    packet = _packet()
    assert packet["schema_version"] == "1.0"
    assert packet["packet_id"] == "ACC.POST.1"
    assert packet["status"] == "not_startable"
    dependencies = packet["dependencies"]
    assert set(dependencies["complete"]) == {
        "ACC.CORE.CONTRACT.1",
        "ACC.CORE.1",
        "ACC.AR.CONTRACT.1",
        "INVOICE.1-3.ACCEL",
        "ACC.AP.CONTRACT.1",
        "PAY.CONTRACT.1",
    }
    assert len(dependencies["blocked"]) == 7
    assert packet["migration"]["slot"] == 5
    assert packet["migration"]["sibling_heads_allowed"] is False
    assert packet["serialization"]["type"] == "TYPE B"
    assert packet["environment_gates"]["real_data_import"] == "prohibited"


def test_packet_preserves_exact_accounting_order_and_boundaries() -> None:
    packet = _packet()
    assert packet["serialization"]["order"] == [
        "ACC.CORE.1",
        "INVOICE.1-3.ACCEL",
        "PAY.1-3.ACCEL",
        "ACC.AP.1",
        "ACC.POST.1",
        "ACC.RPT.1",
        "ACC.MIG.1",
    ]
    assert "backend/app/accounting/posting/**" in packet["allowed_paths"]
    assert "backend/app/accounting_migration/**" in packet["prohibited_paths"]
    assert len(packet["required_invariants"]) == 10
    assert len(packet["validation"]) >= 15


def test_accepted_and_blocked_source_facts_are_explicit() -> None:
    packet = _packet()
    facts = packet["accepted_source_facts"]
    assert set(facts["invoice_ar"]) == {
        "invoice.created",
        "invoice.issued",
        "invoice.voided",
        "invoice.credit_memo_issued",
        "invoice.write_off_recorded",
        "invoice.payment_applied",
        "invoice.payment_application_reversed",
        "invoice.correction_replacement_linked",
    }
    assert set(facts["accounts_payable"]) == {
        "accounts_payable.vendor_created",
        "accounts_payable.vendor_mapped",
        "accounts_payable.bill_approved",
        "accounts_payable.bill_reversed",
        "accounts_payable.vendor_credit_issued",
        "accounts_payable.vendor_credit_applied",
        "accounts_payable.disbursement_recorded",
        "accounts_payable.disbursement_reversed",
        "accounts_payable.reconciliation_required",
    }
    assert set(facts["payment"]) == {
        "payment.intent_created",
        "payment.authorization_recorded",
        "payment.receipt_captured",
        "payment.failed",
        "payment.refund_requested",
        "payment.refund_succeeded",
        "payment.refund_failed",
        "payment.dispute_recorded",
        "payment.deposit_submitted",
        "payment.deposit_reversed",
        "payment.settlement_received",
        "payment.settlement_reconciled",
        "payment.reconciliation_exception_opened",
        "payment.reconciliation_exception_resolved",
    }
    for domain in ("inventory_financial", "payroll_summary"):
        assert "SOURCE CONTRACT REQUIRED" in facts[domain]


def test_contract_links_resolve_and_freezes_required_controls() -> None:
    text = CONTRACT.read_text()
    normalized = " ".join(text.split())
    for relative in (
        "core-ledger-contract.md",
        "accounts-receivable-invoice-contract.md",
        "accounts-payable-vendor-contract.md",
        "payment-cash-settlement-contract.md",
        "integration-control.md",
        "acc-post-1.packet.json",
    ):
        assert (CONTRACT.parent / relative).resolve().is_file()
    for invariant in (
        "AUTHORITATIVE PRODUCER FACT OR FINANCE",
        "SOURCE CONTRACT REQUIRED",
        "equal debit and credit totals",
        "closed/closing period fails closed",
        "Exact replay returns the original journal/receipt",
        "Reconciliation reports tie every eligible event exactly once",
        "w8m0i2k4n619",
        "not startable today",
    ):
        assert invariant in normalized
