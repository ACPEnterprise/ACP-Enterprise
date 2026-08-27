from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.errors import AccountingValidation
from app.accounting.posting.contracts import PostingOutcome, PostingReceipt
from app.accounts_payable.contracts import PostingReceiptSpec as APPostingReceipt
from app.accounts_payable.service import AccountsPayableService
from app.invoicing.contracts import PostingReceiptFact as InvoicePostingReceipt
from app.invoicing.service import InvoiceService
from app.payments.contracts import PostingReceiptFact as PaymentPostingReceipt
from app.payments.service import PaymentService


class DomainPostingReceiptSink:
    """Routes an Accounting outcome to the source-owned idempotent receipt seam."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        invoices: InvoiceService,
        payments: PaymentService,
        accounts_payable: AccountsPayableService,
    ) -> None:
        self.session = session
        self.invoices = invoices
        self.payments = payments
        self.accounts_payable = accounts_payable

    async def deliver(self, receipt: PostingReceipt) -> None:
        if receipt.status is not PostingOutcome.POSTED:
            raise AccountingValidation(
                "Only posted outcomes may use source posted-receipt seams"
            )
        if (
            receipt.journal_id is None
            or receipt.journal_version is None
            or receipt.posted_at is None
        ):
            raise AccountingValidation("Posted outcome is missing journal evidence")
        if receipt.source_type == "invoice":
            if receipt.branch_id is None:
                raise AccountingValidation("Invoice receipt requires Branch evidence")
            await self.invoices.record_posting_receipt(
                self.session,
                InvoicePostingReceipt(
                    company_id=receipt.company_id,
                    branch_id=receipt.branch_id,
                    invoice_id=receipt.source_id,
                    source_event_id=receipt.source_event_id,
                    journal_id=receipt.journal_id,
                    journal_version=receipt.journal_version,
                    policy_version=receipt.policy_version,
                    status=receipt.status.value,
                    effective_date=receipt.effective_date,
                    posted_at=receipt.posted_at,
                ),
            )
            return
        if receipt.source_type.startswith("payment"):
            await self.payments.record_posting_receipt(
                self.session,
                PaymentPostingReceipt(
                    company_id=receipt.company_id,
                    source_event_id=receipt.source_event_id,
                    journal_id=receipt.journal_id,
                    journal_version=receipt.journal_version,
                    policy_version=receipt.policy_version,
                    status=receipt.status.value,
                    effective_date=receipt.effective_date,
                    posted_at=receipt.posted_at,
                ),
            )
            return
        if receipt.source_type.startswith("accounts_payable") or receipt.source_type in {
            "bill",
            "vendor_credit",
            "disbursement",
        }:
            await self.accounts_payable.record_posting_receipt(
                self.session,
                APPostingReceipt(
                    company_id=receipt.company_id,
                    source_event_id=receipt.source_event_id,
                    source_type=receipt.source_type,
                    source_id=receipt.source_id,
                    journal_id=receipt.journal_id,
                    journal_version=receipt.journal_version,
                    mapping_version=receipt.policy_version,
                    status=receipt.status.value,
                    effective_date=receipt.effective_date,
                ),
            )
            return
        raise AccountingValidation("Source domain has no posting-receipt seam")
