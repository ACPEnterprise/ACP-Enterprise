import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKET = ROOT / "docs" / "architecture" / "accounting" / "invoice-1-3-accel.packet.json"
CONTRACT = PACKET.with_name("accounts-receivable-invoice-contract.md")


def _packet() -> dict[str, object]:
    return json.loads(PACKET.read_text())


def test_invoice_execution_packet_is_closed_and_machine_enforceable():
    packet = _packet()
    assert packet["schema_version"] == "1.0"
    assert packet["packet_id"] == "INVOICE.1-3.ACCEL"
    assert packet["status"] == "ready_for_owner_start"
    assert set(packet["dependencies"]) == {
        "ACC.AR.CONTRACT.1",
        "ACC.CORE.1",
        "CRM.2",
        "EST.4",
        "OPS.1",
        "PLAT.1",
        "COMMS.1",
    }
    migration = packet["migration"]
    assert migration["authority"] == "Accounting migration slot 2"
    assert migration["single_head_required"] is True
    assert packet["serialization"]["type"] == "TYPE B"
    assert packet["environment_gates"]["real_data_import"] == "prohibited"


def test_packet_freezes_lifecycle_events_permissions_and_boundaries():
    packet = _packet()
    assert set(packet["lifecycle_states"]) == {
        "draft",
        "cancelled",
        "issued",
        "partially_paid",
        "adjusted",
        "paid",
        "voided",
    }
    assert len(packet["required_events"]) == 8
    assert len(packet["required_permissions"]) == 5
    assert "backend/app/invoicing/**" in packet["allowed_paths"]
    assert "backend/app/payments/**" in packet["prohibited_paths"]
    assert (
        "backend/app/accounting/** except consumption of an accepted public contract"
        in packet["prohibited_paths"]
    )
    assert len(packet["required_invariants"]) == 9
    assert len(packet["validation"]) >= 10


def test_contract_links_resolve_and_names_authoritative_seams():
    text = CONTRACT.read_text()
    for relative in (
        "day-1-control-contract.md",
        "implementation-packets.md",
        "../adr/0005-internal-accounting-system-of-record.md",
    ):
        assert (CONTRACT.parent / relative).resolve().is_file()
    for seam in (
        "EST.4",
        "PAY.1-3.ACCEL",
        "ACC.POST.1",
        "ACC.CORE.1",
        "Company/Branch",
        "QuickBooks accounting basis",
    ):
        assert seam in text


def test_contract_prohibits_silent_financial_drift():
    text = CONTRACT.read_text().lower()
    for invariant in (
        "never zero",
        "never updated or deleted",
        "cannot drift",
        "reconciliation_required",
        "contradictory replay",
        "negative open invoices",
    ):
        assert invariant in text
