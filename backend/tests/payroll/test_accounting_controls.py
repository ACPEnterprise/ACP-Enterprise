import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from app.payroll.accounting_controls import (
    PayrollAccountingControlRequest,
    PayrollControlAmount,
    PayrollControlDisposition,
    PayrollOpeningEvidence,
    reconcile_payroll_accounting,
)
from app.payroll.operator_router import router as operator_router
from pydantic import ValidationError

CUTOFF = datetime(2026, 9, 30, 23, 59, tzinfo=timezone.utc)
DIGEST = "a" * 64


def test_payroll_accounting_control_is_read_only_operator_route() -> None:
    route = next(
        item
        for item in operator_router.routes
        if item.path == "/api/v1/payroll/operator/accounting-controls/runs/{run_id}"
    )
    assert route.methods == {"GET"}


def amount(category: str, payroll: str | None, ledger: str | None, **changes):  # type: ignore[no-untyped-def]
    values = {
        "category": category,
        "payroll_amount": Decimal(payroll) if payroll is not None else None,
        "general_ledger_amount": Decimal(ledger) if ledger is not None else None,
        "payroll_source_digest": DIGEST if payroll is not None else None,
        "ledger_source_digest": DIGEST if ledger is not None else None,
        "payroll_cutoff": CUTOFF if payroll is not None else None,
        "ledger_cutoff": CUTOFF if ledger is not None else None,
    }
    values.update(changes)
    return PayrollControlAmount(**values)


def test_payroll_liability_tie_classifies_all_control_states() -> None:
    result = reconcile_payroll_accounting(
        PayrollAccountingControlRequest(
            cutoff_at=CUTOFF,
            currency="USD",
            amounts=(
                amount("gross_wages", "100", "100"),
                amount("withholding", "20", "21"),
                amount("net_pay", "80", None),
                amount("clearing", None, "4"),
                amount("deductions", "3", "3", source_linked=False),
            ),
        )
    )
    assert result.status == "REVIEW_REQUIRED"
    assert {item.disposition for item in result.findings} == {
        PayrollControlDisposition.MATCHED,
        PayrollControlDisposition.AMOUNT_DIFFERENCE,
        PayrollControlDisposition.SOURCE_ONLY,
        PayrollControlDisposition.ACP_ONLY,
        PayrollControlDisposition.MISSING_LINK,
    }


def test_payroll_liability_tie_requires_identical_cutoff() -> None:
    stale = datetime(2026, 9, 29, 23, 59, tzinfo=timezone.utc)
    result = reconcile_payroll_accounting(
        PayrollAccountingControlRequest(
            cutoff_at=CUTOFF,
            currency="USD",
            amounts=(amount("tax", "10", "10", ledger_cutoff=stale),),
        )
    )
    assert (
        result.findings[0].disposition
        is PayrollControlDisposition.DATE_CUTOFF_DIFFERENCE
    )


def test_sealed_payroll_opening_ytd_requires_digest_and_accountant_certification() -> (
    None
):
    payload = {
        "package_identity": "payroll-opening-1",
        "cutoff_at": "2026-09-30T23:59:00Z",
        "source": "certified_legacy_payroll",
        "accountant_certification_reference": "accountant-cert-1",
        "employees": [
            {
                "employee_id": "employee-1",
                "gross_ytd": "100",
                "tax_ytd": "20",
                "deductions_ytd": "5",
                "net_ytd": "75",
                "employer_liability_ytd": "8",
                "prior_settlement_total": "75",
                "source_digest": DIGEST,
            }
        ],
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    evidence = PayrollOpeningEvidence(**payload, evidence_digest=digest)
    assert evidence.employees[0].gross_ytd == Decimal(100)
    with pytest.raises(ValidationError, match="digest conflicts"):
        PayrollOpeningEvidence(**payload, evidence_digest="b" * 64)
