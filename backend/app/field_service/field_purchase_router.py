from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import InventoryPermission, PurchasingPermission
from app.platform.permissions.dependencies import require_permission

from .errors import FieldServiceError
from .field_purchase_schemas import FieldPurchaseReviewSummary, VendorMappingCreate
from .field_purchases import field_purchase_service
from .router import field_error

router = APIRouter(prefix="/api/v1/field-purchases", tags=["Field Purchase Review"])
Session = Annotated[AsyncSession, Depends(get_database_session)]
InventoryRead = Annotated[
    AuthorizationContext, Depends(require_permission(InventoryPermission.READ))
]
PurchasingManage = Annotated[
    AuthorizationContext, Depends(require_permission(PurchasingPermission.MANAGE))
]


@router.get("/review", response_model=tuple[FieldPurchaseReviewSummary, ...])
async def field_purchase_review(
    context: InventoryRead, session: Session
) -> tuple[FieldPurchaseReviewSummary, ...]:
    try:
        return await field_purchase_service.review_queue(session, context=context)
    except FieldServiceError as error:
        raise field_error(error) from error


@router.post("/vendor-mappings", status_code=201)
async def certify_vendor_mapping(
    payload: VendorMappingCreate, context: PurchasingManage, session: Session
) -> dict[str, object]:
    try:
        mapping = await field_purchase_service.certify_mapping(
            session, context=context, payload=payload
        )
        return {
            "id": mapping.id,
            "vendor_id": mapping.vendor_id,
            "vendor_code": mapping.vendor_code,
            "inventory_item_id": mapping.inventory_item_id,
            "version": mapping.version,
            "active": mapping.active,
        }
    except FieldServiceError as error:
        raise field_error(error) from error
