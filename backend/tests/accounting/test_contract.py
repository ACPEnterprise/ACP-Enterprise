from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.accounting.errors import AccountingValidation
from app.accounting.models import Journal, JournalLine
from app.accounting.schemas import JournalLineCreate
from app.accounting.service import AccountingService
from app.accounting.types import ControlRole, JournalStatus, PeriodStatus
from app.core.database import Base
from app.events.types import EventType
from app.platform.permissions.catalog import permission_catalog
from app.platform.permissions.codes import AccountingPermission


@dataclass(frozen=True)
class Line:
    debit: Decimal
    credit: Decimal
    branch_id: UUID | None = None


def test_balanced_double_entry_is_accepted() -> None:
    debit = Line(Decimal("125.25"), Decimal(0))
    credit = Line(Decimal(0), Decimal("125.25"))
    assert AccountingService.validate_lines((debit, credit)) == (
        Decimal("125.25"),
        Decimal("125.25"),
    )


@pytest.mark.parametrize(
    "lines,message",
    [
        ((Line(Decimal(1), Decimal(0)),), "at least two"),
        ((Line(Decimal(1), Decimal(0)), Line(Decimal(0), Decimal(2))), "equal"),
        (
            (Line(Decimal(1), Decimal(1)), Line(Decimal(0), Decimal(1))),
            "exactly one",
        ),
        (
            (Line(Decimal(0), Decimal(0)), Line(Decimal(0), Decimal(0))),
            "exactly one",
        ),
    ],
)
def test_invalid_double_entry_fails_closed(
    lines: tuple[Line, ...], message: str
) -> None:
    with pytest.raises(AccountingValidation, match=message):
        AccountingService.validate_lines(lines)


def test_manual_cross_branch_entry_fails_closed() -> None:
    with pytest.raises(AccountingValidation, match="cannot span Branches"):
        AccountingService.validate_lines(
            (
                Line(Decimal(1), Decimal(0), uuid4()),
                Line(Decimal(0), Decimal(1), uuid4()),
            )
        )


def test_non_finite_and_negative_money_are_rejected() -> None:
    with pytest.raises(ValidationError):
        JournalLineCreate(
            account_id=uuid4(),
            debit=Decimal("NaN"),
            credit=Decimal(0),
            description="invalid",
        )
    with pytest.raises(ValidationError):
        JournalLineCreate(
            account_id=uuid4(),
            debit=Decimal(-1),
            credit=Decimal(0),
            description="invalid",
        )


def test_accounting_permission_vocabulary_is_exact_and_catalogued() -> None:
    assert AccountingPermission.ALL == {
        "COMPANY_ACCOUNTING_READ",
        "COMPANY_ACCOUNTING_JOURNAL_PREPARE",
        "COMPANY_ACCOUNTING_JOURNAL_POST",
        "COMPANY_ACCOUNTING_PERIOD_MANAGE",
        "COMPANY_ACCOUNTING_JOURNAL_REVERSE",
        "COMPANY_ACCOUNTING_RECONCILE",
        "COMPANY_ACCOUNTING_FINANCE_APPROVE",
        "COMPANY_ACCOUNTING_OPENING_STATE_APPROVE",
        "COMPANY_ACCOUNTING_REPORT_READ",
    }
    definitions = {item.code: item for item in permission_catalog.definitions}
    assert AccountingPermission.ALL <= definitions.keys()
    assert all(definitions[code].reserved for code in AccountingPermission.ALL)
    permission_catalog.validate()


def test_accounting_business_event_vocabulary_is_exact() -> None:
    assert {
        EventType.ACCOUNTING_JOURNAL_POSTED.value,
        EventType.ACCOUNTING_JOURNAL_REVERSED.value,
        EventType.ACCOUNTING_PERIOD_CLOSED.value,
        EventType.ACCOUNTING_PERIOD_REOPENED.value,
        EventType.ACCOUNTING_POSTING_FAILED.value,
    } == {
        "accounting.journal_posted",
        "accounting.journal_reversed",
        "accounting.period_closed",
        "accounting.period_reopened",
        "accounting.posting_failed",
    }


def test_core_state_and_control_vocabularies_are_frozen() -> None:
    assert {item.value for item in PeriodStatus} == {
        "open",
        "closing",
        "closed",
        "reopened",
    }
    assert {item.value for item in JournalStatus} == {
        "draft",
        "prepared",
        "approved",
        "posted",
        "rejected",
        "cancelled",
    }
    assert len(ControlRole) == 9


def test_exact_eleven_table_boundary_and_posting_constraints() -> None:
    names = {
        table.name
        for table in Base.metadata.sorted_tables
        if table.name.startswith("accounting_")
    }
    assert names == {
        "accounting_chart_versions",
        "accounting_accounts",
        "accounting_account_source_identities",
        "accounting_control_account_assignments",
        "accounting_periods",
        "accounting_period_transitions",
        "accounting_journals",
        "accounting_journal_lines",
        "accounting_journal_approvals",
        "accounting_posting_sources",
        "accounting_posting_failures",
    }
    journal_constraints = {item.name for item in Journal.__table__.constraints}
    line_constraints = {item.name for item in JournalLine.__table__.constraints}
    assert "ck_accounting_journal_posted_balanced" in journal_constraints
    assert "ck_accounting_line_one_side" in line_constraints
    assert "uq_accounting_journal_reversal" in journal_constraints
