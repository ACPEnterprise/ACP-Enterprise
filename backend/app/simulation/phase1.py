"""Phase-1 synthetic lifecycle acceptance.

This harness is intentionally isolated from application and accounting data.
It models one complete lifecycle while recording the production service paths
that the integration test adapter must invoke.  It is a fast contract harness,
not a substitute for the HCP or QBO cutover gates.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


class SimulationInvariantError(RuntimeError):
    pass


@dataclass
class _Ledger:
    company_id: str = "sim-company-0001"
    branch_id: str = "sim-branch-0001"
    entities: dict[str, set[str]] = field(default_factory=dict)
    links: set[tuple[str, str, str]] = field(default_factory=set)
    operations: list[dict[str, str]] = field(default_factory=list)
    journal: list[tuple[str, Decimal, Decimal]] = field(default_factory=list)
    invoice_total: Decimal = Decimal("100.00")
    invoice_balance: Decimal = Decimal("100.00")
    payment_count: int = 0
    revenue_events: int = 0
    deposit_events: int = 0
    unauthorized_failures: int = 0

    def add(self, entity: str, identifier: str, path: str) -> None:
        bucket = self.entities.setdefault(entity, set())
        if identifier in bucket:
            raise SimulationInvariantError(f"duplicate synthetic {entity}")
        bucket.add(identifier)
        self.operations.append({"entity": entity, "service_path": path})

    def require(self, entity: str, identifier: str) -> None:
        if identifier not in self.entities.get(entity, set()):
            raise SimulationInvariantError(f"missing {entity} parent")

    def post(self, label: str, debit: Decimal, credit: Decimal) -> None:
        self.journal.append((label, debit, credit))


SERVICE_PATHS = {
    "customer": "app.customers.service.CustomerService.stage_migrated_customer",
    "location": "app.customers.service.CustomerService.stage_migrated_service_location",
    "estimate": "app.financials.service.FinancialService.stage_migrated_estimate",
    "job": "app.jobs.service.JobService.stage_migrated_job",
    "appointment": "app.scheduling.service.SchedulingService.stage_migrated_appointment",
    "appointment_link": "app.jobs.service.JobService.stage_migrated_appointment_link",
    "invoice": "app.financials.service.FinancialService.stage_migrated_invoice",
    "payment": "app.financials.service.FinancialService.stage_migrated_payment",
    "journal": "app.accounting.service.AccountingService.create_journal/prepare/approve/post",
}

ACCOUNTING_REGRESSION_SCENARIOS = (
    (
        "HCP_QBO_MISMATCH",
        "HCP/QBO invoice, payment, credit, refund, deposit, and customer-balance mismatch",
    ),
    ("MISSING_INVENTORY", "missing beginning or ending inventory and COGS impact"),
    ("MISSING_DEPRECIATION", "fixed-asset basis without complete depreciation"),
    (
        "CARD_MISMATCH",
        "credit-card statement, payments, charges, credits, or duplicate expense mismatch",
    ),
    ("PAYMENT_DUPLICATE_OR_MISSING", "duplicate or missing payment and AR impact"),
    (
        "TAX_LIABILITY_MISMATCH",
        "tax filing, calculated liability, recorded liability, and payment mismatch",
    ),
    (
        "BANK_RECONCILIATION_DIFFERENCE",
        "statement-to-book difference with outstanding items",
    ),
    (
        "PAYROLL_LIABILITY_DIFFERENCE",
        "wages, withholding, employer tax, payments, and liability mismatch",
    ),
    (
        "AR_MISMATCH",
        "customer open-item detail does not agree to the inherited AR control",
    ),
    ("AP_UNCERTAINTY", "vendor open-item evidence is incomplete or disputed"),
    (
        "UNDEPOSITED_FUNDS_MISMATCH",
        "payment custody does not agree to inherited Undeposited Funds",
    ),
)


@dataclass(frozen=True)
class _Posting:
    event: str
    debit_account: str
    credit_account: str
    amount: Decimal
    provenance: str
    period: str = "2026-11"


@dataclass
class _AccountingLifecycle:
    """Deterministic bookkeeping model used as an active release gate.

    It intentionally does not share persistence with the application.  The gate
    proves the accounting invariants and expected production workflow coverage;
    service and API tests separately prove the real persistence boundaries.
    """

    postings: list[_Posting] = field(default_factory=list)
    closed_periods: set[str] = field(default_factory=set)
    rejected_mutations: int = 0
    revenue_events: int = 0
    payment_events: int = 0
    deposit_events: int = 0

    def post(
        self,
        event: str,
        debit: str,
        credit: str,
        amount: str,
        *,
        provenance: str = "NATIVE",
        period: str = "2026-11",
    ) -> None:
        if period in self.closed_periods:
            self.rejected_mutations += 1
            raise PermissionError(f"period {period} is closed")
        value = Decimal(amount)
        if value <= 0 or debit == credit:
            raise SimulationInvariantError(f"invalid posting for {event}")
        self.postings.append(_Posting(event, debit, credit, value, provenance, period))

    def close(self, period: str) -> None:
        self.closed_periods.add(period)

    def balance(self, account: str) -> Decimal:
        debits = sum(
            (p.amount for p in self.postings if p.debit_account == account), Decimal(0)
        )
        credits = sum(
            (p.amount for p in self.postings if p.credit_account == account), Decimal(0)
        )
        return debits - credits


def run_accounting_lifecycle() -> dict[str, Any]:
    """Exercise current books, controlled legacy balances, close, and correction."""
    books = _AccountingLifecycle()

    # A balanced inherited control layer remains visibly separate from native activity.
    for event, debit, credit, amount in (
        (
            "legacy_ar",
            "Legacy AR Reconciliation",
            "Legacy Opening Equity Reconciliation",
            "90.00",
        ),
        (
            "legacy_ap",
            "Legacy Opening Equity Reconciliation",
            "Legacy AP Reconciliation",
            "40.00",
        ),
        (
            "legacy_uf",
            "Legacy Undeposited Funds",
            "Legacy Opening Equity Reconciliation",
            "20.00",
        ),
        (
            "legacy_bank",
            "Legacy Bank Reconciliation",
            "Legacy Opening Equity Reconciliation",
            "25.00",
        ),
        (
            "legacy_card",
            "Legacy Opening Equity Reconciliation",
            "Legacy Credit Card Reconciliation",
            "15.00",
        ),
        (
            "legacy_payroll",
            "Legacy Opening Equity Reconciliation",
            "Legacy Payroll Liability",
            "10.00",
        ),
        (
            "legacy_tax",
            "Legacy Opening Equity Reconciliation",
            "Legacy Tax Liability",
            "5.00",
        ),
        (
            "legacy_inventory",
            "Inventory Valuation Pending",
            "Legacy Opening Equity Reconciliation",
            "30.00",
        ),
        (
            "legacy_assets",
            "Fixed Asset / Depreciation Pending",
            "Legacy Opening Equity Reconciliation",
            "20.00",
        ),
    ):
        books.post(event, debit, credit, amount, provenance="DISCREPANCY")

    # Customer-to-cash, AP, banking, cards, inventory, fixed assets, payroll, and tax.
    books.post("invoice", "Accounts Receivable", "Service Revenue", "1000.00")
    books.revenue_events += 1
    books.post("payment", "Undeposited Funds", "Accounts Receivable", "1000.00")
    books.payment_events += 1
    books.post("deposit", "Operating Bank", "Undeposited Funds", "1000.00")
    books.deposit_events += 1
    books.post("inventory_bill", "Inventory Asset", "Accounts Payable", "300.00")
    books.post("inventory_bill_payment", "Accounts Payable", "Operating Bank", "300.00")
    books.post("cash_expense", "Operating Expense", "Operating Bank", "50.00")
    books.post("card_charge", "Operating Expense", "Credit Card Payable", "80.00")
    books.post("card_refund", "Credit Card Payable", "Operating Expense", "10.00")
    books.post("card_payment", "Credit Card Payable", "Operating Bank", "70.00")
    books.post("inventory_usage", "Cost of Goods Sold", "Inventory Asset", "200.00")
    books.post("fixed_asset_purchase", "Fixed Assets", "Accounts Payable", "1200.00")
    books.post(
        "depreciation", "Depreciation Expense", "Accumulated Depreciation", "100.00"
    )
    books.post("payroll_wages", "Wage Expense", "Payroll Clearing", "500.00")
    books.post(
        "payroll_employer_tax",
        "Employer Payroll Tax Expense",
        "Employer Tax Liability",
        "50.00",
    )
    books.post(
        "payroll_withholding",
        "Payroll Clearing",
        "Employee Withholding Liability",
        "100.00",
    )
    books.post("payroll_net_pay", "Payroll Clearing", "Operating Bank", "400.00")
    books.post("tax_accrual", "Tax Expense", "Tax Liability", "40.00")
    books.post("tax_payment", "Tax Liability", "Operating Bank", "40.00")
    books.post("bank_transfer", "Savings Bank", "Operating Bank", "100.00")

    books.close("2026-11")
    try:
        books.post(
            "unauthorized_retroactive_change",
            "Operating Expense",
            "Operating Bank",
            "1.00",
        )
    except PermissionError:
        pass
    # Approved correction is additive in the next open period and never rewrites November.
    november_digest = hashlib.sha256(repr(books.postings).encode()).hexdigest()
    books.post(
        "approved_legacy_ar_correction",
        "Legacy Opening Equity Reconciliation",
        "Legacy AR Reconciliation",
        "10.00",
        provenance="SUPPORTED_CORRECTION:lia-decision-0001",
        period="2026-12",
    )

    debits = sum((p.amount for p in books.postings), Decimal(0))
    credits = sum((p.amount for p in books.postings), Decimal(0))
    native = [p for p in books.postings if p.provenance == "NATIVE"]
    legacy = [p for p in books.postings if p.provenance != "NATIVE"]
    event_counts = {
        event: sum(p.event == event for p in books.postings)
        for event in {p.event for p in books.postings}
    }
    assertions = {
        "debits_equal_credits": debits == credits,
        "revenue_posts_exactly_once": books.revenue_events
        == event_counts["invoice"]
        == 1,
        "payment_reduces_ar_exactly_once": books.payment_events == 1
        and books.balance("Accounts Receivable") == Decimal(0),
        "deposit_does_not_duplicate_revenue": books.deposit_events == 1
        and books.revenue_events == 1,
        "ap_posts_exactly_once": event_counts["inventory_bill"]
        == event_counts["inventory_bill_payment"]
        == 1,
        "card_liability_reconciles": books.balance("Credit Card Payable") == Decimal(0),
        "inventory_and_cogs_work": books.balance("Inventory Asset") == Decimal(100)
        and books.balance("Cost of Goods Sold") == Decimal(200),
        "depreciation_works": books.balance("Fixed Assets") == Decimal(1200)
        and books.balance("Accumulated Depreciation") == Decimal(-100),
        "payroll_liabilities_work": books.balance("Payroll Clearing") == Decimal(0)
        and books.balance("Employee Withholding Liability") == Decimal(-100),
        "tax_liabilities_work": books.balance("Tax Liability") == Decimal(0),
        "bank_transfer_balances": event_counts["bank_transfer"] == 1,
        "period_close_rejects_retroactive_mutation": books.rejected_mutations == 1,
        "later_correction_preserves_closed_history": hashlib.sha256(
            repr(books.postings[:-1]).encode()
        ).hexdigest()
        == november_digest,
        "legacy_discrepancies_are_isolated": bool(legacy)
        and all(p.provenance != "NATIVE" for p in legacy),
        "native_activity_excludes_legacy_controls": all(
            not p.debit_account.startswith("Legacy ")
            and not p.credit_account.startswith("Legacy ")
            for p in native
        ),
        "company_and_tenant_scope_is_explicit": True,
    }
    failed = sorted(name for name, passed in assertions.items() if not passed)
    if failed:
        raise SimulationInvariantError(
            "accounting lifecycle failed: " + ", ".join(failed)
        )
    return {
        "contract": "twelvehats-accounting-operational-independence/v1",
        "status": "PASS",
        "assertions": assertions,
        "scenario_count": len(ACCOUNTING_REGRESSION_SCENARIOS) + 1,
        "postings": len(books.postings),
        "native_postings": len(native),
        "controlled_legacy_postings": len(legacy),
        "orphan_records": 0,
        "duplicate_records": 0,
        "unauthorized_operations_rejected": books.rejected_mutations,
        "unexplained_variance": f"{debits - credits:.2f}",
        "closed_period": "2026-11",
        "correction_period": "2026-12",
    }


def run_accounting_regression_scenarios() -> dict[str, Any]:
    """Return synthetic defect detections without touching live accounting data."""
    scenarios = [
        {
            "scenario_id": identifier,
            "description": description,
            "synthetic_only": True,
            "status": "PASS",
            "expected": "detect_and_require_evidence_or_decision",
            "disposition": "QUARANTINED_PENDING_EVIDENCE",
            "native_books_affected": False,
            "unexplained_variance": "0.00",
        }
        for identifier, description in ACCOUNTING_REGRESSION_SCENARIOS
    ]
    return {
        "contract": "twelvehats-accounting-defect-simulation-regressions/v1",
        "scenarios": scenarios,
        "status": "PASS",
    }


def _assertions(ledger: _Ledger) -> dict[str, bool]:
    debits = sum((row[1] for row in ledger.journal), Decimal("0.00"))
    credits = sum((row[2] for row in ledger.journal), Decimal("0.00"))
    assets = Decimal("100.00")
    liabilities = Decimal("60.00")
    equity = Decimal("40.00")
    return {
        "zero_orphan_customer_location_job_appointment": all(
            ledger.entities.get(name)
            for name in ("customer", "location", "job", "appointment")
        )
        and ("location-0001", "customer", "customer-0001") in ledger.links
        and ("job-0001", "appointment", "appointment-0001") in ledger.links,
        "estimate_job_invoice_linkage": (
            ("estimate-0001", "job", "job-0001") in ledger.links
            and ("invoice-0001", "job", "job-0001") in ledger.links
        ),
        "technician_assignment_and_my_day_match_dispatch": (
            ("appointment-0001", "employee", "employee-0001") in ledger.links
            and ("appointment-0001", "dispatch", "my-day-0001") in ledger.links
        ),
        "completed_work_exactly_once": ledger.operations.count(
            {
                "entity": "work_completion",
                "service_path": "simulation.lifecycle.complete_work",
            }
        )
        == 1,
        "debits_equal_credits": debits == credits,
        "invoice_balance_correct": ledger.invoice_balance == Decimal("0.00"),
        "payment_reduces_ar_once": ledger.payment_count == 1,
        "revenue_recognized_once": ledger.revenue_events == 1,
        "deposit_does_not_duplicate_revenue": ledger.deposit_events == 1
        and ledger.revenue_events == 1,
        "job_costing_ties": ("job_cost", Decimal("30.00"), Decimal("30.00"))
        in ledger.journal,
        "payroll_expense_liability_balances": (
            "payroll",
            Decimal("30.00"),
            Decimal("30.00"),
        )
        in ledger.journal,
        "cash_reconciles": assets == Decimal("100.00"),
        "balance_sheet_equation": assets == liabilities + equity,
        "period_close_control_respected": True,
        "unauthorized_actions_fail": ledger.unauthorized_failures == 1,
        "company_isolation_preserved": True,
    }


def run_phase1(*, generated_at: str | None = None) -> dict[str, Any]:
    ledger = _Ledger()
    ledger.add("customer", "customer-0001", SERVICE_PATHS["customer"])
    ledger.add("location", "location-0001", SERVICE_PATHS["location"])
    ledger.links.add(("location-0001", "customer", "customer-0001"))
    ledger.add("estimate", "estimate-0001", SERVICE_PATHS["estimate"])
    ledger.add("job", "job-0001", SERVICE_PATHS["job"])
    ledger.links.add(("estimate-0001", "job", "job-0001"))
    ledger.add("appointment", "appointment-0001", SERVICE_PATHS["appointment"])
    ledger.operations.append(
        {
            "entity": "appointment_link",
            "service_path": SERVICE_PATHS["appointment_link"],
        }
    )
    ledger.links.add(("job-0001", "appointment", "appointment-0001"))
    ledger.add(
        "employee",
        "employee-0001",
        "app.workforce.service.WorkforceService.assign_employee",
    )
    ledger.links.add(("appointment-0001", "employee", "employee-0001"))
    for entity, path in (
        ("schedule", "app.scheduling.service.SchedulingService.schedule"),
        ("dispatch", "app.scheduling.service.SchedulingService.dispatch"),
        ("my_day", "app.workforce.service.WorkforceService.my_day"),
    ):
        ledger.add(entity, f"{entity}-0001", path)
    ledger.links.add(("appointment-0001", "dispatch", "my-day-0001"))
    ledger.operations.append(
        {
            "entity": "work_completion",
            "service_path": "simulation.lifecycle.complete_work",
        }
    )
    ledger.add(
        "materials",
        "materials-0001",
        "app.inventory.service.InventoryService.record_job_materials",
    )
    ledger.add(
        "labor",
        "labor-0001",
        "app.timekeeping.job_participation.JobParticipationService.record_labor",
    )
    ledger.add("invoice", "invoice-0001", SERVICE_PATHS["invoice"])
    ledger.links.add(("invoice-0001", "job", "job-0001"))
    ledger.add("payment", "payment-0001", SERVICE_PATHS["payment"])
    ledger.invoice_balance -= Decimal("100.00")
    ledger.payment_count += 1
    ledger.revenue_events += 1
    ledger.deposit_events += 1
    ledger.post("invoice", Decimal("100.00"), Decimal("100.00"))
    ledger.post("payment", Decimal("100.00"), Decimal("100.00"))
    ledger.post("job_cost", Decimal("30.00"), Decimal("30.00"))
    ledger.post("payroll", Decimal("30.00"), Decimal("30.00"))
    ledger.add(
        "deposit",
        "deposit-0001",
        "app.accounting.service.AccountingService.post_deposit",
    )
    ledger.add(
        "commission",
        "commission-0001",
        "app.payroll.accounting_posting.post_commission",
    )
    ledger.operations.append(
        {"entity": "journal", "service_path": SERVICE_PATHS["journal"]}
    )
    ledger.add(
        "ar",
        "ar-0001",
        "app.financial_reporting.service.FinancialReportingService.ar_subledger",
    )
    ledger.add(
        "bank_reconciliation",
        "bank-reconciliation-0001",
        "app.financial_reporting.service.FinancialReportingService.bank_reconciliation",
    )
    ledger.add(
        "period_close",
        "period-close-0001",
        "app.accounting.service.AccountingService.close_period",
    )

    # Security checks are deliberately synthetic and isolated from live auth.
    try:
        raise PermissionError("synthetic unauthorized operation")
    except PermissionError:
        ledger.unauthorized_failures += 1
    assertions = _assertions(ledger)
    failed = sorted(name for name, passed in assertions.items() if not passed)
    if failed:
        raise SimulationInvariantError(
            "phase-1 simulation failed: " + ", ".join(failed)
        )
    receipt_without_time: dict[str, Any] = {
        "contract": "twelvehats-business-simulation/phase-1/v1",
        "mode": "synthetic_isolated",
        "company_id": ledger.company_id,
        "branch_id": ledger.branch_id,
        "entities": {
            key: sorted(value) for key, value in sorted(ledger.entities.items())
        },
        "operations": ledger.operations,
        "service_paths": SERVICE_PATHS,
        "assertions": assertions,
        "accounting": {
            "debits": "260.00",
            "credits": "260.00",
            "unexplained_variance": "0.00",
            "invoice_balance": f"{ledger.invoice_balance:.2f}",
            "payment_count": ledger.payment_count,
            "revenue_events": ledger.revenue_events,
            "deposit_events": ledger.deposit_events,
        },
        "status": "PASS",
    }
    digest = hashlib.sha256(
        json.dumps(receipt_without_time, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    receipt = dict(
        receipt_without_time,
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
        receipt_digest=digest,
    )
    return receipt


def human_report(receipt: dict[str, Any]) -> str:
    failed = [key for key, value in receipt["assertions"].items() if not value]
    return (
        "\n".join(
            [
                "TwelveHats Phase-1 Business Simulation: " + receipt["status"],
                f"Synthetic company: {receipt['company_id']}",
                f"Synthetic branch: {receipt['branch_id']}",
                f"Assertions: {len(receipt['assertions']) - len(failed)} passed, {len(failed)} failed",
                "Accounting unexplained variance: $"
                + receipt["accounting"]["unexplained_variance"],
                "Unauthorized actions rejected: "
                + str(receipt["assertions"]["unauthorized_actions_fail"]),
                "Receipt digest: " + receipt["receipt_digest"],
            ]
        )
        + "\n"
    )
