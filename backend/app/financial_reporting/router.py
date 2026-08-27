from collections.abc import Awaitable, Callable
from datetime import date
from hashlib import sha256
from typing import Annotated, TypeVar
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.service import accounting_service
from app.database.session import get_database_session
from app.financial_reporting.contracts import (
    BalanceSheetResult,
    GeneralLedgerResult,
    IncomeStatementResult,
    TrialBalanceResult,
)
from app.financial_reporting.errors import (
    ReportingIntegrityError,
    ReportingNotFound,
    ReportingRequestError,
)
from app.financial_reporting.service import financial_reporting_service
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AccountingPermission
from app.platform.permissions.dependencies import require_permission

router = APIRouter(prefix="/api/v1/accounting/reports", tags=["Financial Reporting"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
ReportContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(AccountingPermission.REPORT_READ)),
]
ResultT = TypeVar("ResultT", bound=BaseModel)


async def _generate(
    *,
    session: AsyncSession,
    context: AuthorizationContext,
    report_name: str,
    request_identity: str,
    operation: Callable[[], Awaitable[ResultT]],
) -> ResultT:
    try:
        return await operation()
    except ReportingNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ReportingRequestError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ReportingIntegrityError as error:
        await session.rollback()
        digest = sha256(request_identity.encode()).hexdigest()
        await accounting_service.record_posting_failure(
            session,
            context=context,
            source_system="financial_reporting",
            source_type=report_name,
            source_identity=request_identity[:200],
            source_digest=digest,
            error_code=str(error),
            correlation_id=uuid4(),
            details={"report_name": report_name, "definition_version": "acc-rpt-1.0"},
        )
        raise HTTPException(
            status_code=409,
            detail="Ledger integrity prevents authoritative report generation",
        ) from error


@router.get("/trial-balance", response_model=TrialBalanceResult)
async def trial_balance(
    as_of: date,
    context: ReportContext,
    session: DatabaseSession,
    start_date: date | None = None,
    branch_id: UUID | None = None,
    period_id: UUID | None = None,
) -> TrialBalanceResult:
    identity = f"trial_balance:{context.company.id}:{branch_id}:{start_date}:{as_of}:{period_id}"
    return await _generate(
        session=session,
        context=context,
        report_name="trial_balance",
        request_identity=identity,
        operation=lambda: financial_reporting_service.trial_balance(
            session,
            context=context,
            as_of=as_of,
            start_date=start_date,
            branch_id=branch_id,
            period_id=period_id,
        ),
    )


@router.get("/balance-sheet", response_model=BalanceSheetResult)
async def balance_sheet(
    as_of: date,
    context: ReportContext,
    session: DatabaseSession,
    branch_id: UUID | None = None,
    period_id: UUID | None = None,
) -> BalanceSheetResult:
    identity = f"balance_sheet:{context.company.id}:{branch_id}:{as_of}:{period_id}"
    return await _generate(
        session=session,
        context=context,
        report_name="balance_sheet",
        request_identity=identity,
        operation=lambda: financial_reporting_service.balance_sheet(
            session,
            context=context,
            as_of=as_of,
            branch_id=branch_id,
            period_id=period_id,
        ),
    )


@router.get("/income-statement", response_model=IncomeStatementResult)
async def income_statement(
    start_date: date,
    end_date: date,
    context: ReportContext,
    session: DatabaseSession,
    branch_id: UUID | None = None,
    period_id: UUID | None = None,
) -> IncomeStatementResult:
    identity = f"income_statement:{context.company.id}:{branch_id}:{start_date}:{end_date}:{period_id}"
    return await _generate(
        session=session,
        context=context,
        report_name="income_statement",
        request_identity=identity,
        operation=lambda: financial_reporting_service.income_statement(
            session,
            context=context,
            start_date=start_date,
            end_date=end_date,
            branch_id=branch_id,
            period_id=period_id,
        ),
    )


@router.get("/general-ledger", response_model=GeneralLedgerResult)
async def general_ledger(
    start_date: date,
    end_date: date,
    context: ReportContext,
    session: DatabaseSession,
    branch_id: UUID | None = None,
    period_id: UUID | None = None,
    account_id: UUID | None = None,
) -> GeneralLedgerResult:
    identity = f"general_ledger:{context.company.id}:{branch_id}:{start_date}:{end_date}:{period_id}:{account_id}"
    return await _generate(
        session=session,
        context=context,
        report_name="general_ledger",
        request_identity=identity,
        operation=lambda: financial_reporting_service.general_ledger(
            session,
            context=context,
            start_date=start_date,
            end_date=end_date,
            branch_id=branch_id,
            period_id=period_id,
            account_id=account_id,
        ),
    )
