from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.beacon.schemas import BeaconSignalPage, BeaconSignalResponse
from app.beacon.service import SIGNAL_TTL, beacon_query_service
from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AnalyticsPermission
from app.platform.permissions.dependencies import require_permission

router = APIRouter(prefix="/api/v1/beacon", tags=["Beacon"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
BeaconReader = Annotated[
    AuthorizationContext,
    Depends(require_permission(AnalyticsPermission.READ)),
]


@router.get(
    "/signals",
    response_model=BeaconSignalPage,
    summary="List deterministic operational signals",
)
async def list_beacon_signals(
    session: DatabaseSession,
    context: BeaconReader,
) -> BeaconSignalPage:
    evaluated_at = datetime.now(timezone.utc)
    signals = await beacon_query_service.list_signals(
        session,
        context=context,
        now=evaluated_at,
    )
    return BeaconSignalPage(
        items=tuple(BeaconSignalResponse.model_validate(item) for item in signals),
        evaluated_at=evaluated_at,
        expires_at=evaluated_at + SIGNAL_TTL,
    )
