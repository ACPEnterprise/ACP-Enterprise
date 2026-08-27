import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.financial_reporting.contracts import (
    AccountBalanceRow,
    BalanceSheetResult,
    GeneralLedgerResult,
    GeneralLedgerRow,
    IncomeStatementResult,
    ReportManifest,
    ReportQuality,
    ReportScope,
    StatementRow,
    TrialBalanceResult,
)
from app.financial_reporting.errors import (
    ReportingIntegrityError,
    ReportingNotFound,
    ReportingRequestError,
)
from app.financial_reporting.repository import (
    FinancialReportingRepository,
    LedgerLineFact,
    PeriodFact,
    ReportingContextFact,
    financial_reporting_repository,
)
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AccountingPermission

DEFINITION_VERSION = "acc-rpt-1.0"
ZERO = Decimal(0)


@dataclass(slots=True)
class _Balance:
    account_id: UUID
    code: str
    name: str
    classification: str
    normal_balance: str
    status: str
    beginning: Decimal = ZERO
    debits: Decimal = ZERO
    credits: Decimal = ZERO

    @property
    def ending(self) -> Decimal:
        return self.beginning + self.debits - self.credits


class FinancialReportingService:
    def __init__(
        self, repository: FinancialReportingRepository | None = None
    ) -> None:
        self.repository = repository or financial_reporting_repository

    async def trial_balance(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        as_of: date,
        start_date: date | None = None,
        branch_id: UUID | None = None,
        period_id: UUID | None = None,
    ) -> TrialBalanceResult:
        report_context, period, lines = await self._facts(
            session,
            context=context,
            as_of=as_of,
            start_date=start_date,
            branch_id=branch_id,
            period_id=period_id,
        )
        balances = self._balances(lines, start_date=start_date)
        rows = tuple(self._account_row(row) for row in balances)
        total_beginning = sum((row.beginning_balance for row in rows), ZERO)
        total_debits = sum((row.debits for row in rows), ZERO)
        total_credits = sum((row.credits for row in rows), ZERO)
        total_ending = sum((row.ending_balance for row in rows), ZERO)
        if total_debits != total_credits or total_ending != ZERO:
            raise ReportingIntegrityError("trial_balance_not_balanced")
        return TrialBalanceResult(
            scope=self._scope(context, branch_id),
            manifest=self._manifest(
                "trial_balance",
                report_context,
                lines,
                context,
                start_date,
                as_of,
                branch_id,
                period,
            ),
            quality=ReportQuality(),
            rows=rows,
            total_beginning_balance=total_beginning,
            total_debits=total_debits,
            total_credits=total_credits,
            total_ending_balance=total_ending,
        )

    async def balance_sheet(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        as_of: date,
        branch_id: UUID | None = None,
        period_id: UUID | None = None,
    ) -> BalanceSheetResult:
        report_context, period, lines = await self._facts(
            session,
            context=context,
            as_of=as_of,
            start_date=None,
            branch_id=branch_id,
            period_id=period_id,
        )
        balances = self._balances(lines, start_date=None)
        assets = self._statement_rows(balances, "asset")
        liabilities = self._statement_rows(balances, "liability")
        equity = self._statement_rows(balances, "equity")
        revenue = self._statement_rows(balances, "revenue")
        expenses = self._statement_rows(balances, "expense")
        total_assets = sum((row.amount for row in assets), ZERO)
        total_liabilities = sum((row.amount for row in liabilities), ZERO)
        total_equity = sum((row.amount for row in equity), ZERO)
        current_earnings = sum((row.amount for row in revenue), ZERO) - sum(
            (row.amount for row in expenses), ZERO
        )
        right_side = total_liabilities + total_equity + current_earnings
        if total_assets != right_side:
            raise ReportingIntegrityError("balance_sheet_equation_failed")
        return BalanceSheetResult(
            scope=self._scope(context, branch_id),
            manifest=self._manifest(
                "balance_sheet",
                report_context,
                lines,
                context,
                None,
                as_of,
                branch_id,
                period,
            ),
            quality=ReportQuality(),
            assets=assets,
            liabilities=liabilities,
            equity=equity,
            total_assets=total_assets,
            total_liabilities=total_liabilities,
            total_equity=total_equity,
            current_earnings=current_earnings,
            liabilities_equity_and_current_earnings=right_side,
        )

    async def income_statement(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        start_date: date,
        end_date: date,
        branch_id: UUID | None = None,
        period_id: UUID | None = None,
    ) -> IncomeStatementResult:
        report_context, period, lines = await self._facts(
            session,
            context=context,
            as_of=end_date,
            start_date=start_date,
            branch_id=branch_id,
            period_id=period_id,
        )
        balances = self._balances(lines, start_date=start_date)
        revenue = self._statement_rows(balances, "revenue", activity_only=True)
        expenses = self._statement_rows(balances, "expense", activity_only=True)
        total_revenue = sum((row.amount for row in revenue), ZERO)
        total_expenses = sum((row.amount for row in expenses), ZERO)
        return IncomeStatementResult(
            scope=self._scope(context, branch_id),
            manifest=self._manifest(
                "income_statement",
                report_context,
                lines,
                context,
                start_date,
                end_date,
                branch_id,
                period,
            ),
            quality=ReportQuality(reconciliation="not_applicable"),
            revenue=revenue,
            expenses=expenses,
            total_revenue=total_revenue,
            total_expenses=total_expenses,
            net_income=total_revenue - total_expenses,
        )

    async def general_ledger(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        start_date: date,
        end_date: date,
        branch_id: UUID | None = None,
        period_id: UUID | None = None,
        account_id: UUID | None = None,
    ) -> GeneralLedgerResult:
        report_context, period, all_lines = await self._facts(
            session,
            context=context,
            as_of=end_date,
            start_date=start_date,
            branch_id=branch_id,
            period_id=period_id,
        )
        account_lines = tuple(
            line
            for line in all_lines
            if account_id is None or line.account_id == account_id
        )
        if account_id is not None and not account_lines:
            raise ReportingNotFound("Accounting account was not found in report scope")
        beginning = sum(
            (
                line.debit - line.credit
                for line in account_lines
                if line.effective_date < start_date
            ),
            ZERO,
        )
        running: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
        for line in account_lines:
            if line.effective_date < start_date:
                running[line.account_id] += line.debit - line.credit
        detail: list[GeneralLedgerRow] = []
        for line in account_lines:
            if line.effective_date < start_date:
                continue
            running[line.account_id] += line.debit - line.credit
            detail.append(self._detail_row(line, running[line.account_id]))
        rows = tuple(detail)
        total_debits = sum((row.debit for row in rows), ZERO)
        total_credits = sum((row.credit for row in rows), ZERO)
        return GeneralLedgerResult(
            scope=self._scope(context, branch_id),
            manifest=self._manifest(
                "general_ledger",
                report_context,
                account_lines,
                context,
                start_date,
                end_date,
                branch_id,
                period,
            ),
            quality=ReportQuality(reconciliation="not_applicable"),
            account_id=account_id,
            beginning_balance=beginning,
            total_debits=total_debits,
            total_credits=total_credits,
            ending_balance=beginning + total_debits - total_credits,
            rows=rows,
        )

    async def _facts(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        as_of: date,
        start_date: date | None,
        branch_id: UUID | None,
        period_id: UUID | None,
    ) -> tuple[ReportingContextFact, PeriodFact | None, tuple[LedgerLineFact, ...]]:
        if not context.has_permission(AccountingPermission.REPORT_READ):
            raise ReportingNotFound("Financial report was not found")
        if start_date is not None and start_date > as_of:
            raise ReportingRequestError("Report start date must not follow end date")
        if branch_id is not None and not context.can_access_branch(branch_id):
            raise ReportingNotFound("Financial report Branch was not found")
        report_context = await self.repository.context(session, context.company.id)
        if report_context is None:
            raise ReportingNotFound("Active Accounting reporting context was not found")
        period = None
        if period_id is not None:
            period = await self.repository.period(session, context.company.id, period_id)
            if period is None:
                raise ReportingNotFound("Accounting period was not found")
            expected_start = period.start_date if start_date is not None else None
            if period.end_date != as_of or expected_start != start_date:
                raise ReportingRequestError(
                    "Period report dates must equal Accounting period boundaries"
                )
        lines = await self.repository.ledger_lines(
            session,
            company_id=context.company.id,
            as_of=as_of,
            branch_id=None,
        )
        self._validate_integrity(lines, report_context)
        if branch_id is not None:
            lines = tuple(line for line in lines if line.branch_id == branch_id)
        return report_context, period, lines

    @staticmethod
    def _validate_integrity(
        lines: tuple[LedgerLineFact, ...], context: ReportingContextFact
    ) -> None:
        journals: dict[UUID, list[LedgerLineFact]] = defaultdict(list)
        source_digests: dict[tuple[str, str, str], str] = {}
        for line in lines:
            if line.company_id != context.company_id:
                raise ReportingIntegrityError("cross_company_ledger_evidence")
            if line.journal_status != "posted" or line.posted_at is None:
                raise ReportingIntegrityError("invalid_posted_journal_state")
            if line.approved_by_user_id is None or line.correlation_id is None:
                raise ReportingIntegrityError("missing_posting_provenance")
            if line.currency != context.currency:
                raise ReportingIntegrityError("contradictory_functional_currency")
            if line.classification not in {
                "asset",
                "liability",
                "equity",
                "revenue",
                "expense",
            } or line.normal_balance not in {"debit", "credit"}:
                raise ReportingIntegrityError("unknown_account_classification")
            if line.effective_date < line.account_effective_from or (
                line.account_effective_to is not None
                and line.effective_date > line.account_effective_to
            ):
                raise ReportingIntegrityError("account_lifecycle_conflict")
            if not (
                line.period_start_date
                <= line.effective_date
                <= line.period_end_date
            ):
                raise ReportingIntegrityError("journal_period_conflict")
            if not (
                (line.debit > ZERO and line.credit == ZERO)
                or (line.credit > ZERO and line.debit == ZERO)
            ):
                raise ReportingIntegrityError("invalid_journal_line_state")
            source_key = (
                line.source_system,
                line.source_type,
                line.source_identity,
            )
            prior_digest = source_digests.setdefault(source_key, line.source_digest)
            if prior_digest != line.source_digest and line.journal_type != "reversal":
                raise ReportingIntegrityError("contradictory_source_evidence")
            journals[line.journal_id].append(line)
        for journal_lines in journals.values():
            debits = sum((line.debit for line in journal_lines), ZERO)
            credits = sum((line.credit for line in journal_lines), ZERO)
            first = journal_lines[0]
            if (
                len(journal_lines) < 2
                or debits != credits
                or debits != first.journal_total_debits
                or credits != first.journal_total_credits
            ):
                raise ReportingIntegrityError("journal_balance_evidence_conflict")

    @staticmethod
    def _balances(
        lines: Iterable[LedgerLineFact], *, start_date: date | None
    ) -> tuple[_Balance, ...]:
        balances: dict[UUID, _Balance] = {}
        for line in lines:
            balance = balances.setdefault(
                line.account_id,
                _Balance(
                    account_id=line.account_id,
                    code=line.account_code,
                    name=line.account_name,
                    classification=line.classification,
                    normal_balance=line.normal_balance,
                    status=line.account_status,
                ),
            )
            if start_date is not None and line.effective_date < start_date:
                balance.beginning += line.debit - line.credit
            else:
                balance.debits += line.debit
                balance.credits += line.credit
        return tuple(sorted(balances.values(), key=lambda row: (row.code, row.account_id)))

    @staticmethod
    def _account_row(balance: _Balance) -> AccountBalanceRow:
        display = (
            balance.ending
            if balance.normal_balance == "debit"
            else -balance.ending
        )
        return AccountBalanceRow(
            account_id=balance.account_id,
            code=balance.code,
            name=balance.name,
            classification=balance.classification,
            normal_balance=balance.normal_balance,
            status=balance.status,
            hierarchy_path=(balance.code,),
            beginning_balance=balance.beginning,
            debits=balance.debits,
            credits=balance.credits,
            ending_balance=balance.ending,
            display_balance=display,
        )

    @classmethod
    def _statement_rows(
        cls,
        balances: tuple[_Balance, ...],
        classification: str,
        *,
        activity_only: bool = False,
    ) -> tuple[StatementRow, ...]:
        rows = []
        for balance in balances:
            if balance.classification != classification:
                continue
            canonical = (
                balance.debits - balance.credits
                if activity_only
                else balance.ending
            )
            amount = canonical if balance.normal_balance == "debit" else -canonical
            rows.append(
                StatementRow(
                    account_id=balance.account_id,
                    code=balance.code,
                    name=balance.name,
                    classification=classification,
                    amount=amount,
                    hierarchy_path=(balance.code,),
                )
            )
        return tuple(rows)

    @staticmethod
    def _detail_row(line: LedgerLineFact, running: Decimal) -> GeneralLedgerRow:
        if line.posted_at is None or line.approved_by_user_id is None or line.correlation_id is None:
            raise ReportingIntegrityError("missing_general_ledger_provenance")
        return GeneralLedgerRow(
            line_id=line.line_id,
            journal_id=line.journal_id,
            ordinal=line.ordinal,
            account_id=line.account_id,
            account_code=line.account_code,
            account_name=line.account_name,
            branch_id=line.branch_id,
            period_id=line.period_id,
            period_name=line.period_name,
            effective_date=line.effective_date,
            posted_at=line.posted_at,
            journal_type=line.journal_type,
            journal_description=line.journal_description,
            line_description=line.line_description,
            debit=line.debit,
            credit=line.credit,
            running_balance=running,
            prepared_by_user_id=line.prepared_by_user_id,
            approved_by_user_id=line.approved_by_user_id,
            source_system=line.source_system,
            source_type=line.source_type,
            source_identity=line.source_identity,
            source_digest=line.source_digest,
            posting_rule_version=line.posting_rule_version,
            correlation_id=line.correlation_id,
            reversal_of_id=line.reversal_of_id,
        )

    @staticmethod
    def _scope(context: AuthorizationContext, branch_id: UUID | None) -> ReportScope:
        return ReportScope(
            company_id=context.company.id,
            branch_id=branch_id,
            scope_label="Company" if branch_id is None else "Branch workpaper",
            includes_company_unassigned=branch_id is None,
        )

    @classmethod
    def _manifest(
        cls,
        report_name: str,
        report_context: ReportingContextFact,
        lines: Iterable[LedgerLineFact],
        context: AuthorizationContext,
        start_date: date | None,
        as_of: date,
        branch_id: UUID | None,
        period: PeriodFact | None,
    ) -> ReportManifest:
        ordered = tuple(lines)
        cutoff_document = [
            {
                "journal_id": str(line.journal_id),
                "journal_version": line.journal_version,
                "line_id": str(line.line_id),
                "source_digest": line.source_digest,
            }
            for line in ordered
        ]
        ledger_cutoff = cls._digest(cutoff_document)
        canonical = {
            "accounting_basis": report_context.accounting_basis,
            "as_of_date": as_of.isoformat(),
            "branch_id": str(branch_id) if branch_id else None,
            "company_id": str(report_context.company_id),
            "currency": report_context.currency,
            "definition_version": DEFINITION_VERSION,
            "ledger_cutoff": ledger_cutoff,
            "period_id": str(period.id) if period else None,
            "report_name": report_name,
            "start_date": start_date.isoformat() if start_date else None,
        }
        return ReportManifest(
            report_name=report_name,
            definition_version=DEFINITION_VERSION,
            company_id=report_context.company_id,
            branch_id=branch_id,
            currency=report_context.currency,
            accounting_basis=report_context.accounting_basis,
            timezone=report_context.company_timezone,
            start_date=start_date,
            as_of_date=as_of,
            period_id=period.id if period else None,
            period_status=period.status if period else None,
            ledger_cutoff=ledger_cutoff,
            contributing_line_count=len(ordered),
            generated_at=datetime.now(timezone.utc),
            requested_by_user_id=context.user.id,
            checksum=cls._digest(canonical),
        )

    @staticmethod
    def _digest(value: object) -> str:
        return sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


financial_reporting_service = FinancialReportingService()
