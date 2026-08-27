from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.errors import AccountingConflict, AccountingValidation
from app.accounting.posting.contracts import (
    PostingFact,
    PostingOutcome,
    PostingReceipt,
    PostingReceiptSink,
    PostingRule,
    PostingSide,
)
from app.accounting.posting.rules import PostingRuleRegistry
from app.accounting.schemas import JournalCreate, JournalLineCreate
from app.accounting.service import AccountingService
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AccountingPermission


class AutomatedPostingService:
    """Resumable, idempotent posting through Accounting Core's governed lifecycle."""

    def __init__(
        self,
        *,
        rules: PostingRuleRegistry,
        accounting: AccountingService | None = None,
    ) -> None:
        self.rules = rules
        self.accounting = accounting or AccountingService()

    @staticmethod
    def _validate_fact(fact: PostingFact) -> None:
        if fact.schema_version != "1.0":
            raise AccountingValidation("Financial fact schema version is unsupported")
        if len(fact.evidence_digest) != 64 or any(
            character not in "0123456789abcdef" for character in fact.evidence_digest
        ):
            raise AccountingValidation("Financial fact evidence digest is invalid")
        if not fact.source_type.strip() or not fact.event_type.strip():
            raise AccountingValidation("Financial fact identity is required")
        if not fact.components:
            raise AccountingValidation("Financial fact components are required")
        for amount in fact.components.values():
            value = Decimal(amount)
            if not value.is_finite() or value <= 0:
                raise AccountingValidation(
                    "Financial fact components must be finite and positive"
                )

    @staticmethod
    def _journal_create(
        fact: PostingFact, rule: PostingRule, period_id: UUID
    ) -> JournalCreate:
        mapped = {leg.component for leg in rule.legs}
        if mapped != set(fact.components):
            raise AccountingValidation(
                "Posting rule must map every fact component exactly"
            )
        lines = tuple(
            JournalLineCreate(
                account_id=leg.account_id,
                branch_id=fact.branch_id,
                debit=Decimal(fact.components[leg.component])
                if leg.side is PostingSide.DEBIT
                else Decimal(0),
                credit=Decimal(fact.components[leg.component])
                if leg.side is PostingSide.CREDIT
                else Decimal(0),
                description=leg.description,
            )
            for leg in rule.legs
        )
        AccountingService.validate_lines(lines)
        return JournalCreate(
            period_id=period_id,
            journal_type="automated",
            effective_date=fact.effective_date,
            currency=fact.currency,
            description=f"{fact.event_type} {fact.source_id}",
            source_system="acp_enterprise",
            source_type=fact.source_type,
            source_identity=fact.source_identity,
            source_digest=fact.canonical_digest(),
            posting_rule_version=rule.version,
            client_idempotency_key=f"posting:{fact.source_event_id}:{rule.version}",
            evidence_digest=fact.evidence_digest,
            lines=lines,
        )

    async def post(
        self,
        session: AsyncSession,
        *,
        fact: PostingFact,
        period_id: UUID,
        preparer: AuthorizationContext,
        approver: AuthorizationContext,
        poster: AuthorizationContext,
        receipt_sink: PostingReceiptSink | None = None,
    ) -> PostingReceipt:
        self._validate_fact(fact)
        if any(context.company.id != fact.company_id for context in (preparer, approver, poster)):
            raise AccountingValidation("Posting actors must belong to the fact Company")
        if fact.branch_id is not None and not all(
            context.can_access_branch(fact.branch_id)
            for context in (preparer, approver, poster)
        ):
            raise AccountingValidation("Posting actors must have fact Branch access")
        if len({preparer.user.id, approver.user.id, poster.user.id}) != 3:
            raise AccountingConflict("Automated posting requires three distinct actors")
        required = (
            (preparer, AccountingPermission.JOURNAL_PREPARE),
            (approver, AccountingPermission.FINANCE_APPROVE),
            (poster, AccountingPermission.JOURNAL_POST),
        )
        if any(not context.has_permission(permission) for context, permission in required):
            raise AccountingValidation("Posting actor lacks the required Accounting permission")

        rule = self.rules.resolve(fact)
        data = self._journal_create(fact, rule, period_id)
        journal = await self.accounting.create_journal(
            session, context=preparer, data=data
        )
        if journal.status == "draft":
            journal = await self.accounting.prepare_journal(
                session,
                context=preparer,
                journal_id=journal.id,
                expected_version=journal.version,
            )
        if journal.status == "prepared":
            journal = await self.accounting.approve_journal(
                session,
                context=approver,
                journal_id=journal.id,
                expected_version=journal.version,
                evidence_digest=fact.evidence_digest,
                reason=f"Approved posting rule {rule.version}",
            )
        if journal.status == "approved":
            journal = await self.accounting.post_journal(
                session,
                context=poster,
                journal_id=journal.id,
                expected_version=journal.version,
            )
        if journal.status != "posted" or journal.posted_at is None:
            raise AccountingConflict("Accounting journal did not reach posted state")
        receipt = PostingReceipt(
            company_id=fact.company_id,
            branch_id=fact.branch_id,
            source_event_id=fact.source_event_id,
            source_type=fact.source_type,
            source_id=fact.source_id,
            journal_id=journal.id,
            journal_version=journal.version,
            policy_version=rule.version,
            status=PostingOutcome.POSTED,
            effective_date=fact.effective_date,
            posted_at=journal.posted_at,
        )
        if receipt_sink is not None:
            await receipt_sink.deliver(receipt)
        return receipt

    async def reconciliation_required(
        self,
        session: AsyncSession,
        *,
        fact: PostingFact,
        context: AuthorizationContext,
        error_code: str,
        correlation_id: UUID,
    ) -> PostingReceipt:
        """Record bounded evidence after a failed posting transaction."""
        self._validate_fact(fact)
        if context.company.id != fact.company_id:
            raise AccountingValidation("Failure evidence must remain Company scoped")
        await self.accounting.record_posting_failure(
            session,
            context=context,
            source_system="acp_enterprise",
            source_type=fact.source_type,
            source_identity=fact.source_identity,
            source_digest=fact.canonical_digest(),
            error_code=error_code,
            correlation_id=correlation_id,
            details={"event_type": fact.event_type, "schema_version": fact.schema_version},
        )
        return PostingReceipt(
            company_id=fact.company_id,
            branch_id=fact.branch_id,
            source_event_id=fact.source_event_id,
            source_type=fact.source_type,
            source_id=fact.source_id,
            journal_id=None,
            journal_version=None,
            policy_version="unresolved",
            status=PostingOutcome.RECONCILIATION_REQUIRED,
            effective_date=fact.effective_date,
            posted_at=None,
            failure_reason=error_code,
        )
