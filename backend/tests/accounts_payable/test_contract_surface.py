from pathlib import Path

import pytest

from app.accounts_payable.errors import APValidation
from app.accounts_payable.models import AccountingVendor, Disbursement, DuplicateOverride, VendorBill
from app.accounts_payable.service import normalize_document
from app.events.types import EventType
from app.platform.permissions.codes import AccountsPayablePermission


def test_permission_and_event_contract_is_exact() -> None:
    assert AccountsPayablePermission.ALL == {
        "COMPANY_ACCOUNTS_PAYABLE_READ", "COMPANY_ACCOUNTS_PAYABLE_VENDOR_MANAGE",
        "COMPANY_ACCOUNTS_PAYABLE_BILL_PREPARE", "COMPANY_ACCOUNTS_PAYABLE_BILL_APPROVE",
        "COMPANY_ACCOUNTS_PAYABLE_CREDIT_MANAGE", "COMPANY_ACCOUNTS_PAYABLE_DISBURSEMENT_RECORD",
        "COMPANY_ACCOUNTS_PAYABLE_RECONCILE", "COMPANY_ACCOUNTS_PAYABLE_REPORT_READ",
    }
    required = {
        "accounts_payable.vendor_created", "accounts_payable.vendor_mapped",
        "accounts_payable.bill_approved", "accounts_payable.bill_reversed",
        "accounts_payable.vendor_credit_issued", "accounts_payable.vendor_credit_applied",
        "accounts_payable.disbursement_recorded", "accounts_payable.disbursement_reversed",
        "accounts_payable.reconciliation_required",
    }
    assert required <= {event.value for event in EventType}


def test_document_normalization_is_deterministic_and_blank_fails_closed() -> None:
    assert normalize_document(" inv- 001/a ") == "INV001A"
    with pytest.raises(APValidation):
        normalize_document("---")


def test_database_constraints_enforce_identity_duplicate_and_sod_boundaries() -> None:
    vendor_constraints = {constraint.name for constraint in AccountingVendor.__table__.constraints}
    bill_constraints = {constraint.name for constraint in VendorBill.__table__.constraints}
    override_constraints = {constraint.name for constraint in DuplicateOverride.__table__.constraints}
    disbursement_constraints = {constraint.name for constraint in Disbursement.__table__.constraints}
    assert "uq_ap_vendors_company_code" in vendor_constraints
    assert "uq_ap_bills_vendor_document" in bill_constraints
    assert "uq_ap_bills_source_identity" in bill_constraints
    assert "ck_ap_duplicate_override_sod" in override_constraints
    assert "ck_ap_disbursements_sod" in disbursement_constraints


def test_slot_four_parent_and_domain_seams() -> None:
    root = Path(__file__).resolve().parents[2]
    migration = (root / "alembic/versions/y0p2k4m6q831_create_day_one_accounts_payable_runtime.py").read_text()
    service = (root / "app/accounts_payable/service.py").read_text()
    assert 'down_revision: str | Sequence[str] | None = "x9n1j3l5p720"' in migration
    assert "app.purchasing" not in service
    assert "app.payments" not in service
    assert "JournalEntry" not in service
    assert "bank_credentials" not in service.lower()
