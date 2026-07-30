from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.customer_migration.adapter_import import (
    ApprovedCustomerImportBoundary,
    CustomerAdapterImportReport,
    CustomerAdapterImportService,
    ReviewedCustomerAdapterOutput,
)
from app.platform.permissions.authorization import AuthorizationContext


class CustomerImportFacade:
    """Authoritative production entry point for reviewed Customer adapter imports."""

    def __init__(self, service: CustomerAdapterImportService | None = None) -> None:
        self.service = service or CustomerAdapterImportService()

    async def import_reviewed(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        reviewed: ReviewedCustomerAdapterOutput,
        boundary: ApprovedCustomerImportBoundary,
    ) -> CustomerAdapterImportReport:
        return await self.service.run(
            factory,
            context=context,
            reviewed=reviewed,
            boundary=boundary,
        )


customer_import_facade = CustomerImportFacade()
