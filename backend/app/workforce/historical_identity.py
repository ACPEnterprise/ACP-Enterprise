from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.permissions.authorization import AuthorizationContext

from .models import HistoricalWorkforceIdentity


class HistoricalWorkforceIdentityService:
    async def list(
        self, session: AsyncSession, *, context: AuthorizationContext
    ) -> tuple[HistoricalWorkforceIdentity, ...]:
        rows = await session.scalars(
            select(HistoricalWorkforceIdentity)
            .where(HistoricalWorkforceIdentity.company_id == context.company.id)
            .order_by(
                HistoricalWorkforceIdentity.display_name,
                HistoricalWorkforceIdentity.source_system,
                HistoricalWorkforceIdentity.source_identity,
            )
        )
        return tuple(rows.all())


historical_workforce_identity_service = HistoricalWorkforceIdentityService()
