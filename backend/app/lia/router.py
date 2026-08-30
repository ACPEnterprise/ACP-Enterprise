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
        state="DETERMINISTIC_CAPABLE",
        provider_state="AI_PROVIDER_NOT_CONFIGURED",
        policy_state="POLICY_REQUIRED",
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


@router.get("/retention-options", response_model=dict[str, object])
async def retention_options(context: ResolvedAuthorization) -> dict[str, object]:
    return {
        "company_id": str(context.company.id),
        "state": "POLICY_REQUIRED",
        "current_behavior": "NO_TRANSCRIPT_PERSISTENCE",
        "options": [
            {
                "option": "NO_RETENTION",
                "privacy": "Strongest minimization; no conversation continuity or retrospective quality review.",
                "security": "No transcript repository or deletion workflow is required.",
            },
            {
                "option": "SHORT_RETENTION",
                "privacy": "Time-limited protected transcripts; requires an explicit duration and deletion evidence.",
                "security": "Requires encrypted custody, narrow access, expiry enforcement, and access audit.",
            },
            {
                "option": "GOVERNED_RETENTION",
                "privacy": "Purpose-bound history for approved use cases; highest governance burden.",
                "security": "Requires retention classes, legal holds, export/deletion controls, and privileged review audit.",
            },
        ],
        "owner_decisions": [
            "retention option",
            "duration when applicable",
            "authorized reviewer roles",
            "approved purposes and legal-hold policy",
        ],
    }


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
