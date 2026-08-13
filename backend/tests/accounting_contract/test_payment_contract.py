import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKET = ROOT / "docs" / "architecture" / "accounting" / "pay-1-3-accel.packet.json"
CONTRACT = PACKET.with_name("payment-cash-settlement-contract.md")


def _packet() -> dict[str, object]:
    return json.loads(PACKET.read_text())


def test_payment_packet_is_closed_and_machine_enforceable():
    packet = _packet()
    assert packet["schema_version"] == "1.0"
    assert packet["packet_id"] == "PAY.1-3.ACCEL"
    assert packet["status"] == "ready_for_owner_start"
    assert set(packet["dependencies"]) == {
        "PAY.CONTRACT.1",
        "INVOICE.1-3.ACCEL",
        "ACC.CORE.1",
        "PLAT.1",
    }
    migration = packet["migration"]
    assert migration["authority"] == "Accounting migration slot 3"
    assert migration["implementation_parent"] == "w8m0i2k4n619"
    assert migration["single_head_required"] is True
    assert packet["serialization"]["migration_after"] == "INVOICE.1-3.ACCEL"
    assert packet["serialization"]["migration_before"] == "ACC.AP.1"


def test_packet_freezes_security_ownership_events_and_permissions():
    packet = _packet()
    assert packet["processor_boundary"]["replacement"] == "prohibited"
    assert "backend/app/payments/**" in packet["allowed_paths"]
    assert (
        "backend/app/invoicing/** except consumption of accepted public commands/contracts"
        in packet["prohibited_paths"]
    )
    assert len(packet["required_events"]) == 14
    assert len(packet["required_permissions"]) == 7
    assert len(packet["required_invariants"]) == 12
    assert len(packet["validation"]) >= 15
    assert (
        packet["environment_gates"]["real_transactions"]
        == "prohibited during implementation and automated validation"
    )


def test_contract_links_resolve_and_names_authoritative_seams():
    text = CONTRACT.read_text()
    for relative in (
        "day-1-control-contract.md",
        "accounts-receivable-invoice-contract.md",
        "core-ledger-contract.md",
        "pay-1-3-accel.packet.json",
    ):
        assert (CONTRACT.parent / relative).resolve().is_file()
    for seam in (
        "PaymentReceiptFact",
        "INVOICE.1-3.ACCEL",
        "ACC.POST.1",
        "Company, Branch",
        "undeposited funds",
        "existing external payment processor",
    ):
        assert seam in text


def test_contract_fails_closed_and_prohibits_sensitive_storage():
    text = CONTRACT.read_text().lower()
    for invariant in (
        "never zero",
        "never stores pan",
        "raw request before parsing",
        "never creates a fresh charge",
        "automatic netting",
        "reconciliation_required",
        "provider fees",
        "separation of duties",
    ):
        assert invariant in text
