from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.errors import (
    AccountingConflict,
    AccountingNotFound,
    AccountingValidation,
)
from app.accounting.models import (
    Account,
    AccountingPeriod,
    AccountSourceIdentity,
    ChartVersion,
    ControlAccountAssignment,
    Journal,
    JournalApproval,
    JournalLine,
    PeriodTransition,
    PostingFailure,
    PostingSource,
)
from app.accounting.repository import AccountingRepository, accounting_repository
from app.accounting.schemas import (
    AccountCreate,
    ChartCreate,
    ControlAssignmentCreate,
    JournalCreate,
    PeriodCreate,
    PeriodTransitionRequest,
    ReversalCreate,
)
from app.accounting.types import (
    AccountClassification,
    ControlRole,
    JournalType,
    NormalBalance,
)
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, AuditService
from app.platform.permissions.authorization import AuthorizationContext


class LineLike(Protocol):
    debit: Decimal
    credit: Decimal
    branch_id: UUID | None


class AccountingService:
    def __init__(self, repository: AccountingRepository | None = None) -> None:
        self.repository = repository or accounting_repository

    @staticmethod
    def validate_lines(lines: tuple[LineLike, ...]) -> tuple[Decimal, Decimal]:
        if len(lines) < 2:
            raise AccountingValidation("A journal requires at least two lines")
        debits = Decimal(0)
        credits = Decimal(0)
        branches: set[UUID] = set()
        for line in lines:
            debit = Decimal(line.debit)
            credit = Decimal(line.credit)
            if not debit.is_finite() or not credit.is_finite():
                raise AccountingValidation("Journal amounts must be finite")
            if not ((debit > 0 and credit == 0) or (credit > 0 and debit == 0)):
                raise AccountingValidation(
                    "Each line requires exactly one positive debit or credit"
                )
            debits += debit
            credits += credit
            branch_id = line.branch_id
            if branch_id is not None:
                branches.add(branch_id)
        if debits <= 0 or debits != credits:
            raise AccountingValidation(
                "Journal debits and credits must be equal and non-zero"
            )
        if len(branches) > 1:
            raise AccountingValidation("Day-1 journals cannot span Branches")
        return debits, credits

    async def create_chart(
        self, session: AsyncSession, *, context: AuthorizationContext, data: ChartCreate
    ) -> ChartVersion:
        async with session.begin():
            active = await self.repository.active_chart(session, context.company.id)
            version = 1 if active is None else active.version + 1
            if active is not None:
                active.is_active = False
            chart = ChartVersion(
                company_id=context.company.id,
                version=version,
                name=data.name.strip(),
                currency=data.currency,
                accounting_basis=data.accounting_basis.strip(),
                source_checksum=data.source_checksum,
                effective_at=data.effective_at,
                is_active=True,
                approved_by_user_id=context.user.id,
            )
            session.add(chart)
            await session.flush()
            self._audit(
                session,
                context,
                "accounting.chart.created",
                "accounting_chart",
                chart.id,
            )
        return chart

    async def create_account(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        data: AccountCreate,
    ) -> Account:
        try:
            classification = AccountClassification(data.classification)
            normal = NormalBalance(data.normal_balance)
        except ValueError as error:
            raise AccountingValidation(
                "Account classification or normal balance is invalid"
            ) from error
        expected = (
            NormalBalance.DEBIT
            if classification
            in {AccountClassification.ASSET, AccountClassification.EXPENSE}
            else NormalBalance.CREDIT
        )
        if normal is not expected:
            raise AccountingValidation(
                "Normal balance conflicts with account classification"
            )
        async with session.begin():
            chart = await self.repository.active_chart(session, context.company.id)
            if chart is None or chart.id != data.chart_version_id:
                raise AccountingValidation(
                    "Account must belong to the active Company chart"
                )
            account = Account(
                company_id=context.company.id,
                chart_version_id=chart.id,
                code=data.code.strip(),
                name=data.name.strip(),
                classification=classification.value,
                normal_balance=normal.value,
                status="active",
                effective_from=data.effective_from,
            )
            session.add(account)
            await session.flush()
            session.add(
                AccountSourceIdentity(
                    company_id=context.company.id,
                    account_id=account.id,
                    source_system=data.source_system.strip(),
                    source_company_id=data.source_company_id.strip(),
                    source_account_id=data.source_account_id.strip(),
                    source_code=data.source_code.strip(),
                    source_type=data.source_type.strip(),
                    source_subtype=data.source_subtype.strip()
                    if data.source_subtype
                    else None,
                    source_checksum=data.source_checksum,
                )
            )
            self._audit(
                session,
                context,
                "accounting.account.created",
                "accounting_account",
                account.id,
            )
        return account

    async def assign_control(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        data: ControlAssignmentCreate,
    ) -> ControlAccountAssignment:
        try:
            role = ControlRole(data.control_role)
        except ValueError as error:
            raise AccountingValidation("Control role is invalid") from error
        async with session.begin():
            account = await self.repository.account(
                session, context.company.id, data.account_id
            )
            if account is None or account.status != "active":
                raise AccountingNotFound("Active account was not found")
            assignment = ControlAccountAssignment(
                company_id=context.company.id,
                account_id=account.id,
                control_role=role.value,
                qualifier=data.qualifier.strip(),
                effective_from=data.effective_from,
                approved_by_user_id=context.user.id,
            )
            session.add(assignment)
            await session.flush()
            self._audit(
                session,
                context,
                "accounting.control.assigned",
                "accounting_control_assignment",
                assignment.id,
            )
        return assignment

    async def create_period(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        data: PeriodCreate,
    ) -> AccountingPeriod:
        if data.start_date > data.end_date:
            raise AccountingValidation("Period start must not follow period end")
        async with session.begin():
            overlap = await session.scalar(
                select(AccountingPeriod.id).where(
                    AccountingPeriod.company_id == context.company.id,
                    AccountingPeriod.start_date <= data.end_date,
                    AccountingPeriod.end_date >= data.start_date,
                )
            )
            if overlap:
                raise AccountingConflict("Accounting periods cannot overlap")
            period = AccountingPeriod(
                company_id=context.company.id,
                name=data.name.strip(),
                start_date=data.start_date,
                end_date=data.end_date,
                status="open",
                version=1,
                created_by_user_id=context.user.id,
            )
            session.add(period)
            await session.flush()
            self._audit(
                session,
                context,
                "accounting.period.created",
                "accounting_period",
                period.id,
            )
        return period

    async def create_journal(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        data: JournalCreate,
        allow_control_override: bool = False,
    ) -> Journal:
        try:
            journal_type = JournalType(data.journal_type)
        except ValueError as error:
            raise AccountingValidation("Journal type is invalid") from error
        debits, credits = self.validate_lines(data.lines)
        async with session.begin():
            existing = await self.repository.journal_by_client_key(
                session, context.company.id, data.client_idempotency_key
            )
            if existing is not None:
                if existing.source_digest != data.source_digest:
                    raise AccountingConflict(
                        "Idempotency key was reused with different evidence"
                    )
                return existing
            source = await self.repository.posting_source(
                session,
                company_id=context.company.id,
                source_system=data.source_system,
                source_type=data.source_type,
                source_identity=data.source_identity,
                posting_rule_version=data.posting_rule_version,
            )
            if source is not None:
                if source.source_digest != data.source_digest:
                    raise AccountingConflict(
                        "Source identity digest conflicts with prior posting"
                    )
                existing_source_journal = await self.repository.journal(
                    session, context.company.id, source.journal_id
                )
                if existing_source_journal is None:
                    raise AccountingConflict("Posting source has no journal")
                return existing_source_journal
            chart = await self.repository.active_chart(session, context.company.id)
            if chart is None:
                raise AccountingValidation("An active Company chart is required")
            if data.currency != chart.currency:
                raise AccountingValidation(
                    "Journal currency must match Company functional currency"
                )
            period = await self.repository.period(
                session, context.company.id, data.period_id, lock=True
            )
            if period is None or not (
                period.start_date <= data.effective_date <= period.end_date
            ):
                raise AccountingValidation(
                    "Effective date must belong to the selected Company period"
                )
            if period.status not in {"open", "reopened"}:
                raise AccountingConflict(
                    "Selected accounting period does not accept posting"
                )
            account_ids = {line.account_id for line in data.lines}
            for account_id in account_ids:
                account = await self.repository.account(
                    session, context.company.id, account_id
                )
                if account is None or account.status != "active":
                    raise AccountingValidation(
                        "Every journal account must be active in the Company"
                    )
            for line in data.lines:
                if line.branch_id is not None and not context.can_access_branch(
                    line.branch_id
                ):
                    raise AccountingNotFound("Accounting Branch was not found")
            protected = account_ids & await self.repository.control_account_ids(
                session, context.company.id, data.effective_date
            )
            if protected:
                governed_override = (
                    journal_type in {JournalType.OPENING, JournalType.CORRECTIVE}
                    and allow_control_override
                    and data.evidence_digest is not None
                    and bool(data.control_override_reason)
                )
                mapped_automatic = journal_type is JournalType.AUTOMATED
                if not (governed_override or mapped_automatic):
                    raise AccountingValidation(
                        "Direct manual posting to a control account is prohibited"
                    )
            journal = Journal(
                company_id=context.company.id,
                period_id=period.id,
                journal_type=journal_type.value,
                status="draft",
                effective_date=data.effective_date,
                currency=data.currency,
                description=data.description.strip(),
                total_debits=debits,
                total_credits=credits,
                source_system=data.source_system.strip(),
                source_type=data.source_type.strip(),
                source_identity=data.source_identity.strip(),
                source_digest=data.source_digest,
                posting_rule_version=data.posting_rule_version.strip(),
                client_idempotency_key=data.client_idempotency_key.strip(),
                prepared_by_user_id=context.user.id,
                version=1,
            )
            session.add(journal)
            await session.flush()
            for ordinal, line in enumerate(data.lines, 1):
                session.add(
                    JournalLine(
                        company_id=context.company.id,
                        journal_id=journal.id,
                        ordinal=ordinal,
                        account_id=line.account_id,
                        branch_id=line.branch_id,
                        debit=line.debit,
                        credit=line.credit,
                        description=line.description.strip(),
                    )
                )
            session.add(
                PostingSource(
                    company_id=context.company.id,
                    journal_id=journal.id,
                    source_system=journal.source_system,
                    source_type=journal.source_type,
                    source_identity=journal.source_identity,
                    posting_rule_version=journal.posting_rule_version,
                    source_digest=journal.source_digest,
                    correlation_id=uuid4(),
                )
            )
            self._audit(
                session,
                context,
                "accounting.journal.created",
                "accounting_journal",
                journal.id,
            )
        return journal

    async def prepare_journal(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        journal_id: UUID,
        expected_version: int,
    ) -> Journal:
        return await self._journal_transition(
            session,
            context=context,
            journal_id=journal_id,
            expected_version=expected_version,
            source="draft",
            target="prepared",
            action="accounting.journal.prepared",
        )

    async def approve_journal(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        journal_id: UUID,
        expected_version: int,
        evidence_digest: str,
        reason: str,
    ) -> Journal:
        async with session.begin():
            journal = await self._locked_journal(
                session, context.company.id, journal_id, expected_version
            )
            if journal.status != "prepared":
                raise AccountingConflict("Only a prepared journal can be approved")
            if journal.prepared_by_user_id == context.user.id:
                raise AccountingConflict(
                    "Journal preparer and approver must be distinct"
                )
            journal.status = "approved"
            journal.approved_by_user_id = context.user.id
            journal.version += 1
            session.add(
                JournalApproval(
                    company_id=context.company.id,
                    journal_id=journal.id,
                    approval_type="opening_state"
                    if journal.journal_type == "opening"
                    else "journal",
                    approved_by_user_id=context.user.id,
                    evidence_digest=evidence_digest,
                    reason=reason.strip(),
                )
            )
            self._audit(
                session,
                context,
                "accounting.journal.approved",
                "accounting_journal",
                journal.id,
            )
        return journal

    async def post_journal(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        journal_id: UUID,
        expected_version: int,
    ) -> Journal:
        async with session.begin():
            journal = await self._locked_journal(
                session, context.company.id, journal_id, expected_version
            )
            if journal.status != "approved" or journal.approved_by_user_id is None:
                raise AccountingConflict("Only an approved journal can post")
            if journal.prepared_by_user_id == context.user.id:
                raise AccountingConflict(
                    "Journal preparer cannot post the same journal"
                )
            period = await self.repository.period(
                session, context.company.id, journal.period_id, lock=True
            )
            if period is None or period.status not in {"open", "reopened"}:
                raise AccountingConflict("Accounting period does not accept posting")
            lines = await self.repository.lines(session, context.company.id, journal.id)
            debits, credits = self.validate_lines(lines)
            if debits != journal.total_debits or credits != journal.total_credits:
                raise AccountingConflict("Journal evidence changed after preparation")
            journal.status = "posted"
            journal.posted_at = datetime.now(timezone.utc)
            journal.version += 1
            self._audit(
                session,
                context,
                "accounting.journal.posted",
                "accounting_journal",
                journal.id,
                {"total_debits": str(debits), "total_credits": str(credits)},
            )
            self._event(
                session,
                context,
                EventType.ACCOUNTING_JOURNAL_POSTED,
                "accounting_journal",
                journal.id,
                {
                    "effective_date": journal.effective_date.isoformat(),
                    "currency": journal.currency,
                    "total_debits": str(debits),
                    "total_credits": str(credits),
                },
            )
            if (
                journal.journal_type == "reversal"
                and journal.reversal_of_id is not None
            ):
                self._event(
                    session,
                    context,
                    EventType.ACCOUNTING_JOURNAL_REVERSED,
                    "accounting_journal",
                    journal.id,
                    {
                        "reversal_of_id": str(journal.reversal_of_id),
                        "effective_date": journal.effective_date.isoformat(),
                    },
                )
        return journal

    async def reverse_journal(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        journal_id: UUID,
        data: ReversalCreate,
    ) -> Journal:
        async with session.begin():
            original = await self.repository.journal(
                session, context.company.id, journal_id, lock=True
            )
            if original is None or original.status != "posted":
                raise AccountingNotFound("Posted journal was not found")
            existing = await session.scalar(
                select(Journal.id).where(
                    Journal.company_id == context.company.id,
                    Journal.reversal_of_id == original.id,
                    Journal.status == "posted",
                )
            )
            if existing:
                raise AccountingConflict("Journal already has a posted reversal")
            period = await self.repository.period(
                session, context.company.id, data.period_id, lock=True
            )
            if (
                period is None
                or period.status not in {"open", "reopened"}
                or not (period.start_date <= data.effective_date <= period.end_date)
            ):
                raise AccountingConflict("Reversal requires an open period")
            lines = await self.repository.lines(
                session, context.company.id, original.id
            )
            reversal = Journal(
                company_id=context.company.id,
                period_id=period.id,
                journal_type="reversal",
                status="prepared",
                effective_date=data.effective_date,
                currency=original.currency,
                description=data.reason.strip(),
                total_debits=original.total_credits,
                total_credits=original.total_debits,
                source_system="accounting",
                source_type="journal_reversal",
                source_identity=str(original.id),
                source_digest=data.source_digest,
                posting_rule_version="core-reversal-v1",
                client_idempotency_key=data.client_idempotency_key,
                prepared_by_user_id=context.user.id,
                reversal_of_id=original.id,
                version=1,
            )
            session.add(reversal)
            await session.flush()
            for line in lines:
                session.add(
                    JournalLine(
                        company_id=context.company.id,
                        journal_id=reversal.id,
                        ordinal=line.ordinal,
                        account_id=line.account_id,
                        branch_id=line.branch_id,
                        debit=line.credit,
                        credit=line.debit,
                        description=data.reason.strip(),
                    )
                )
            session.add(
                PostingSource(
                    company_id=context.company.id,
                    journal_id=reversal.id,
                    source_system=reversal.source_system,
                    source_type=reversal.source_type,
                    source_identity=reversal.source_identity,
                    posting_rule_version=reversal.posting_rule_version,
                    source_digest=reversal.source_digest,
                    correlation_id=uuid4(),
                )
            )
            self._audit(
                session,
                context,
                "accounting.journal.reversal_prepared",
                "accounting_journal",
                reversal.id,
                {
                    "reversal_of_id": str(original.id),
                    "evidence_digest": data.evidence_digest,
                },
            )
        return reversal

    async def begin_close(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        period_id: UUID,
        data: PeriodTransitionRequest,
    ) -> AccountingPeriod:
        async with session.begin():
            period = await self._locked_period(
                session, context.company.id, period_id, data.expected_version
            )
            if period.status not in {"open", "reopened"}:
                raise AccountingConflict("Only an accepting period can begin close")
            self._period_transition(
                session, period, "closing", context.user.id, data.reason
            )
            self._audit(
                session,
                context,
                "accounting.period.closing",
                "accounting_period",
                period.id,
            )
        return period

    async def close_period(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        period_id: UUID,
        data: PeriodTransitionRequest,
    ) -> AccountingPeriod:
        if not data.controls_reconciled or data.evidence_digest is None:
            raise AccountingValidation(
                "Control-account reconciliation evidence is required"
            )
        async with session.begin():
            period = await self._locked_period(
                session, context.company.id, period_id, data.expected_version
            )
            if period.status != "closing":
                raise AccountingConflict("Period must be closing before it can close")
            request = await session.scalar(
                select(PeriodTransition)
                .where(
                    PeriodTransition.company_id == context.company.id,
                    PeriodTransition.period_id == period.id,
                    PeriodTransition.to_status == "closing",
                    PeriodTransition.from_version == period.version - 1,
                )
                .with_for_update()
            )
            if request is None:
                raise AccountingConflict("Period close request evidence is missing")
            if request.requested_by_user_id == context.user.id:
                raise AccountingConflict(
                    "Close requester and Finance approver must be distinct"
                )
            request.approved_by_user_id = context.user.id
            request.evidence_digest = data.evidence_digest
            debits, credits = await self.repository.trial_balance(
                session, context.company.id, through=period.end_date
            )
            if debits != credits:
                raise AccountingConflict("Trial balance is not balanced")
            self._period_transition(
                session, period, "closed", context.user.id, data.reason
            )
            self._audit(
                session,
                context,
                "accounting.period.closed",
                "accounting_period",
                period.id,
            )
            self._event(
                session,
                context,
                EventType.ACCOUNTING_PERIOD_CLOSED,
                "accounting_period",
                period.id,
                {"end_date": period.end_date.isoformat()},
            )
        return period

    async def record_posting_failure(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        source_system: str,
        source_type: str,
        source_identity: str,
        source_digest: str,
        error_code: str,
        correlation_id: UUID,
        details: dict[str, object] | None = None,
    ) -> PostingFailure:
        """Persist bounded failure evidence only after the financial transaction rolled back."""
        async with session.begin():
            failure = PostingFailure(
                company_id=context.company.id,
                source_system=source_system.strip(),
                source_type=source_type.strip(),
                source_identity=source_identity.strip(),
                source_digest=source_digest,
                error_code=error_code.strip(),
                correlation_id=correlation_id,
                details=details or {},
            )
            session.add(failure)
            await session.flush()
            self._audit(
                session,
                context,
                "accounting.posting.failed",
                "accounting_posting_failure",
                failure.id,
                {
                    "error_code": failure.error_code,
                    "correlation_id": str(correlation_id),
                },
            )
            self._event(
                session,
                context,
                EventType.ACCOUNTING_POSTING_FAILED,
                "accounting_posting_failure",
                failure.id,
                {
                    "source_system": failure.source_system,
                    "source_type": failure.source_type,
                    "source_identity": failure.source_identity,
                    "error_code": failure.error_code,
                    "correlation_id": str(correlation_id),
                },
            )
        return failure

    async def request_reopen(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        period_id: UUID,
        data: PeriodTransitionRequest,
    ) -> PeriodTransition:
        async with session.begin():
            period = await self._locked_period(
                session, context.company.id, period_id, data.expected_version
            )
            if period.status != "closed":
                raise AccountingConflict("Only a closed period can be reopened")
            transition = PeriodTransition(
                company_id=context.company.id,
                period_id=period.id,
                from_status="closed",
                to_status="reopened",
                from_version=period.version,
                reason=data.reason.strip(),
                requested_by_user_id=context.user.id,
            )
            session.add(transition)
            await session.flush()
            self._audit(
                session,
                context,
                "accounting.period.reopen_requested",
                "accounting_period",
                period.id,
            )
        return transition

    async def approve_reopen(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        period_id: UUID,
        data: PeriodTransitionRequest,
    ) -> AccountingPeriod:
        if data.evidence_digest is None:
            raise AccountingValidation("Finance evidence is required")
        async with session.begin():
            period = await self._locked_period(
                session, context.company.id, period_id, data.expected_version
            )
            pending = await session.scalar(
                select(PeriodTransition)
                .where(
                    PeriodTransition.company_id == context.company.id,
                    PeriodTransition.period_id == period.id,
                    PeriodTransition.from_version == period.version,
                    PeriodTransition.from_status == "closed",
                    PeriodTransition.to_status == "reopened",
                    PeriodTransition.approved_by_user_id.is_(None),
                )
                .with_for_update()
            )
            if pending is None:
                raise AccountingNotFound("Pending reopen request was not found")
            if pending.requested_by_user_id == context.user.id:
                raise AccountingConflict(
                    "Reopen requester and Finance approver must be distinct"
                )
            pending.approved_by_user_id = context.user.id
            pending.evidence_digest = data.evidence_digest
            period.status = "reopened"
            period.version += 1
            period.updated_at = datetime.now(timezone.utc)
            self._audit(
                session,
                context,
                "accounting.period.reopened",
                "accounting_period",
                period.id,
            )
            self._event(
                session,
                context,
                EventType.ACCOUNTING_PERIOD_REOPENED,
                "accounting_period",
                period.id,
                {"reason": pending.reason},
            )
        return period

    async def _journal_transition(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        journal_id: UUID,
        expected_version: int,
        source: str,
        target: str,
        action: str,
    ) -> Journal:
        async with session.begin():
            journal = await self._locked_journal(
                session, context.company.id, journal_id, expected_version
            )
            if journal.status != source:
                raise AccountingConflict(f"Only a {source} journal can become {target}")
            journal.status = target
            journal.version += 1
            self._audit(session, context, action, "accounting_journal", journal.id)
        return journal

    async def _locked_journal(
        self,
        session: AsyncSession,
        company_id: UUID,
        journal_id: UUID,
        expected_version: int,
    ) -> Journal:
        journal = await self.repository.journal(
            session, company_id, journal_id, lock=True
        )
        if journal is None:
            raise AccountingNotFound("Accounting journal was not found")
        if journal.version != expected_version:
            raise AccountingConflict("Accounting journal version is stale")
        return journal

    async def _locked_period(
        self,
        session: AsyncSession,
        company_id: UUID,
        period_id: UUID,
        expected_version: int,
    ) -> AccountingPeriod:
        period = await self.repository.period(session, company_id, period_id, lock=True)
        if period is None:
            raise AccountingNotFound("Accounting period was not found")
        if period.version != expected_version:
            raise AccountingConflict("Accounting period version is stale")
        return period

    @staticmethod
    def _period_transition(
        session: AsyncSession,
        period: AccountingPeriod,
        target: str,
        actor: UUID,
        reason: str,
    ) -> None:
        session.add(
            PeriodTransition(
                company_id=period.company_id,
                period_id=period.id,
                from_status=period.status,
                to_status=target,
                from_version=period.version,
                reason=reason.strip(),
                requested_by_user_id=actor,
            )
        )
        period.status = target
        period.version += 1
        period.updated_at = datetime.now(timezone.utc)

    @staticmethod
    def _audit(
        session: AsyncSession,
        context: AuthorizationContext,
        action: str,
        resource_type: str,
        resource_id: UUID,
        details: dict[str, object] | None = None,
    ) -> None:
        AuditService.stage(
            session,
            AuditEntry(
                action=action,
                resource_type=resource_type,
                actor_user_id=context.user.id,
                company_id=context.company.id,
                resource_id=resource_id,
                details=details or {},
            ),
        )

    @staticmethod
    def _event(
        session: AsyncSession,
        context: AuthorizationContext,
        event_type: EventType,
        entity_type: str,
        entity_id: UUID,
        payload: dict[str, object],
    ) -> None:
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                company_id=context.company.id,
                user_id=context.user.id,
                payload=payload,
            ),
        )


accounting_service = AccountingService()
