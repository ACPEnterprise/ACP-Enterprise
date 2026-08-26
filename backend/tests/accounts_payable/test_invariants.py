from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.accounts_payable.contracts import BillLineSpec, BillSpec, DisbursementSpec


def test_bill_contract_keeps_receipt_references_as_evidence_only() -> None:
    line = BillLineSpec(description="Material", quantity=Decimal("1"), net_amount=Decimal("10"), tax_amount=Decimal("0"), mapping_id=uuid4(), branch_id=uuid4(), purchasing_reference="PO-evidence", receipt_reference="receipt-evidence")
    spec = BillSpec(company_id=uuid4(), branch_id=line.branch_id, actor_user_id=uuid4(), vendor_id=uuid4(), vendor_document_number="V-1", bill_date=date(2026, 8, 1), received_date=date(2026, 8, 2), due_date=date(2026, 8, 31), terms_snapshot="Net 30", currency="USD", source_system="manual", source_identity="evidence-1", source_digest="a" * 64, evidence_reference="restricted://bill/1", idempotency_key="bill-1", lines=(line,))
    assert spec.lines[0].receipt_reference == "receipt-evidence"
    assert not hasattr(spec, "purchase_order_creates_liability")


def test_disbursement_contract_contains_no_money_movement_credentials() -> None:
    fields = set(DisbursementSpec.__dataclass_fields__)
    assert {"source_identity", "evidence_digest", "recorder_user_id", "approver_user_id"} <= fields
    assert not ({"bank_account", "routing_number", "credential", "payment_token"} & fields)
