from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.accounting.errors import AccountingConflict, AccountingValidation
from app.accounting.models import AccountingOperation, Journal
from app.accounting.operations import AccountingOperationService
from app.accounting.schemas import (
    AccountingOperationCreate,
    PeriodCreate,
    PeriodTransitionRequest,
)
from app.accounting.service import AccountingService
from app.financial_reporting.service import FinancialReportingService
from sqlalchemy import func, select

from tests.accounting.test_service_persistence import journal_command

pytest_plugins = ("tests.accounting.test_service_persistence",)


def command(
    company,
    branch,
    period,
    accounts,
    *,
    kind: str,
    reference: str,
    amount: str = "75.25",
    payload: dict[str, object],
    related_operation_id=None,
) -> AccountingOperationCreate:
    journal = journal_command(
        company, branch, period, accounts, key=f"operation-{uuid4()}"
    ).model_copy(
        update={
            "source_type": kind,
            "source_identity": reference,
            "description": f"Controlled {kind}",
            "lines": tuple(
                line.model_copy(
                    update={
                        "debit": Decimal(amount) if index == 0 else Decimal(0),
                        "credit": Decimal(amount) if index == 1 else Decimal(0),
                    }
                )
                for index, line in enumerate(
                    journal_command(
                        company, branch, period, accounts, key=f"lines-{uuid4()}"
                    ).lines
                )
            ),
        }
    )
    return AccountingOperationCreate(
        kind=kind,
        reference=reference,
        effective_date=date(2026, 8, 30),
        amount=Decimal(amount),
        currency="USD",
        related_operation_id=related_operation_id,
        payload=payload,
        provenance={
            "source": "operator_recorded",
            "evidence_reference": f"acceptance:{reference}",
            "classification": "VERIFIED",
        },
        journal=journal,
    )


@pytest.mark.asyncio
async def test_all_current_accounting_workflows_are_registered_and_ledger_bound(
    accounting_fixture,
) -> None:
    factory, company, branch, contexts, period, accounts = accounting_fixture
    service = AccountingOperationService()
    async with factory() as session:
        await service.create(
            session,
            context=contexts[0],
            data=command(
                company,
                branch,
                period,
                accounts,
                kind="undeposited_receipt",
                reference="payment-001",
                payload={
                    "payment_reference": "payment-001",
                    "customer_reference": "customer-001",
                },
            ),
        )
    async with factory() as session:
        card = await service.create(
            session,
            context=contexts[0],
            data=AccountingOperationCreate(
                kind="card_account",
                reference="card-001",
                effective_date=date(2026, 8, 30),
                amount=Decimal(0),
                currency="USD",
                payload={"masked_identity": "4242", "account_name": "Corporate card"},
                provenance={
                    "source": "operator_recorded",
                    "evidence_reference": "statement:card-001",
                    "classification": "VERIFIED",
                },
            ),
        )
    async with factory() as session:
        activation = await service.create(
            session,
            context=contexts[0],
            data=AccountingOperationCreate(
                kind="cutover_activation",
                reference="native-accounting-2026-11-14",
                effective_date=date(2026, 8, 30),
                amount=Decimal(0),
                currency="USD",
                payload={
                    "accepted_capabilities": ["ledger", "ar", "ap", "banking"],
                    "acceptance_evidence_reference": "acceptance:clean-beta",
                },
                provenance={
                    "source": "operator_recorded",
                    "evidence_reference": "acceptance:clean-beta",
                    "classification": "VERIFIED",
                },
            ),
        )
        assert activation.status == "active"
    async with factory() as session:
        asset = await service.create(
            session,
            context=contexts[0],
            data=command(
                company,
                branch,
                period,
                accounts,
                kind="fixed_asset",
                reference="asset-001",
                payload={
                    "placed_in_service_date": "2026-08-30",
                    "useful_life_months": 60,
                    "depreciation_method": "straight_line",
                },
            ),
        )

    cases = (
        (
            "deposit",
            "dep-001",
            {
                "payment_references": ["payment-001"],
                "bank_account_reference": "checking-001",
            },
            None,
        ),
        ("card_charge", "charge-001", {}, card.id),
        ("card_credit", "credit-001", {}, card.id),
        ("card_payment", "card-payment-001", {}, card.id),
        (
            "depreciation",
            "dep-expense-001",
            {"depreciation_period": "2026-08"},
            asset.id,
        ),
        (
            "tax_accrual",
            "tax-001",
            {"tax_type": "sales", "liability_period": "2026-08"},
            None,
        ),
        (
            "tax_payment",
            "tax-payment-001",
            {"tax_type": "sales", "payment_reference": "ach-001"},
            None,
        ),
        (
            "inventory_valuation",
            "valuation-001",
            {"valuation_method": "weighted_average"},
            None,
        ),
        (
            "inventory_purchase",
            "inv-purchase-001",
            {"inventory_item_id": "item-001", "quantity": "5"},
            None,
        ),
        (
            "inventory_usage",
            "inv-usage-001",
            {"inventory_item_id": "item-001", "quantity": "2", "job_id": "job-001"},
            None,
        ),
        (
            "inventory_adjustment",
            "inv-adjust-001",
            {"inventory_item_id": "item-001", "reason": "cycle count"},
            None,
        ),
        (
            "job_cost",
            "job-cost-001",
            {"job_id": "job-001", "cost_category": "materials"},
            None,
        ),
    )
    for kind, reference, payload, related in cases:
        async with factory() as session:
            row = await service.create(
                session,
                context=contexts[0],
                data=command(
                    company,
                    branch,
                    period,
                    accounts,
                    kind=kind,
                    reference=reference,
                    payload=payload,
                    related_operation_id=related,
                ),
            )
    with pytest.raises(AccountingValidation, match="related card_account"):
        async with factory() as session:
            await service.create(
                session,
                context=contexts[0],
                data=command(
                    company,
                    branch,
                    period,
                    accounts,
                    kind="card_charge",
                    reference=f"charge-{uuid4()}",
                    payload={},
                ),
            )
            assert row.journal_id is not None

    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count(AccountingOperation.id)).where(
                    AccountingOperation.company_id == company.id
                )
            )
            == len(cases) + 4
        )
        assert (
            await session.scalar(
                select(func.count(Journal.id)).where(Journal.company_id == company.id)
            )
            == len(cases) + 2
        )


@pytest.mark.asyncio
async def test_operation_replay_scope_and_validation_fail_closed(
    accounting_fixture,
) -> None:
    factory, company, branch, contexts, period, accounts = accounting_fixture
    service = AccountingOperationService()
    async with factory() as session:
        await service.create(
            session,
            context=contexts[0],
            data=command(
                company,
                branch,
                period,
                accounts,
                kind="undeposited_receipt",
                reference="payment-001",
                payload={
                    "payment_reference": "payment-001",
                    "customer_reference": "customer-001",
                },
            ),
        )
    data = command(
        company,
        branch,
        period,
        accounts,
        kind="deposit",
        reference=f"deposit-{uuid4()}",
        payload={
            "payment_references": ["payment-001"],
            "bank_account_reference": "checking-001",
        },
    )
    async with factory() as session:
        first = await service.create(session, context=contexts[0], data=data)
    async with factory() as session:
        replay = await service.create(session, context=contexts[0], data=data)
    assert replay.id == first.id

    async with factory() as session:
        with pytest.raises(AccountingConflict):
            await service.create(
                session,
                context=contexts[0],
                data=data.model_copy(
                    update={
                        "provenance": {
                            **data.provenance,
                            "evidence_reference": "conflicting-evidence",
                        }
                    }
                ),
            )
    duplicate_payment = command(
        company,
        branch,
        period,
        accounts,
        kind="deposit",
        reference=f"different-deposit-{uuid4()}",
        payload={
            "payment_references": ["payment-001"],
            "bank_account_reference": "checking-001",
        },
    )
    async with factory() as session:
        with pytest.raises(AccountingConflict, match="already assigned"):
            await service.create(session, context=contexts[0], data=duplicate_payment)


@pytest.mark.asyncio
async def test_database_backed_first_native_close_and_later_correction_pass(
    accounting_fixture,
) -> None:
    factory, company, branch, contexts, period, accounts = accounting_fixture
    operations = AccountingOperationService()
    ledger = AccountingService()
    reporting = FinancialReportingService()
    report_context = SimpleNamespace(
        company=company,
        user=contexts[0].user,
        can_access_branch=contexts[0].can_access_branch,
        has_permission=lambda _permission: True,
        branch_ids=frozenset({branch.id}),
    )
    journal_ids = []
    async with factory() as session:
        receipt = await operations.create(
            session,
            context=contexts[0],
            data=command(
                company,
                branch,
                period,
                accounts,
                kind="undeposited_receipt",
                reference="payment-close-001",
                payload={
                    "payment_reference": "payment-close-001",
                    "customer_reference": "customer-close-001",
                },
            ),
        )
        assert receipt.journal_id is not None
        journal_ids.append(receipt.journal_id)
    for kind, reference, payload in (
        (
            "deposit",
            f"close-deposit-{uuid4()}",
            {
                "payment_references": ["payment-close-001"],
                "bank_account_reference": "checking-close-001",
            },
        ),
        (
            "tax_accrual",
            f"close-tax-{uuid4()}",
            {"tax_type": "sales", "liability_period": "2026-08"},
        ),
        (
            "job_cost",
            f"close-job-cost-{uuid4()}",
            {"job_id": "job-close-001", "cost_category": "materials"},
        ),
    ):
        async with factory() as session:
            row = await operations.create(
                session,
                context=contexts[0],
                data=command(
                    company,
                    branch,
                    period,
                    accounts,
                    kind=kind,
                    reference=reference,
                    payload=payload,
                ),
            )
            assert row.journal_id is not None
            journal_ids.append(row.journal_id)

    for journal_id in journal_ids:
        async with factory() as session:
            draft = await session.get(Journal, journal_id)
            assert draft is not None
            version = draft.version
            await session.rollback()
            prepared = await ledger.prepare_journal(
                session,
                context=contexts[0],
                journal_id=journal_id,
                expected_version=version,
            )
        async with factory() as session:
            approved = await ledger.approve_journal(
                session,
                context=contexts[1],
                journal_id=journal_id,
                expected_version=prepared.version,
                evidence_digest="7" * 64,
                reason="Independent native-close acceptance approval",
            )
        async with factory() as session:
            posted = await ledger.post_journal(
                session,
                context=contexts[2],
                journal_id=journal_id,
                expected_version=approved.version,
            )
            assert posted.status == "posted"

    async with factory() as session:
        trial_balance = await reporting.trial_balance(
            session, context=report_context, as_of=period.end_date
        )
        profit_and_loss = await reporting.income_statement(
            session,
            context=report_context,
            start_date=period.start_date,
            end_date=period.end_date,
        )
        balance_sheet = await reporting.balance_sheet(
            session, context=report_context, as_of=period.end_date
        )
    assert trial_balance.total_debits == trial_balance.total_credits
    assert profit_and_loss.total_revenue == Decimal("301.0000")
    assert balance_sheet.total_assets == (
        balance_sheet.liabilities_equity_and_current_earnings
    )

    async with factory() as session:
        closing = await ledger.begin_close(
            session,
            context=contexts[0],
            period_id=period.id,
            data=PeriodTransitionRequest(
                expected_version=period.version,
                reason="Native acceptance reconciliation complete",
            ),
        )
    async with factory() as session:
        closed = await ledger.close_period(
            session,
            context=contexts[1],
            period_id=period.id,
            data=PeriodTransitionRequest(
                expected_version=closing.version,
                reason="Independent Finance close acceptance",
                controls_reconciled=True,
                evidence_digest="8" * 64,
            ),
        )
    assert closed.status == "closed"

    closed_command = command(
        company,
        branch,
        period,
        accounts,
        kind="tax_payment",
        reference=f"closed-rejection-{uuid4()}",
        payload={"tax_type": "sales", "payment_reference": "closed-ach"},
    ).journal
    assert closed_command is not None
    async with factory() as session:
        with pytest.raises(AccountingConflict, match="does not accept posting"):
            await ledger.create_journal(
                session, context=contexts[0], data=closed_command
            )

    async with factory() as session:
        correction_period = await ledger.create_period(
            session,
            context=contexts[0],
            data=PeriodCreate(
                name="September 2026",
                start_date=date(2026, 9, 1),
                end_date=date(2026, 9, 30),
            ),
        )
    correction = closed_command.model_copy(
        update={
            "period_id": correction_period.id,
            "effective_date": date(2026, 9, 1),
            "journal_type": "corrective",
            "source_type": "approved_legacy_correction",
            "source_identity": f"lia-decision-{uuid4()}",
            "source_digest": "9" * 64,
            "client_idempotency_key": f"correction-{uuid4()}",
            "evidence_digest": "a" * 64,
            "control_override_reason": "Approved additive reconciliation correction",
        }
    )
    async with factory() as session:
        corrected = await ledger.create_journal(
            session,
            context=contexts[0],
            data=correction,
            allow_control_override=True,
        )
    assert corrected.period_id == correction_period.id
    assert corrected.journal_type == "corrective"
