import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ACCOUNTING = ROOT / "docs" / "architecture" / "accounting"
READINESS = ACCOUNTING / "acc-post-1-readiness.md"
PACKET = ACCOUNTING / "acc-post-1.packet.json"


def test_runtime_remains_not_startable_with_exact_two_runtime_blockers() -> None:
    packet = json.loads(PACKET.read_text())
    assert packet["status"] == "not_startable"
    assert packet["dependencies"]["blocked"] == [
        "PAY.1-3.ACCEL accepted payment runtime implementing its accepted fact contract",
        "ACC.AP.1 accepted AP/vendor runtime implementing its accepted fact contract",
        "separate Owner Start",
    ]
    assert packet["startability"]["actual_account_ids_required_for_start"] is False
    assert packet["startability"]["inventory_adapter_required_for_initial_runtime"] is False
    assert packet["startability"]["payroll_adapter_required_for_initial_runtime"] is False
    assert packet["startability"]["tax_mapping_required_for_invoice_tax_activation"] is True


def test_readiness_classifies_dependencies_and_preserves_gates() -> None:
    text = " ".join(READINESS.read_text().split())
    for value in (
        "COMPLETE_AND_AUTHORITATIVE",
        "FINANCE_INPUT_REQUIRED",
        "SOURCE_EVIDENCE_REQUIRED",
        "NOT_REQUIRED_FOR_INITIAL_RUNTIME",
        "authoritative accepted runtime commits",
        "Actual Finance account IDs",
        "Preview, Production, import/cutover",
        "August 21, 2026 target has passed",
    ):
        assert value in text


def test_matrix_covers_every_required_day_one_rule_without_account_numbers() -> None:
    text = READINESS.read_text()
    for fact in (
        "Invoice issuance / AR",
        "Payment receipt/capture",
        "Payment application",
        "Refund succeeded",
        "Processor fee",
        "Deposit / clearing",
        "AP bill approval",
        "Vendor credit",
        "Disbursement evidence",
        "Sales-tax liability",
        "Inventory financial adjustment",
        "Payroll summary",
    ):
        assert fact in text
    assert "SOURCE_EVIDENCE_REQUIRED" in text
    assert "No actual Company account number" in text


def test_migration_parent_and_source_adapter_seams_are_closed() -> None:
    text = READINESS.read_text()
    assert "Invoice slot 2 → Payment slot 3 → AP slot 4 → Posting slot 5" in text
    assert "w8m0i2k4n619" in text
    assert "inventory.financial_adjustment_posted.v1" in text
    assert "payroll.summary_accepted.v1" in text
    assert "Sibling heads" in text
    assert "creates no migration" in text
