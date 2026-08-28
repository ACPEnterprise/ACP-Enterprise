from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.accounting.errors import AccountingConflict, AccountingValidation
from app.accounting.service import AccountingService
from app.accounting_migration import (
    AccountTargetBinding,
    BranchTargetBinding,
    NativeOpeningStateService,
    OpeningComponent,
    OpeningPolicyPrerequisites,
    ReconciliationState,
)
from app.financial_reporting.repository import PeriodFact, ReportingContextFact
from app.financial_reporting.service import FinancialReportingService
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AccountingPermission
from tests.accounting_migration.test_opening_state_runtime import (
    BRANCH_ID,
    COMPANY_ID,
    _manifest,
    _plan,
    _validator,
)
from tests.financial_reporting.test_financial_reporting_service import (
    FakeRepository as ReportingRepository,
)
from tests.financial_reporting.test_financial_reporting_service import (
    _line as reporting_line,
)


def _context(user_id: UUID, permissions: set[str]) -> AuthorizationContext:
    company_id = UUID(COMPANY_ID)
    branch_id = UUID(BRANCH_ID)
    return cast(
        AuthorizationContext,
        SimpleNamespace(
            user=SimpleNamespace(id=user_id),
            company=SimpleNamespace(id=company_id),
            can_access_branch=lambda candidate: candidate == branch_id,
            has_permission=lambda candidate: candidate in permissions,
        ),
    )


def _policy() -> OpeningPolicyPrerequisites:
    return OpeningPolicyPrerequisites(
        definition_version="acc-mig-1-v1",
        cutover_date=date(2030, 1, 1),
        period_id=uuid4(),
        currency="USD",
        opening_balance_acceptance_reference="finance:acceptance:synthetic-1",
        reconciliation_precedence_reference="finance:precedence:synthetic-1",
        retained_earnings_treatment_reference="finance:retained-earnings:synthetic-1",
        opening_equity_treatment_reference="finance:opening-equity:synthetic-1",
        unresolved_ar_ap_treatment_reference="finance:ar-ap:synthetic-1",
        unresolved_bank_cash_treatment_reference="finance:bank-cash:synthetic-1",
        materiality_policy_reference="finance:materiality:synthetic-1",
        approval_evidence_digest="a" * 64,
    )


class _Repository:
    def __init__(self, *, accounts: dict[UUID, object]) -> None:
        self.accounts = accounts

    async def active_chart(self, session: object, company_id: UUID) -> object:
        return SimpleNamespace(currency="USD", accounting_basis="accrual")

    async def period(self, session: object, company_id: UUID, period_id: UUID) -> object:
        return SimpleNamespace(
            start_date=date(2030, 1, 1),
            end_date=date(2030, 1, 31),
            status="open",
        )

    async def account(self, session: object, company_id: UUID, account_id: UUID) -> object | None:
        return self.accounts.get(account_id)


def _inputs(tmp_path: Path) -> tuple[Any, Any, tuple[AccountTargetBinding, ...], tuple[BranchTargetBinding, ...]]:
    package = _validator().validate(_manifest(tmp_path))
    cash_id, equity_id = uuid4(), uuid4()
    accounts = {
        cash_id: SimpleNamespace(status="active", classification="asset"),
        equity_id: SimpleNamespace(status="active", classification="equity"),
    }
    bindings = (
        AccountTargetBinding("synthetic-cash", cash_id, OpeningComponent.OTHER_BALANCE_SHEET, "finance:map:cash"),
        AccountTargetBinding("synthetic-equity", equity_id, OpeningComponent.OPENING_EQUITY, "finance:map:equity"),
    )
    return package, accounts, bindings, (BranchTargetBinding(BRANCH_ID, UUID(BRANCH_ID)),)


@pytest.mark.asyncio
async def test_reconciles_to_native_accounts_with_complete_provenance(tmp_path: Path) -> None:
    package, accounts, bindings, branches = _inputs(tmp_path)
    session = SimpleNamespace(scalar=AsyncMock(return_value="opening_balance"))
    accounting = cast(Any, AsyncMock(spec=AccountingService))
    service = NativeOpeningStateService(accounting=accounting, repository=cast(Any, _Repository(accounts=accounts)))
    preparer = _context(uuid4(), {AccountingPermission.JOURNAL_PREPARE, AccountingPermission.RECONCILE})
    approver = _context(uuid4(), {AccountingPermission.FINANCE_APPROVE})

    result = await service.reconcile(
        cast(Any, session), package=package, plan=_plan(package), policy=_policy(),
        account_bindings=bindings, branch_bindings=branches,
        preparer=preparer, finance_approver=approver,
    )

    assert result.state is ReconciliationState.APPROVED_ELIGIBLE
    assert result.eligible_for_posting
    assert len(result.canonical_package_digest) == len(result.reconciliation_digest) == 64
    assert all(line.state is ReconciliationState.RECONCILED for line in result.lines)
    assert all(line.difference == 0 for line in result.lines)
    assert all(line.source_authority_classification for line in result.lines)
    accounting.record_posting_failure.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_evidence_is_not_coerced_to_zero(tmp_path: Path) -> None:
    package, accounts, bindings, branches = _inputs(tmp_path)
    accounting = cast(Any, AsyncMock(spec=AccountingService))
    service = NativeOpeningStateService(accounting=accounting, repository=cast(Any, _Repository(accounts=accounts)))
    preparer = _context(uuid4(), {AccountingPermission.JOURNAL_PREPARE, AccountingPermission.RECONCILE})
    approver = _context(uuid4(), {AccountingPermission.FINANCE_APPROVE})

    result = await service.reconcile(
        cast(Any, SimpleNamespace(scalar=AsyncMock(return_value="opening_balance"), rollback=AsyncMock())),
        package=package, plan=_plan(package), policy=_policy(),
        account_bindings=bindings[:1], branch_bindings=branches,
        preparer=preparer, finance_approver=approver,
    )

    missing = result.lines[1]
    assert result.state is ReconciliationState.MISSING_EVIDENCE
    assert not result.eligible_for_posting
    assert missing.expected_credit is None
    assert missing.actual_prepared_credit is None
    assert missing.difference is None
    accounting.record_posting_failure.assert_awaited_once()


@pytest.mark.asyncio
async def test_conflicting_mapping_and_unresolved_policy_fail_closed(tmp_path: Path) -> None:
    package, accounts, bindings, branches = _inputs(tmp_path)
    accounting = cast(Any, AsyncMock(spec=AccountingService))
    service = NativeOpeningStateService(accounting=accounting, repository=cast(Any, _Repository(accounts=accounts)))
    preparer = _context(uuid4(), {AccountingPermission.JOURNAL_PREPARE, AccountingPermission.RECONCILE})
    approver = _context(uuid4(), {AccountingPermission.FINANCE_APPROVE})
    session = cast(Any, SimpleNamespace(scalar=AsyncMock(return_value="opening_balance"), rollback=AsyncMock()))

    conflict = await service.reconcile(
        session, package=package, plan=_plan(package), policy=_policy(),
        account_bindings=bindings + (bindings[0],), branch_bindings=branches,
        preparer=preparer, finance_approver=approver,
    )
    assert conflict.state is ReconciliationState.CONFLICTING
    assert conflict.lines[0].difference is None
    accounting.record_posting_failure.assert_awaited_once()

    with pytest.raises(AccountingValidation, match="policy reference"):
        await service.reconcile(
            session, package=package, plan=_plan(package),
            policy=replace(_policy(), materiality_policy_reference=""),
            account_bindings=bindings, branch_bindings=branches,
            preparer=preparer, finance_approver=approver,
        )


@pytest.mark.asyncio
async def test_posts_only_through_native_lifecycle_and_replay_is_idempotent(tmp_path: Path) -> None:
    package, accounts, bindings, branches = _inputs(tmp_path)
    accounting = cast(Any, AsyncMock(spec=AccountingService))
    repository = cast(Any, _Repository(accounts=accounts))
    service = NativeOpeningStateService(accounting=accounting, repository=repository)
    preparer = _context(uuid4(), {AccountingPermission.JOURNAL_PREPARE, AccountingPermission.RECONCILE})
    approver = _context(uuid4(), {AccountingPermission.FINANCE_APPROVE})
    poster = _context(uuid4(), {AccountingPermission.JOURNAL_POST})
    reconciliation = await service.reconcile(
        cast(Any, SimpleNamespace(scalar=AsyncMock(return_value="opening_balance"))),
        package=package, plan=_plan(package), policy=_policy(),
        account_bindings=bindings, branch_bindings=branches,
        preparer=preparer, finance_approver=approver,
    )
    posted = SimpleNamespace(id=uuid4(), status="posted", version=4, posted_at=datetime.now(timezone.utc))
    accounting.create_journal.return_value = posted

    receipt = await service.post(
        cast(Any, SimpleNamespace(rollback=AsyncMock())), reconciliation=reconciliation,
        preparer=preparer, finance_approver=approver, poster=poster,
    )

    data = accounting.create_journal.call_args.kwargs["data"]
    assert receipt.status == "posted"
    assert data.journal_type == "opening"
    assert data.source_system == "accounting_migration"
    assert data.source_digest == reconciliation.reconciliation_digest
    assert data.client_idempotency_key.startswith("opening:")
    assert accounting.create_journal.call_args.kwargs["allow_control_override"] is True
    accounting.prepare_journal.assert_not_awaited()
    accounting.approve_journal.assert_not_awaited()
    accounting.post_journal.assert_not_awaited()

    same_actor = replace(reconciliation, approved_by_user_id=preparer.user.id)
    with pytest.raises(AccountingConflict, match="three distinct"):
        await service.post(
            cast(Any, SimpleNamespace(rollback=AsyncMock())), reconciliation=same_actor,
            preparer=preparer, finance_approver=preparer, poster=poster,
        )


@pytest.mark.asyncio
async def test_posted_opening_fact_is_consumed_by_acc_rpt_deterministically(tmp_path: Path) -> None:
    package, accounts, bindings, branches = _inputs(tmp_path)
    accounting = cast(Any, AsyncMock(spec=AccountingService))
    service = NativeOpeningStateService(
        accounting=accounting,
        repository=cast(Any, _Repository(accounts=accounts)),
    )
    preparer = _context(uuid4(), {AccountingPermission.JOURNAL_PREPARE, AccountingPermission.RECONCILE})
    approver = _context(uuid4(), {AccountingPermission.FINANCE_APPROVE})
    poster = _context(uuid4(), {AccountingPermission.JOURNAL_POST})
    policy = _policy()
    reconciliation = await service.reconcile(
        cast(Any, SimpleNamespace(scalar=AsyncMock(return_value="opening_balance"))),
        package=package, plan=_plan(package), policy=policy,
        account_bindings=bindings, branch_bindings=branches,
        preparer=preparer, finance_approver=approver,
    )
    journal_id = uuid4()
    posted_at = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)
    accounting.create_journal.return_value = SimpleNamespace(
        id=journal_id, status="posted", version=4, posted_at=posted_at
    )
    receipt = await service.post(
        cast(Any, SimpleNamespace(rollback=AsyncMock())),
        reconciliation=reconciliation, preparer=preparer,
        finance_approver=approver, poster=poster,
    )

    company_id, branch_id = UUID(COMPANY_ID), UUID(BRANCH_ID)
    debit, credit = reconciliation.lines
    facts = (
        replace(
            reporting_line(
                company_id=company_id, branch_id=branch_id, journal_id=journal_id,
                ordinal=1, account_id=cast(UUID, debit.target_account_id), code="1000",
                classification="asset", normal_balance="debit",
                effective_date=policy.cutover_date, debit=cast(Any, debit.actual_prepared_debit),
                journal_total=cast(Any, debit.actual_prepared_debit),
            ),
            journal_type="opening", source_system="accounting_migration",
            source_type="opening_state", source_identity=f"package:{package.package_id}",
            source_digest=receipt.reconciliation_digest,
            account_effective_from=date(2030, 1, 1),
            period_id=policy.period_id, period_name="2030-01",
            period_start_date=date(2030, 1, 1), period_end_date=date(2030, 1, 31),
        ),
        replace(
            reporting_line(
                company_id=company_id, branch_id=branch_id, journal_id=journal_id,
                ordinal=2, account_id=cast(UUID, credit.target_account_id), code="3000",
                classification="equity", normal_balance="credit",
                effective_date=policy.cutover_date, credit=cast(Any, credit.actual_prepared_credit),
                journal_total=cast(Any, credit.actual_prepared_credit),
            ),
            journal_type="opening", source_system="accounting_migration",
            source_type="opening_state", source_identity=f"package:{package.package_id}",
            source_digest=receipt.reconciliation_digest,
            account_effective_from=date(2030, 1, 1),
            period_id=policy.period_id, period_name="2030-01",
            period_start_date=date(2030, 1, 1), period_end_date=date(2030, 1, 31),
        ),
    )
    reporting = FinancialReportingService(
        cast(
            Any,
            ReportingRepository(
                ReportingContextFact(company_id, "America/New_York", "USD", "accrual", 1),
                PeriodFact(policy.period_id, "2030-01", date(2030, 1, 1), date(2030, 1, 31), "open", 1),
                facts,
            ),
        )
    )
    report_context = _context(uuid4(), {AccountingPermission.REPORT_READ})
    first = await reporting.trial_balance(
        cast(Any, object()), context=report_context, as_of=policy.cutover_date
    )
    second = await reporting.trial_balance(
        cast(Any, object()), context=report_context, as_of=policy.cutover_date
    )
    balance_sheet = await reporting.balance_sheet(
        cast(Any, object()), context=report_context, as_of=policy.cutover_date
    )
    assert first.total_debits == first.total_credits
    assert first.manifest.checksum == second.manifest.checksum
    assert first.manifest.ledger_cutoff == second.manifest.ledger_cutoff
    assert balance_sheet.total_assets == balance_sheet.liabilities_equity_and_current_earnings
    assert facts[0].source_digest == reconciliation.reconciliation_digest
