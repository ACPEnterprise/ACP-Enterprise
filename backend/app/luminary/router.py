from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import LuminaryPermission
from app.platform.permissions.dependencies import require_permission

from .service import LuminaryNotFoundError, luminary_service

router = APIRouter(prefix="/api/v1/luminary", tags=["Luminary"])
Session = Annotated[AsyncSession, Depends(get_database_session)]
Reader = Annotated[
    AuthorizationContext, Depends(require_permission(LuminaryPermission.READ))
]
Analyst = Annotated[
    AuthorizationContext, Depends(require_permission(LuminaryPermission.ANALYZE))
]


@router.post("/analyses", response_model=dict[str, object])
async def analyze(
    session: Session,
    context: Analyst,
    start: Annotated[date, Query()],
    end: Annotated[date, Query()],
) -> dict[str, object]:
    try:
        value = await luminary_service.analyze(
            session, context=context, period_start=start, period_end=end
        )
        await session.commit()
        return value
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error


@router.get("/briefing", response_model=dict[str, object])
async def briefing(
    session: Session,
    context: Reader,
    start: Annotated[date, Query()],
    end: Annotated[date, Query()],
) -> dict[str, object]:
    try:
        value = await luminary_service.latest(
            session, context=context, period_start=start, period_end=end
        )
        await session.commit()
        return value
    except LuminaryNotFoundError as error:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Luminary briefing has not been analyzed for this period.",
        ) from error


@router.get("/findings/{finding_id}", response_model=dict[str, object])
async def finding(
    finding_id: UUID, session: Session, context: Reader
) -> dict[str, object]:
    try:
        return await luminary_service.finding(
            session, context=context, finding_id=finding_id
        )
    except LuminaryNotFoundError as error:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Luminary finding was not found."
        ) from error


@router.get("/history", response_model=list[dict[str, object]])
async def history(
    session: Session, context: Reader, limit: Annotated[int, Query(ge=1, le=100)] = 24
) -> list[dict[str, object]]:
    return await luminary_service.history(session, context=context, limit=limit)


@router.get("/source-readiness", response_model=dict[str, object])
async def source_readiness(context: Reader) -> dict[str, object]:
    """Truthful admission map; unavailable sources never become implied facts."""
    return {
        "company_id": str(context.company.id),
        "branch_id": str(context.active_branch.id) if context.active_branch else None,
        "sources": [
            {
                "domain": "business_economics",
                "state": "authoritative",
                "use": "profitability, revenue, admitted costs, attribution, quality, and lineage",
            },
            {
                "domain": "beacon",
                "state": "authoritative_reference",
                "use": "condition identity and workflow link; Beacon retains lifecycle",
            },
            {
                "domain": "jobs_customers_branches",
                "state": "admitted_through_economics",
                "use": "authoritative identity and rollup scope",
            },
            {
                "domain": "payroll_purchasing_inventory_accounting",
                "state": "admitted_through_economics",
                "use": "accepted measured cost provenance only",
            },
            {
                "domain": "scheduling_dispatch_operations",
                "state": "policy_required",
                "use": "no cross-domain association until an admitted measurement contract exists",
            },
            {
                "domain": "cash_collection",
                "state": "policy_required",
                "use": "invoice revenue is never treated as settled cash",
            },
        ],
        "limitations": [
            "Luminary does not infer Employee-to-Job attribution.",
            "Luminary does not infer causality or choose allocation policy.",
            "Luminary does not create Beacon workflow or operational mutations.",
        ],
    }


@router.get("/lia/briefing", response_model=dict[str, object])
async def lia_briefing(
    session: Session,
    context: Reader,
    start: Annotated[date, Query()],
    end: Annotated[date, Query()],
) -> dict[str, object]:
    """Stable, permission-aware evidence contract; LIA remains a separate product."""
    return await briefing(session, context, start, end)
