from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_quality.catalog import QUALITY_CATALOG
from app.data_quality.schemas import QualityRuleResponse, QualitySummaryResponse
from app.data_quality.service import data_quality_service
from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import LaunchPlatformPermission
from app.platform.permissions.dependencies import require_permission

router = APIRouter(prefix="/api/v1/data-quality", tags=["Data Quality"])
ReadContext = Annotated[AuthorizationContext, Depends(require_permission(LaunchPlatformPermission.AUDIT_READ))]
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]


@router.get("/catalog", response_model=list[QualityRuleResponse])
async def catalog(context: ReadContext) -> list[QualityRuleResponse]:
    del context
    return [QualityRuleResponse(rule_id=r.rule_id, version=r.version, domain=r.domain, state=r.state, severity=r.severity, launch_impact=r.launch_impact, explanation=r.explanation, evidence_required=list(r.evidence_required), repair_owner=r.repair_owner, automated_correction_prohibited=r.automated_correction_prohibited, evidence_digest=r.digest) for r in QUALITY_CATALOG]


@router.get("/summary", response_model=QualitySummaryResponse)
async def summary(context: ReadContext, session: DatabaseSession,
                  limit: Annotated[int, Query(ge=1, le=200)] = 50,
                  offset: Annotated[int, Query(ge=0)] = 0) -> QualitySummaryResponse:
    return await data_quality_service.scan(session, context=context, limit=limit, offset=offset)
