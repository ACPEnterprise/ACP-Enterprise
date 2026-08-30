from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.dependencies import ResolvedAuthorization

from .contracts import (
    LiaFeedback,
    LiaFeedbackReceipt,
    LiaReadiness,
    LiaRequest,
    LiaResponse,
)
from .foundation import FoundationReadiness, foundation_readiness
from .service import POLICY_VERSION, lia_service

router = APIRouter(prefix="/api/v1/lia", tags=["LIA"])
Session = Annotated[AsyncSession, Depends(get_database_session)]


@router.get("/readiness", response_model=LiaReadiness)
async def readiness(context: ResolvedAuthorization) -> LiaReadiness:
    return LiaReadiness(
        state="PRODUCT_READY_PROVIDER_GATE",
        provider_state="AI_PROVIDER_NOT_CONFIGURED",
        deterministic_capabilities=(
            "authorized_retrieval",
            "evidence_summary",
            "navigation",
            "safe_proposal",
        ),
        generative_capabilities=(),
        policy_version=POLICY_VERSION,
        retention_state="TRANSCRIPT_RETENTION_POLICY_REQUIRED",
    )


@router.get("/foundation-readiness", response_model=FoundationReadiness)
async def foundation_readiness_status(
    context: ResolvedAuthorization,
) -> FoundationReadiness:
    # Authentication and current authorization resolution are required even though
    # the response contains no protected business evidence.
    _ = context.authorization_version
    return foundation_readiness()


@router.post("/ask", response_model=LiaResponse)
async def ask(
    payload: LiaRequest,
    context: ResolvedAuthorization,
    session: Session,
) -> LiaResponse:
    return await lia_service.ask(session, context=context, request=payload)


@router.get("/briefing", response_model=LiaResponse)
async def briefing(
    context: ResolvedAuthorization,
    session: Session,
) -> LiaResponse:
    return await lia_service.ask(
        session,
        context=context,
        request=LiaRequest(question="How are we doing today and what needs attention?"),
    )


@router.post("/feedback", response_model=LiaFeedbackReceipt)
async def feedback(
    payload: LiaFeedback, context: ResolvedAuthorization
) -> LiaFeedbackReceipt:
    # Feedback is quality evidence only and cannot rewrite an authoritative fact.
    from .service import logger

    feedback_id = uuid4()
    logger.info(
        "lia_feedback feedback_id=%s request_id=%s actor_id=%s company_id=%s rating=%s reason_code=%s",
        feedback_id,
        payload.request_id,
        context.user.id,
        context.company.id,
        payload.rating,
        payload.reason_code,
    )
    return LiaFeedbackReceipt(feedback_id=feedback_id)
