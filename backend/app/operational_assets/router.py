from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.operational_assets.operationalization import asset_operationalization_service
from app.operational_assets.schemas import (
    AssetActionCreate,
    AssetActionOut,
    AssetCreate,
    AssetDetail,
    AssetImportCandidate,
    AssetImportOut,
    AssetOperationalReadiness,
    AssetOut,
    AssetPolicyDraft,
    AssetPolicyOut,
    EvidenceCreate,
    EvidenceOut,
    LifecycleChange,
    RelationshipCreate,
    RelationshipOut,
)
from app.operational_assets.service import (
    AssetConflict,
    AssetNotFound,
    AssetValidation,
    asset_service,
)
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AssetPermission
from app.platform.permissions.dependencies import require_permission
from app.platform.reliability.correlation import current_correlation_id
from app.platform.reliability.failures import ClientRecovery, FailureCode, SafeFailure

router = APIRouter(prefix="/api/v1/assets", tags=["Operational Assets"])
Session = Annotated[AsyncSession, Depends(get_database_session)]
Read = Annotated[
    AuthorizationContext, Depends(require_permission(AssetPermission.READ))
]
Manage = Annotated[
    AuthorizationContext, Depends(require_permission(AssetPermission.MANAGE))
]


def translated(error: Exception) -> HTTPException:
    if isinstance(error, AssetNotFound):
        code, http, message, recovery = (
            FailureCode.NOT_FOUND,
            404,
            "Asset evidence was not found.",
            ClientRecovery.TERMINAL_FAILURE,
        )
    elif isinstance(error, AssetConflict):
        code, http, message, recovery = (
            FailureCode.RESOURCE_STATE_CONFLICT,
            409,
            "Asset command conflicts with current authority.",
            ClientRecovery.RETRY_AFTER_REFRESH,
        )
    else:
        code, http, message, recovery = (
            FailureCode.VALIDATION,
            422,
            "Asset request requires correction.",
            ClientRecovery.USER_CORRECTION_REQUIRED,
        )
    return HTTPException(
        status_code=http,
        detail=SafeFailure(code, message, recovery, current_correlation_id()).detail(),
    )


@router.get("", response_model=list[AssetOut])
async def list_assets(
    context: Read,
    session: Session,
    branch_id: UUID | None = None,
    asset_class: str | None = None,
    lifecycle: str | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
):
    try:
        return [
            AssetOut.model_validate(x)
            for x in await asset_service.list_assets(
                session,
                context,
                branch_id=branch_id,
                asset_class=asset_class,
                lifecycle=lifecycle,
                query=q,
                limit=limit,
            )
        ]
    except (AssetNotFound, AssetConflict, AssetValidation) as e:
        raise translated(e) from e


@router.post("", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
async def create_asset(data: AssetCreate, context: Manage, session: Session):
    try:
        return AssetOut.model_validate(
            await asset_service.create(session, context, data)
        )
    except (AssetNotFound, AssetConflict, AssetValidation) as e:
        raise translated(e) from e


@router.get("/{asset_id}", response_model=AssetDetail)
async def asset_detail(asset_id: UUID, context: Read, session: Session):
    try:
        row, evidence, relationships, readiness, reasons = await asset_service.detail(
            session, context, asset_id
        )
        return AssetDetail(
            asset=AssetOut.model_validate(row),
            evidence=[EvidenceOut.model_validate(x) for x in evidence],
            relationships=[RelationshipOut.model_validate(x) for x in relationships],
            readiness=readiness,
            readiness_reasons=reasons,
        )
    except (AssetNotFound, AssetConflict, AssetValidation) as e:
        raise translated(e) from e


@router.post(
    "/{asset_id}/evidence",
    response_model=EvidenceOut,
    status_code=status.HTTP_201_CREATED,
)
async def record_evidence(
    asset_id: UUID, data: EvidenceCreate, context: Manage, session: Session
):
    try:
        return EvidenceOut.model_validate(
            await asset_service.add_evidence(session, context, asset_id, data)
        )
    except (AssetNotFound, AssetConflict, AssetValidation) as e:
        raise translated(e) from e


@router.post(
    "/{asset_id}/relationships",
    response_model=RelationshipOut,
    status_code=status.HTTP_201_CREATED,
)
async def record_relationship(
    asset_id: UUID, data: RelationshipCreate, context: Manage, session: Session
):
    try:
        return RelationshipOut.model_validate(
            await asset_service.relate(session, context, asset_id, data)
        )
    except (AssetNotFound, AssetConflict, AssetValidation) as e:
        raise translated(e) from e


@router.post("/{asset_id}/lifecycle", response_model=AssetOut)
async def change_lifecycle(
    asset_id: UUID, data: LifecycleChange, context: Manage, session: Session
):
    try:
        return AssetOut.model_validate(
            await asset_service.transition(session, context, asset_id, data)
        )
    except (AssetNotFound, AssetConflict, AssetValidation) as e:
        raise translated(e) from e


@router.get("/{asset_id}/actions", response_model=list[AssetActionOut])
async def asset_action_history(
    asset_id: UUID,
    context: Read,
    session: Session,
    limit: int = Query(100, ge=1, le=200),
):
    try:
        return [
            AssetActionOut.model_validate(item)
            for item in await asset_service.action_history(
                session, context, asset_id, limit
            )
        ]
    except (AssetNotFound, AssetConflict, AssetValidation) as e:
        raise translated(e) from e


@router.post(
    "/{asset_id}/actions",
    response_model=AssetActionOut,
    status_code=status.HTTP_201_CREATED,
)
async def record_asset_action(
    asset_id: UUID,
    data: AssetActionCreate,
    context: Manage,
    session: Session,
):
    try:
        return AssetActionOut.model_validate(
            await asset_service.record_action(session, context, asset_id, data)
        )
    except (AssetNotFound, AssetConflict, AssetValidation) as e:
        raise translated(e) from e


@router.post(
    "/operationalization/policies", response_model=AssetPolicyOut, status_code=201
)
async def draft_asset_policy(data: AssetPolicyDraft, context: Manage, session: Session):
    try:
        return AssetPolicyOut.model_validate(
            await asset_operationalization_service.draft_policy(session, context, data)
        )
    except (AssetNotFound, AssetConflict, AssetValidation) as e:
        raise translated(e) from e


@router.post(
    "/operationalization/import-preview", response_model=AssetImportOut, status_code=201
)
async def preview_asset_import(
    data: AssetImportCandidate, context: Manage, session: Session
):
    try:
        return AssetImportOut.model_validate(
            await asset_operationalization_service.import_candidate(
                session, context, data
            )
        )
    except (AssetNotFound, AssetConflict, AssetValidation) as e:
        raise translated(e) from e


@router.get("/operationalization/readiness", response_model=AssetOperationalReadiness)
async def asset_operational_readiness(context: Read, session: Session):
    state, counts, policies = await asset_operationalization_service.readiness(
        session, context
    )
    return AssetOperationalReadiness(state=state, counts=counts, policy_states=policies)
