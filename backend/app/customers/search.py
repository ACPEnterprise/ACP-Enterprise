from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.models import Customer
from app.customers.repository import CustomerRepository
from app.customers.schemas import CustomerSearchQuery
from app.platform.permissions.authorization import AuthorizationContext


class CustomerSearchService:
    async def search(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        criteria: CustomerSearchQuery,
    ) -> tuple[list[Customer], int]:
        return await CustomerRepository.search_customers(
            session,
            company_id=context.company.id,
            criteria=criteria,
        )


customer_search_service = CustomerSearchService()
