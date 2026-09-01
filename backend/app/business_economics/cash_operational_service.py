"""Read-only owner projection across Economics, native AR/AP, and cash readiness."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.models import ChartVersion
from app.accounts_payable.models import Disbursement, VendorBill
from app.invoicing.models import Invoice
from app.jobs.models import Job
from app.payments.models import Deposit, PaymentReceipt
from app.platform.permissions.authorization import AuthorizationContext

from .cash_operational import CONTRACT_VERSION, recognition_contract
from .workspace import EconomicsWorkspaceService


class CashOperationalEconomicsService:
    async def overview(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        period_start: date,
        period_end: date,
    ) -> dict[str, object]:
        if period_end < period_start:
            raise ValueError("period end cannot precede period start")
        economics = await EconomicsWorkspaceService().overview(
            session,
            context=context,
            period_start=period_start,
            period_end=period_end,
        )
        branch_id = context.active_branch.id if context.active_branch else None
        company_id = context.company.id
        currency = economics.get("currency")
        start_at = datetime.combine(period_start, time.min, tzinfo=timezone.utc)
        end_at = datetime.combine(
            period_end + timedelta(days=1), time.min, tzinfo=timezone.utc
        )

        completed_open_query = (
            select(
                func.count(Invoice.id),
                func.coalesce(func.sum(Invoice.open_amount), 0),
                func.count(func.distinct(Invoice.currency)),
                func.min(Invoice.currency),
            )
            .join(
                Job,
                (Job.company_id == Invoice.company_id) & (Job.id == Invoice.job_id),
            )
            .where(
                Invoice.company_id == company_id,
                Invoice.status.in_(("issued", "partially_paid", "adjusted", "paid")),
                Invoice.open_amount > 0,
                Job.status == "completed",
                Job.completed_at >= start_at,
                Job.completed_at < end_at,
            )
        )
        receipt_query = select(
            func.count(PaymentReceipt.id),
            func.coalesce(func.sum(PaymentReceipt.captured_amount), 0),
            func.count(func.distinct(PaymentReceipt.currency)),
            func.min(PaymentReceipt.currency),
        ).where(
            PaymentReceipt.company_id == company_id,
            PaymentReceipt.captured_at >= start_at,
            PaymentReceipt.captured_at < end_at,
        )
        deposit_query = select(
            func.count(Deposit.id),
            func.coalesce(func.sum(Deposit.gross_amount), 0),
            func.count(func.distinct(Deposit.currency)),
            func.min(Deposit.currency),
        ).where(
            Deposit.company_id == company_id,
            Deposit.created_at >= start_at,
            Deposit.created_at < end_at,
        )
        ap_query = select(
            func.count(VendorBill.id),
            func.coalesce(func.sum(VendorBill.open_amount), 0),
            func.count(func.distinct(VendorBill.currency)),
            func.min(VendorBill.currency),
        ).where(
            VendorBill.company_id == company_id,
            VendorBill.status.in_(
                ("approved", "posted", "partially_paid", "paid", "credited")
            ),
            VendorBill.open_amount > 0,
            VendorBill.bill_date <= period_end,
        )
        disbursement_query = select(
            func.count(Disbursement.id),
            func.coalesce(func.sum(Disbursement.amount), 0),
            func.count(func.distinct(Disbursement.currency)),
            func.min(Disbursement.currency),
        ).where(
            Disbursement.company_id == company_id,
            Disbursement.status == "recorded",
            Disbursement.effective_date >= period_start,
            Disbursement.effective_date <= period_end,
        )
        if branch_id is not None:
            completed_open_query = completed_open_query.where(
                Invoice.branch_id == branch_id
            )
            receipt_query = receipt_query.where(PaymentReceipt.branch_id == branch_id)
            deposit_query = deposit_query.where(Deposit.branch_id == branch_id)
            ap_query = ap_query.where(VendorBill.branch_id == branch_id)
            disbursement_query = disbursement_query.where(
                Disbursement.branch_id == branch_id
            )

        completed_open = (await session.execute(completed_open_query)).one()
        receipts = (await session.execute(receipt_query)).one()
        deposits = (await session.execute(deposit_query)).one()
        vendor_open = (await session.execute(ap_query)).one()
        disbursements = (await session.execute(disbursement_query)).one()
        chart = await session.scalar(
            select(ChartVersion).where(
                ChartVersion.company_id == company_id, ChartVersion.is_active.is_(True)
            )
        )

        operational_rows = (
            completed_open,
            receipts,
            deposits,
            vendor_open,
            disbursements,
        )
        observed_currencies = {str(row[3]) for row in operational_rows if row[3]}
        operational_conflict = any(int(row[2]) > 1 for row in operational_rows) or (
            len(observed_currencies) > 1
        )
        if isinstance(currency, str) and observed_currencies not in (set(), {currency}):
            operational_conflict = True
        operational_currency = (
            currency
            if isinstance(currency, str)
            else next(iter(observed_currencies), None)
        )
        operational = {
            "state": "CONFLICTING" if operational_conflict else "AVAILABLE",
            "currency": operational_currency,
            "completed_jobs_with_open_invoice_count": int(completed_open[0]),
            "completed_work_open_commercial_balance_minor": self._minor(
                completed_open[1]
            ),
            "payment_receipt_count": int(receipts[0]),
            "payment_receipt_assertion_minor": self._minor(receipts[1]),
            "deposit_batch_count": int(deposits[0]),
            "deposit_batch_gross_minor": self._minor(deposits[1]),
            "open_vendor_obligation_count": int(vendor_open[0]),
            "open_vendor_obligation_minor": self._minor(vendor_open[1]),
            "vendor_disbursement_count": int(disbursements[0]),
            "vendor_disbursement_minor": self._minor(disbursements[1]),
            "limitations": [
                "Open balances are operational obligations, not cash-basis income or expense.",
                "Payment receipts and deposit batches are not Accounting recognition.",
                "Vendor payment timing does not establish Job material cost.",
                "No collection or aging threshold is inferred.",
            ],
        }
        accounting = {
            "state": (
                "EXTERNAL_GATE"
                if chart is None
                else "AVAILABLE_BASIS_ONLY"
                if chart.accounting_basis.strip().lower() == "cash"
                else "CONFLICTING"
            ),
            "basis": chart.accounting_basis if chart else None,
            "currency": chart.currency if chart else None,
            "recognized_income_minor": None,
            "recognized_expense_minor": None,
            "limitation": "Accounting totals require admitted native Accounting reports; operational payment, deposit, Invoice, and AP evidence is not substituted.",
        }
        earned = {
            "state": str(economics["quality_state"]).upper(),
            "currency": currency,
            "earned_revenue_minor": self._optional_minor(
                economics.get("totals"), "revenue"
            ),
            "job_contribution_minor": self._optional_minor(
                economics.get("totals"), "gross_profit"
            ),
            "job_count": economics["job_count"],
            "complete_job_count": economics["complete_job_count"],
            "limitation": "Earned-work Economics does not become cash-basis Accounting recognition or proof of collection.",
        }
        canonical: dict[str, Any] = {
            "version": CONTRACT_VERSION,
            "company_id": str(company_id),
            "branch_id": str(branch_id) if branch_id else None,
            "period": {
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
            },
            "work_period": earned,
            "operational_current_state": operational,
            "cash_accounting_period": accounting,
        }
        canonical["owner_question_battery"] = self._owner_answers(
            earned=earned, operational=operational, accounting=accounting
        )
        canonical["beacon_readiness"] = [
            {
                "condition": "open_customer_obligation",
                "state": "POLICY_REQUIRED",
                "evidence_available": int(completed_open[0]) > 0,
                "reason": "No owner-approved attention threshold is inferred.",
            },
            {
                "condition": "open_vendor_obligation",
                "state": "POLICY_REQUIRED",
                "evidence_available": int(vendor_open[0]) > 0,
                "reason": "No owner-approved attention threshold is inferred.",
            },
            {
                "condition": "economic_accounting_timing_divergence",
                "state": "SOURCE_REQUIRED",
                "evidence_available": accounting["recognized_income_minor"] is not None,
                "reason": "Admitted Accounting cash totals are required before comparison.",
            },
        ]
        return {
            **canonical,
            "recognition_contract": recognition_contract(),
            "projection_digest": hashlib.sha256(
                json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "mutation_authority": "none",
        }

    @staticmethod
    def _minor(value: Decimal | int) -> int:
        return int(Decimal(value) * 100)

    @classmethod
    def _optional_minor(cls, totals: object, key: str) -> int | None:
        if not isinstance(totals, dict):
            return None
        value = totals.get(key)
        return int(value) if isinstance(value, int) else None

    @staticmethod
    def _owner_answers(
        *,
        earned: Mapping[str, object],
        operational: Mapping[str, object],
        accounting: Mapping[str, object],
    ) -> list[dict[str, object]]:
        missing: list[str] = []
        if earned["state"] != "COMPLETE":
            missing.append("complete_admitted_earned_work_evidence")
        if operational["state"] != "AVAILABLE":
            missing.append("currency_consistent_operational_ar_ap_evidence")
        if accounting["recognized_income_minor"] is None:
            missing.append("admitted_cash_basis_accounting_report")
        return [
            {
                "question": "How much work did we perform?",
                "answer_minor": earned["earned_revenue_minor"],
                "truth_plane": "business_economics",
                "state": earned["state"],
            },
            {
                "question": "How much cash did we collect?",
                "answer_minor": accounting["recognized_income_minor"],
                "truth_plane": "accounting_cash",
                "state": accounting["state"],
                "limitation": "Payment receipts and deposits are shown separately and are never substituted for Accounting cash truth.",
            },
            {
                "question": "How much completed work remains unpaid?",
                "answer_minor": operational[
                    "completed_work_open_commercial_balance_minor"
                ],
                "truth_plane": "operational_ar_ap",
                "state": operational["state"],
            },
            {
                "question": "Why are performed work and collected cash different?",
                "answer": "Work, Invoice, open receivable, payment assertion, settlement, deposit, and Accounting recognition are separate admitted events and may occur in different periods.",
                "state": "DETERMINISTIC_CAPABLE",
            },
            {
                "question": "How much Vendor obligation remains unsettled?",
                "answer_minor": operational["open_vendor_obligation_minor"],
                "truth_plane": "operational_ar_ap",
                "state": operational["state"],
            },
            {
                "question": "Why could cash decline while Job profitability was positive?",
                "answer": "Positive Job contribution and cash movement use different evidence and periods. A conclusion requires admitted Accounting cash evidence plus operational settlement timing.",
                "state": accounting["state"],
                "causality": "not_inferred",
            },
            {
                "question": "Which evidence is missing before this answer is complete?",
                "items": missing,
                "state": "COMPLETE" if not missing else "PARTIAL",
            },
        ]
