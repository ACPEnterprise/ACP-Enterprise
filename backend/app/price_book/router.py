from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import PriceBookPermission
from app.platform.permissions.dependencies import require_permission

from .errors import (
    PriceBookConflict,
    PriceBookError,
    PriceBookNotFound,
    PriceBookValidation,
)
from .schemas import (
    ActivationRequest,
    AuditItem,
    CatalogPage,
    CategoryCreate,
    CategoryItem,
    LifecycleRequest,
    OptionCreate,
    OptionGroupCreate,
    OptionGroupItem,
    OptionItem,
    PriceVersionCreate,
    PriceVersionItem,
    PriceVersionUpdate,
    ServiceItem,
    ServiceItemCreate,
    SnapshotItem,
    SnapshotRequest,
    TaxClassificationCreate,
    TaxClassificationItem,
)
from .service import price_book_service

router = APIRouter(prefix="/api/v1/price-book", tags=["Price Book"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
ReadContext = Annotated[
    AuthorizationContext, Depends(require_permission(PriceBookPermission.READ))
]
ManageContext = Annotated[
    AuthorizationContext, Depends(require_permission(PriceBookPermission.MANAGE))
]
ActivateContext = Annotated[
    AuthorizationContext, Depends(require_permission(PriceBookPermission.ACTIVATE))
]


def http_error(error: PriceBookError) -> HTTPException:
    if isinstance(error, PriceBookNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(error))
    if isinstance(error, PriceBookConflict):
        return HTTPException(status.HTTP_409_CONFLICT, str(error))
    if isinstance(error, PriceBookValidation):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))
    return HTTPException(status.HTTP_400_BAD_REQUEST, "Price Book operation failed.")


@router.get("", response_model=CatalogPage)
async def catalog(
    context: ReadContext,
    session: DatabaseSession,
    branch_id: Annotated[UUID | None, Query()] = None,
) -> CatalogPage:
    try:
        return await price_book_service.catalog(
            session, context=context, branch_id=branch_id
        )
    except PriceBookError as error:
        raise http_error(error) from error


@router.post(
    "/categories", response_model=CategoryItem, status_code=status.HTTP_201_CREATED
)
async def create_category(
    payload: CategoryCreate, context: ManageContext, session: DatabaseSession
) -> CategoryItem:
    try:
        return CategoryItem.model_validate(
            await price_book_service.create_category(
                session, context=context, payload=payload
            )
        )
    except PriceBookError as error:
        raise http_error(error) from error


@router.post(
    "/tax-classifications",
    response_model=TaxClassificationItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_tax(
    payload: TaxClassificationCreate, context: ManageContext, session: DatabaseSession
) -> TaxClassificationItem:
    try:
        return TaxClassificationItem.model_validate(
            await price_book_service.create_tax(
                session, context=context, payload=payload
            )
        )
    except PriceBookError as error:
        raise http_error(error) from error


@router.post(
    "/option-groups",
    response_model=OptionGroupItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_option_group(
    payload: OptionGroupCreate, context: ManageContext, session: DatabaseSession
) -> OptionGroupItem:
    try:
        return OptionGroupItem.model_validate(
            await price_book_service.create_option_group(
                session, context=context, payload=payload
            )
        )
    except PriceBookError as error:
        raise http_error(error) from error


@router.post(
    "/option-groups/{group_id}/options",
    response_model=OptionItem,
    status_code=status.HTTP_201_CREATED,
)
async def add_option(
    group_id: UUID,
    payload: OptionCreate,
    context: ManageContext,
    session: DatabaseSession,
) -> OptionItem:
    try:
        return OptionItem.model_validate(
            await price_book_service.add_option(
                session, context=context, group_id=group_id, payload=payload
            )
        )
    except PriceBookError as error:
        raise http_error(error) from error


@router.post(
    "/service-items", response_model=ServiceItem, status_code=status.HTTP_201_CREATED
)
async def create_item(
    payload: ServiceItemCreate, context: ManageContext, session: DatabaseSession
) -> ServiceItem:
    try:
        return ServiceItem.model_validate(
            await price_book_service.create_item(
                session, context=context, payload=payload
            )
        )
    except PriceBookError as error:
        raise http_error(error) from error


@router.post(
    "/service-items/{item_id}/versions",
    response_model=PriceVersionItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_version(
    item_id: UUID,
    payload: PriceVersionCreate,
    context: ManageContext,
    session: DatabaseSession,
) -> PriceVersionItem:
    try:
        return PriceVersionItem.model_validate(
            await price_book_service.create_version(
                session, context=context, item_id=item_id, payload=payload
            )
        )
    except PriceBookError as error:
        raise http_error(error) from error


@router.post("/versions/{version_id}/activate", response_model=PriceVersionItem)
async def activate(
    version_id: UUID,
    payload: ActivationRequest,
    context: ActivateContext,
    session: DatabaseSession,
) -> PriceVersionItem:
    try:
        return PriceVersionItem.model_validate(
            await price_book_service.activate(
                session,
                context=context,
                version_id=version_id,
                expected_version=payload.expected_version,
                reason=payload.reason,
            )
        )
    except PriceBookError as error:
        raise http_error(error) from error


@router.put("/versions/{version_id}/draft", response_model=PriceVersionItem)
async def update_draft(
    version_id: UUID,
    payload: PriceVersionUpdate,
    context: ManageContext,
    session: DatabaseSession,
) -> PriceVersionItem:
    try:
        return PriceVersionItem.model_validate(
            await price_book_service.update_draft(
                session,
                context=context,
                version_id=version_id,
                payload=payload,
            )
        )
    except PriceBookError as error:
        raise http_error(error) from error


@router.post("/versions/{version_id}/inactivate", response_model=PriceVersionItem)
async def inactivate(
    version_id: UUID,
    payload: LifecycleRequest,
    context: ActivateContext,
    session: DatabaseSession,
) -> PriceVersionItem:
    try:
        return PriceVersionItem.model_validate(
            await price_book_service.transition_lifecycle(
                session,
                context=context,
                version_id=version_id,
                target_status="inactive",
                expected_version=payload.expected_version,
                reason=payload.reason,
            )
        )
    except PriceBookError as error:
        raise http_error(error) from error


@router.post("/versions/{version_id}/archive", response_model=PriceVersionItem)
async def archive(
    version_id: UUID,
    payload: LifecycleRequest,
    context: ActivateContext,
    session: DatabaseSession,
) -> PriceVersionItem:
    try:
        return PriceVersionItem.model_validate(
            await price_book_service.transition_lifecycle(
                session,
                context=context,
                version_id=version_id,
                target_status="archived",
                expected_version=payload.expected_version,
                reason=payload.reason,
            )
        )
    except PriceBookError as error:
        raise http_error(error) from error


@router.post(
    "/service-items/{item_id}/snapshots",
    response_model=SnapshotItem,
    status_code=status.HTTP_201_CREATED,
)
async def snapshot(
    item_id: UUID,
    payload: SnapshotRequest,
    context: ManageContext,
    session: DatabaseSession,
) -> SnapshotItem:
    try:
        return SnapshotItem.model_validate(
            await price_book_service.snapshot(
                session, context=context, item_id=item_id, payload=payload
            )
        )
    except PriceBookError as error:
        raise http_error(error) from error


@router.get("/snapshots/{snapshot_id}", response_model=SnapshotItem)
async def get_snapshot(
    snapshot_id: UUID,
    context: ReadContext,
    session: DatabaseSession,
) -> SnapshotItem:
    try:
        return SnapshotItem.model_validate(
            await price_book_service.get_snapshot(
                session, context=context, snapshot_id=snapshot_id
            )
        )
    except PriceBookError as error:
        raise http_error(error) from error


@router.get("/audit", response_model=tuple[AuditItem, ...])
async def audit_history(
    context: ReadContext,
    session: DatabaseSession,
    entity_id: Annotated[UUID | None, Query()] = None,
) -> tuple[AuditItem, ...]:
    return await price_book_service.audit_history(
        session, context=context, entity_id=entity_id
    )
