from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.bank_connectivity import (
    BankAccountingEvidence,
    ConnectionView,
    GLMappingRequest,
    GLMappingView,
    bank_connectivity_service,
)
from app.accounting.banking import NormalizedBankEvidence, bank_authority_service
from app.accounting.banking_operator import banking_operator_service
from app.accounting.banking_schemas import (
    BankAccountCreate,
    BankAccountResponse,
    BankAccountSummary,
    BankDrilldownResponse,
    BankImportConfirmRequest,
    BankImportConfirmResponse,
    BankImportPreviewRequest,
    BankImportPreviewResponse,
    BankMatchReviewItem,
    BankReconciliationPrepare,
    BankReconciliationPreviewRequest,
    BankReconciliationPreviewResponse,
    BankReconciliationResponse,
    BankReconciliationTransition,
    BankTransactionIngest,
    BankTransactionMatchResponse,
    BankTransactionResponse,
    CashFlowResponse,
)
from app.accounting.errors import (
    AccountingConflict,
    AccountingNotFound,
    AccountingValidation,
)
from app.accounting.models import BankAccount, BankConnection, BankTransaction
from app.accounting.router import translate
from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AccountingPermission
from app.platform.permissions.dependencies import require_permission

router = APIRouter(prefix="/api/v1/accounting/banking", tags=["Accounting Banking"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
ReadContext = Annotated[
    AuthorizationContext, Depends(require_permission(AccountingPermission.READ))
]
ReconcileContext = Annotated[
    AuthorizationContext, Depends(require_permission(AccountingPermission.RECONCILE))
]
ApproveContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(AccountingPermission.FINANCE_APPROVE)),
]
MappingContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(AccountingPermission.OPENING_STATE_APPROVE)),
]


@router.get("/connections", response_model=tuple[ConnectionView, ...])
async def list_bank_connections(
    context: ReadContext, session: DatabaseSession
) -> tuple[ConnectionView, ...]:
    rows = tuple(
        (
            await session.scalars(
                select(BankConnection)
                .where(BankConnection.company_id == context.company.id)
                .order_by(BankConnection.institution_name, BankConnection.id)
            )
        ).all()
    )
    count_rows = (
        await session.execute(
            select(BankAccount.connection_id, func.count(BankAccount.id))
            .where(BankAccount.company_id == context.company.id)
            .group_by(BankAccount.connection_id)
        )
    ).all()
    counts: dict[UUID | None, int] = {
        connection_id: int(count) for connection_id, count in count_rows
    }
    return tuple(
        ConnectionView.model_validate(row).model_copy(
            update={"account_count": counts.get(row.id, 0)}
        )
        for row in rows
        if row.branch_id is None or context.can_access_branch(row.branch_id)
    )


@router.post("/accounts/{bank_account_id}/gl-mapping", response_model=GLMappingView)
async def approve_bank_gl_mapping(
    bank_account_id: UUID,
    data: GLMappingRequest,
    context: MappingContext,
    session: DatabaseSession,
) -> GLMappingView:
    try:
        async with session.begin():
            row = await bank_connectivity_service.approve_mapping(
                session,
                context=context,
                bank_account_id=bank_account_id,
                request=data,
            )
        return GLMappingView.model_validate(row)
    except (AccountingConflict, AccountingNotFound, AccountingValidation) as error:
        raise translate(error) from error


@router.get(
    "/accounts/{bank_account_id}/accounting-evidence",
    response_model=BankAccountingEvidence,
)
async def bank_accounting_evidence(
    bank_account_id: UUID,
    cutoff: date,
    context: ReadContext,
    session: DatabaseSession,
) -> BankAccountingEvidence:
    try:
        return await bank_connectivity_service.accounting_evidence(
            session,
            context=context,
            bank_account_id=bank_account_id,
            cutoff=cutoff,
        )
    except (AccountingConflict, AccountingNotFound, AccountingValidation) as error:
        raise translate(error) from error


@router.get("/summary", response_model=tuple[BankAccountSummary, ...])
async def bank_account_summary(
    context: ReadContext, session: DatabaseSession
) -> tuple[BankAccountSummary, ...]:
    return await banking_operator_service.summaries(
        session,
        company_id=context.company.id,
        accessible_branch_ids=context.authorized_branch_ids,
    )


@router.get("/accounts", response_model=tuple[BankAccountResponse, ...])
async def list_bank_accounts(
    context: ReadContext, session: DatabaseSession
) -> tuple[BankAccountResponse, ...]:
    rows = await session.scalars(
        select(BankAccount)
        .where(BankAccount.company_id == context.company.id)
        .order_by(BankAccount.account_name)
    )
    return tuple(
        BankAccountResponse.model_validate(row)
        for row in rows.all()
        if row.branch_id is None or context.can_access_branch(row.branch_id)
    )


@router.post(
    "/accounts", response_model=BankAccountResponse, status_code=status.HTTP_201_CREATED
)
async def create_bank_account(
    data: BankAccountCreate, context: ReconcileContext, session: DatabaseSession
) -> BankAccountResponse:
    try:
        async with session.begin():
            row = await bank_authority_service.create_account(
                session, context=context, **data.model_dump()
            )
        return BankAccountResponse.model_validate(row)
    except (AccountingConflict, AccountingNotFound, AccountingValidation) as error:
        raise translate(error) from error


@router.get(
    "/accounts/{bank_account_id}/transactions",
    response_model=tuple[BankTransactionResponse, ...],
)
async def list_bank_transactions(
    bank_account_id: UUID, context: ReadContext, session: DatabaseSession
) -> tuple[BankTransactionResponse, ...]:
    rows = await session.scalars(
        select(BankTransaction)
        .where(
            BankTransaction.company_id == context.company.id,
            BankTransaction.bank_account_id == bank_account_id,
        )
        .order_by(BankTransaction.posted_date, BankTransaction.external_transaction_id)
    )
    return tuple(BankTransactionResponse.model_validate(row) for row in rows.all())


@router.post(
    "/accounts/{bank_account_id}/transactions",
    response_model=BankTransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_bank_transaction(
    bank_account_id: UUID,
    data: BankTransactionIngest,
    context: ReconcileContext,
    session: DatabaseSession,
) -> BankTransactionResponse:
    values = data.model_dump()
    source_system = values.pop("source_system")
    try:
        async with session.begin():
            row = await bank_authority_service.ingest(
                session,
                context=context,
                bank_account_id=bank_account_id,
                source_system=source_system,
                evidence=NormalizedBankEvidence(**values),
            )
        return BankTransactionResponse.model_validate(row)
    except (AccountingConflict, AccountingNotFound, AccountingValidation) as error:
        raise translate(error) from error


@router.post(
    "/accounts/{bank_account_id}/imports/preview",
    response_model=BankImportPreviewResponse,
)
async def preview_bank_import(
    bank_account_id: UUID,
    data: BankImportPreviewRequest,
    context: ReconcileContext,
    session: DatabaseSession,
) -> BankImportPreviewResponse:
    try:
        return await banking_operator_service.preview_import(
            session,
            company_id=context.company.id,
            account_id=bank_account_id,
            request=data,
        )
    except (AccountingConflict, AccountingNotFound, AccountingValidation) as error:
        raise translate(error) from error


@router.post(
    "/accounts/{bank_account_id}/imports/confirm",
    response_model=BankImportConfirmResponse,
)
async def confirm_bank_import(
    bank_account_id: UUID,
    data: BankImportConfirmRequest,
    context: ReconcileContext,
    session: DatabaseSession,
) -> BankImportConfirmResponse:
    try:
        async with session.begin():
            return await banking_operator_service.confirm_import(
                session,
                context=context,
                account_id=bank_account_id,
                request=data,
            )
    except (AccountingConflict, AccountingNotFound, AccountingValidation) as error:
        raise translate(error) from error


@router.post(
    "/accounts/{bank_account_id}/transactions/{transaction_id}/match",
    response_model=BankTransactionMatchResponse,
)
async def match_bank_transaction(
    bank_account_id: UUID,
    transaction_id: UUID,
    context: ReconcileContext,
    session: DatabaseSession,
) -> BankTransactionMatchResponse:
    try:
        async with session.begin():
            row = await bank_authority_service.match_transaction(
                session,
                context=context,
                bank_account_id=bank_account_id,
                bank_transaction_id=transaction_id,
            )
        return BankTransactionMatchResponse.model_validate(row)
    except (AccountingConflict, AccountingNotFound, AccountingValidation) as error:
        raise translate(error) from error


@router.get("/match-review", response_model=tuple[BankMatchReviewItem, ...])
async def bank_match_review_queue(
    context: ReadContext,
    session: DatabaseSession,
    bank_account_id: UUID | None = None,
) -> tuple[BankMatchReviewItem, ...]:
    return await banking_operator_service.review_queue(
        session,
        company_id=context.company.id,
        account_id=bank_account_id,
    )


@router.get(
    "/transactions/{transaction_id}/drilldown",
    response_model=BankDrilldownResponse,
)
async def bank_transaction_drilldown(
    transaction_id: UUID, context: ReadContext, session: DatabaseSession
) -> BankDrilldownResponse:
    try:
        return await banking_operator_service.drilldown(
            session,
            company_id=context.company.id,
            transaction_id=transaction_id,
        )
    except AccountingNotFound as error:
        raise translate(error) from error


@router.post(
    "/accounts/{bank_account_id}/reconciliations/preview",
    response_model=BankReconciliationPreviewResponse,
)
async def preview_bank_reconciliation(
    bank_account_id: UUID,
    data: BankReconciliationPreviewRequest,
    context: ReconcileContext,
    session: DatabaseSession,
) -> BankReconciliationPreviewResponse:
    try:
        return await banking_operator_service.reconciliation_preview(
            session,
            company_id=context.company.id,
            account_id=bank_account_id,
            request=data,
        )
    except (AccountingConflict, AccountingNotFound, AccountingValidation) as error:
        raise translate(error) from error


@router.get(
    "/accounts/{bank_account_id}/reconciliations",
    response_model=tuple[BankReconciliationResponse, ...],
)
async def bank_reconciliation_states(
    bank_account_id: UUID,
    context: ReadContext,
    session: DatabaseSession,
) -> tuple[BankReconciliationResponse, ...]:
    try:
        return await banking_operator_service.reconciliations(
            session, company_id=context.company.id, account_id=bank_account_id
        )
    except AccountingNotFound as error:
        raise translate(error) from error


@router.get(
    "/accounts/{bank_account_id}/reconciliations/history",
    response_model=tuple[BankReconciliationResponse, ...],
)
async def bank_reconciliation_history(
    bank_account_id: UUID,
    context: ReadContext,
    session: DatabaseSession,
) -> tuple[BankReconciliationResponse, ...]:
    try:
        return await banking_operator_service.history(
            session, company_id=context.company.id, account_id=bank_account_id
        )
    except AccountingNotFound as error:
        raise translate(error) from error


@router.get("/cash-flow", response_model=CashFlowResponse)
async def bank_cash_flow(
    context: ReadContext,
    session: DatabaseSession,
    period_start: Annotated[date, Query()],
    period_end: Annotated[date, Query()],
    basis: Annotated[str, Query()] = "posted_cash_movement",
) -> CashFlowResponse:
    try:
        return await banking_operator_service.cash_flow(
            session,
            company_id=context.company.id,
            period_start=period_start,
            period_end=period_end,
            basis=basis,
        )
    except AccountingConflict as error:
        raise translate(error) from error


@router.post(
    "/accounts/{bank_account_id}/reconciliations/prepare",
    response_model=BankReconciliationResponse,
)
async def prepare_bank_reconciliation(
    bank_account_id: UUID,
    data: BankReconciliationPrepare,
    context: ReconcileContext,
    session: DatabaseSession,
) -> BankReconciliationResponse:
    try:
        async with session.begin():
            row = await bank_authority_service.prepare_reconciliation(
                session,
                context=context,
                bank_account_id=bank_account_id,
                **data.model_dump(),
            )
        return await banking_operator_service.reconciliation_response(session, row)
    except (AccountingConflict, AccountingNotFound, AccountingValidation) as error:
        raise translate(error) from error


@router.post(
    "/accounts/{bank_account_id}/reconciliations/{reconciliation_id}/submit",
    response_model=BankReconciliationResponse,
)
async def submit_bank_reconciliation(
    bank_account_id: UUID,
    reconciliation_id: UUID,
    data: BankReconciliationTransition,
    context: ReconcileContext,
    session: DatabaseSession,
) -> BankReconciliationResponse:
    try:
        async with session.begin():
            row = await bank_authority_service.submit_reconciliation(
                session,
                context=context,
                bank_account_id=bank_account_id,
                reconciliation_id=reconciliation_id,
                expected_version=data.expected_version,
            )
        return await banking_operator_service.reconciliation_response(session, row)
    except (AccountingConflict, AccountingNotFound, AccountingValidation) as error:
        raise translate(error) from error


@router.post(
    "/accounts/{bank_account_id}/reconciliations/{reconciliation_id}/close",
    response_model=BankReconciliationResponse,
)
async def close_bank_reconciliation(
    bank_account_id: UUID,
    reconciliation_id: UUID,
    data: BankReconciliationTransition,
    context: ApproveContext,
    session: DatabaseSession,
) -> BankReconciliationResponse:
    try:
        async with session.begin():
            row = await bank_authority_service.close_reconciliation(
                session,
                context=context,
                bank_account_id=bank_account_id,
                reconciliation_id=reconciliation_id,
                expected_version=data.expected_version,
            )
        return await banking_operator_service.reconciliation_response(session, row)
    except (AccountingConflict, AccountingNotFound, AccountingValidation) as error:
        raise translate(error) from error
