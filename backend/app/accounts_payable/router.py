from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts_payable.contracts import (
    BillLineSpec,
    BillSpec,
    CreditSpec,
    DisbursementSpec,
    VendorSpec,
)
from app.accounts_payable.errors import AccountsPayableError, APConflict, APNotFound
from app.accounts_payable.schemas import (
    AccountMappingInput,
    AgingItem,
    BillCreate,
    BillItem,
    CreditApplyInput,
    CreditCreate,
    DisbursementApplyInput,
    DisbursementCreate,
    DuplicateOverrideInput,
    ReverseInput,
    TransitionInput,
    UnapplyInput,
    VendorCreate,
    VendorItem,
    VendorMapInput,
)
from app.accounts_payable.service import accounts_payable_service
from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AccountsPayablePermission
from app.platform.permissions.dependencies import require_permission
from app.platform.reliability.correlation import current_correlation_id
from app.platform.reliability.failures import ClientRecovery, FailureCode, SafeFailure

router = APIRouter(prefix="/api/v1/accounts-payable", tags=["Accounts Payable"])
Session = Annotated[AsyncSession, Depends(get_database_session)]
Read = Annotated[AuthorizationContext, Depends(require_permission(AccountsPayablePermission.READ))]
VendorManage = Annotated[AuthorizationContext, Depends(require_permission(AccountsPayablePermission.VENDOR_MANAGE))]
Prepare = Annotated[AuthorizationContext, Depends(require_permission(AccountsPayablePermission.BILL_PREPARE))]
Approve = Annotated[AuthorizationContext, Depends(require_permission(AccountsPayablePermission.BILL_APPROVE))]
CreditManage = Annotated[AuthorizationContext, Depends(require_permission(AccountsPayablePermission.CREDIT_MANAGE))]
DisbursementRecord = Annotated[AuthorizationContext, Depends(require_permission(AccountsPayablePermission.DISBURSEMENT_RECORD))]
ReportRead = Annotated[AuthorizationContext, Depends(require_permission(AccountsPayablePermission.REPORT_READ))]


def _error(exc: AccountsPayableError) -> HTTPException:
    if isinstance(exc, APNotFound):
        failure = SafeFailure(FailureCode.NOT_FOUND, "AP resource was not found.", ClientRecovery.TERMINAL_FAILURE, current_correlation_id())
        return HTTPException(status.HTTP_404_NOT_FOUND, failure.detail())
    if isinstance(exc, APConflict):
        failure = SafeFailure(FailureCode.RESOURCE_STATE_CONFLICT, "AP operation conflicts with current authority.", ClientRecovery.RETRY_AFTER_REFRESH, current_correlation_id())
        return HTTPException(status.HTTP_409_CONFLICT, failure.detail())
    failure = SafeFailure(FailureCode.VALIDATION, "AP request requires correction.", ClientRecovery.USER_CORRECTION_REQUIRED, current_correlation_id())
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, failure.detail())


def _branch(context: AuthorizationContext, branch_id: UUID) -> None:
    if not context.can_access_branch(branch_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "AP resource was not found.")


@router.post("/vendors", response_model=VendorItem, status_code=status.HTTP_201_CREATED)
async def create_vendor(payload: VendorCreate, context: VendorManage, session: Session) -> VendorItem:
    try:
        row = await accounts_payable_service.create_vendor(session, VendorSpec(company_id=context.company.id, actor_user_id=context.user.id, **payload.model_dump()))
        return VendorItem.model_validate(row)
    except AccountsPayableError as exc:
        raise _error(exc) from exc


@router.post("/vendors/{vendor_id}/source-mappings", status_code=status.HTTP_201_CREATED)
async def map_vendor(vendor_id: UUID, payload: VendorMapInput, context: VendorManage, session: Session) -> dict[str, UUID]:
    try:
        row = await accounts_payable_service.map_vendor(session, context.company.id, vendor_id, context.user.id, **payload.model_dump())
        return {"id": row.id}
    except AccountsPayableError as exc:
        raise _error(exc) from exc


@router.post("/vendors/{vendor_id}/archive", response_model=VendorItem)
async def archive_vendor(vendor_id: UUID, payload: TransitionInput, context: VendorManage, session: Session) -> VendorItem:
    try:
        return VendorItem.model_validate(await accounts_payable_service.archive_vendor(session, context.company.id, vendor_id, context.user.id, payload.expected_version))
    except AccountsPayableError as exc:
        raise _error(exc) from exc


@router.post("/account-mappings", status_code=status.HTTP_201_CREATED)
async def create_account_mapping(payload: AccountMappingInput, context: Approve, session: Session) -> dict[str, UUID]:
    try:
        row = await accounts_payable_service.create_account_mapping(session, context.company.id, context.user.id, **payload.model_dump())
        return {"id": row.id}
    except AccountsPayableError as exc:
        raise _error(exc) from exc


@router.post("/bills", response_model=BillItem, status_code=status.HTTP_201_CREATED)
async def create_bill(payload: BillCreate, context: Prepare, session: Session) -> BillItem:
    _branch(context, payload.branch_id)
    if any(not context.can_access_branch(line.branch_id) for line in payload.lines):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "AP resource was not found.")
    data = payload.model_dump(exclude={"lines"})
    spec = BillSpec(company_id=context.company.id, actor_user_id=context.user.id, lines=tuple(BillLineSpec(**line.model_dump()) for line in payload.lines), **data)
    try:
        return BillItem.model_validate(await accounts_payable_service.create_bill(session, spec))
    except AccountsPayableError as exc:
        raise _error(exc) from exc


@router.post("/bills/{bill_id}/submit", response_model=BillItem)
async def submit_bill(bill_id: UUID, payload: TransitionInput, context: Prepare, session: Session) -> BillItem:
    try:
        return BillItem.model_validate(await accounts_payable_service.submit_bill(session, context.company.id, bill_id, context.user.id, payload.expected_version, context.authorized_branch_ids))
    except AccountsPayableError as exc:
        raise _error(exc) from exc


@router.post("/bills/{bill_id}/approve", response_model=BillItem)
async def approve_bill(bill_id: UUID, payload: TransitionInput, context: Approve, session: Session) -> BillItem:
    try:
        return BillItem.model_validate(await accounts_payable_service.approve_bill(session, context.company.id, bill_id, context.user.id, payload.expected_version, context.authorized_branch_ids))
    except AccountsPayableError as exc:
        raise _error(exc) from exc


@router.post("/bills/{bill_id}/duplicate-override", status_code=status.HTTP_201_CREATED)
async def override_duplicate(bill_id: UUID, payload: DuplicateOverrideInput, context: Approve, session: Session) -> dict[str, UUID]:
    try:
        row = await accounts_payable_service.authorize_duplicate(session, context.company.id, bill_id, payload.duplicate_bill_id, payload.requester_user_id, context.user.id, payload.reason, payload.evidence_reference, context.authorized_branch_ids)
        return {"id": row.id}
    except AccountsPayableError as exc:
        raise _error(exc) from exc


@router.post("/bills/{bill_id}/reverse", response_model=BillItem)
async def reverse_bill(bill_id: UUID, payload: ReverseInput, context: Approve, session: Session) -> BillItem:
    try:
        return BillItem.model_validate(await accounts_payable_service.reverse_bill(session, context.company.id, bill_id, context.user.id, payload.effective_date, payload.reason, context.authorized_branch_ids))
    except AccountsPayableError as exc:
        raise _error(exc) from exc


@router.post("/credits", status_code=status.HTTP_201_CREATED)
async def issue_credit(payload: CreditCreate, context: CreditManage, session: Session) -> dict[str, UUID]:
    try:
        row = await accounts_payable_service.issue_credit(session, CreditSpec(company_id=context.company.id, actor_user_id=context.user.id, **payload.model_dump()))
        return {"id": row.id}
    except AccountsPayableError as exc:
        raise _error(exc) from exc


@router.post("/credits/{credit_id}/applications", status_code=status.HTTP_201_CREATED)
async def apply_credit(credit_id: UUID, payload: CreditApplyInput, context: CreditManage, session: Session) -> dict[str, UUID]:
    try:
        row = await accounts_payable_service.apply_credit(session, context.company.id, credit_id, payload.bill_id, context.user.id, payload.amount, payload.idempotency_key, context.authorized_branch_ids)
        return {"id": row.id}
    except AccountsPayableError as exc:
        raise _error(exc) from exc


@router.post("/credit-applications/{application_id}/unapply")
async def unapply_credit(application_id: UUID, payload: UnapplyInput, context: CreditManage, session: Session) -> dict[str, UUID]:
    try:
        row = await accounts_payable_service.unapply_credit(session, context.company.id, application_id, context.user.id, payload.idempotency_key, context.authorized_branch_ids)
        return {"id": row.id}
    except AccountsPayableError as exc:
        raise _error(exc) from exc


@router.post("/disbursements", status_code=status.HTTP_201_CREATED)
async def record_disbursement(payload: DisbursementCreate, context: DisbursementRecord, session: Session) -> dict[str, UUID]:
    _branch(context, payload.branch_id)
    try:
        row = await accounts_payable_service.record_disbursement(session, DisbursementSpec(company_id=context.company.id, recorder_user_id=context.user.id, **payload.model_dump()))
        return {"id": row.id}
    except AccountsPayableError as exc:
        raise _error(exc) from exc


@router.post("/disbursements/{disbursement_id}/applications", status_code=status.HTTP_201_CREATED)
async def apply_disbursement(disbursement_id: UUID, payload: DisbursementApplyInput, context: DisbursementRecord, session: Session) -> dict[str, UUID]:
    try:
        row = await accounts_payable_service.apply_disbursement(session, context.company.id, disbursement_id, payload.bill_id, context.user.id, payload.amount, payload.idempotency_key, context.authorized_branch_ids)
        return {"id": row.id}
    except AccountsPayableError as exc:
        raise _error(exc) from exc


@router.post("/disbursements/{disbursement_id}/reverse")
async def reverse_disbursement(disbursement_id: UUID, payload: ReverseInput, context: DisbursementRecord, session: Session) -> dict[str, UUID]:
    try:
        row = await accounts_payable_service.reverse_disbursement(session, context.company.id, disbursement_id, context.user.id, payload.reason, context.authorized_branch_ids)
        return {"id": row.id}
    except AccountsPayableError as exc:
        raise _error(exc) from exc


@router.get("/aging", response_model=list[AgingItem])
async def aging(as_of: Annotated[date, Query()], context: ReportRead, session: Session) -> list[AgingItem]:
    return [AgingItem.model_validate(row) for row in await accounts_payable_service.aging(session, context.company.id, as_of, context.authorized_branch_ids)]
