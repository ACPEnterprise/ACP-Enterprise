from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.codes import AdministrationPermission
from app.platform.permissions.dependencies import UnrestrictedAuthorization

from .schemas import (
    AgreementAcceptRequest,
    AgreementReceiptResponse,
    CurrentAgreementResponse,
)
from .service import (
    SALES_DEMO_ROLE,
    AgreementNotConfiguredError,
    AgreementValidationError,
    access_agreement_service,
)

router = APIRouter(prefix="/api/v1/access-agreements", tags=["Access Agreements"])
Session = Annotated[AsyncSession, Depends(get_database_session)]


def _receipt(receipt, document) -> AgreementReceiptResponse:
    return AgreementReceiptResponse(
        receipt_id=receipt.id,
        agreement_id=receipt.agreement_id,
        agreement_version=receipt.agreement_version,
        agreement_sha256=receipt.agreement_sha256,
        recipient_name=receipt.recipient_name,
        recipient_email=receipt.recipient_email,
        company_id=receipt.company_id,
        accepted_at=receipt.accepted_at,
        action=receipt.action,
        electronic_signature_consent=receipt.electronic_signature_consent,
        title=document.title,
        content=document.content,
    )


@router.get("/current", response_model=CurrentAgreementResponse)
async def current_agreement(
    context: UnrestrictedAuthorization,
    session: Session,
) -> CurrentAgreementResponse:
    document, acceptance = await access_agreement_service.current(
        session, context=context
    )
    if document is None:
        return CurrentAgreementResponse(
            required=SALES_DEMO_ROLE in context.role_codes,
            configured=False,
            accepted=False,
        )
    return CurrentAgreementResponse(
        required=True,
        configured=True,
        accepted=acceptance is not None,
        agreement_id=document.id,
        code=document.code,
        title=document.title,
        version=document.version,
        effective_at=document.effective_at,
        content=document.content,
        content_sha256=document.content_sha256,
        receipt_id=acceptance.id if acceptance else None,
        accepted_at=acceptance.accepted_at if acceptance else None,
    )


@router.post("/accept", response_model=AgreementReceiptResponse)
async def accept_agreement(
    payload: AgreementAcceptRequest,
    request: Request,
    context: UnrestrictedAuthorization,
    session: Session,
) -> AgreementReceiptResponse:
    try:
        receipt = await access_agreement_service.accept(
            session,
            context=context,
            agreement_id=payload.agreement_id,
            version=payload.version,
            acknowledge_reviewed=payload.acknowledge_reviewed,
            electronic_signature_consent=payload.electronic_signature_consent,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        await session.commit()
        from .models import AccessAgreementDocument

        document = await session.get(AccessAgreementDocument, receipt.agreement_id)
        assert document is not None
        return _receipt(receipt, document)
    except (AgreementNotConfiguredError, AgreementValidationError) as error:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/receipts/{receipt_id}", response_model=AgreementReceiptResponse)
async def get_receipt(
    receipt_id: UUID,
    context: UnrestrictedAuthorization,
    session: Session,
) -> AgreementReceiptResponse:
    from sqlalchemy import select

    from .models import AccessAgreementAcceptance, AccessAgreementDocument

    row = await session.execute(
        select(AccessAgreementAcceptance, AccessAgreementDocument)
        .join(
            AccessAgreementDocument,
            AccessAgreementDocument.id == AccessAgreementAcceptance.agreement_id,
        )
        .where(
            AccessAgreementAcceptance.id == receipt_id,
            AccessAgreementAcceptance.company_id == context.company.id,
        )
    )
    receipt, document = row.one_or_none() or (None, None)
    if receipt is None:
        raise HTTPException(status_code=404, detail="Agreement receipt not found.")
    if receipt.user_id != context.user.id and not context.has_permission(
        AdministrationPermission.COMPANY_ADMINISTER
    ):
        raise HTTPException(status_code=403, detail="Agreement receipt access denied.")
    return _receipt(receipt, document)
