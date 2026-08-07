from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.audit.contracts import AuditQuery, AuditRecordView
from app.platform.audit.repository import AuditReadRepository, audit_read_repository
from app.platform.permissions.authorization import (
    AuthorizationContext,
    TenantAccessDeniedError,
)


class AuditAccessService:
    def __init__(self, repository: AuditReadRepository = audit_read_repository) -> None:
        self.repository = repository

    async def list_records(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        branch_id: UUID | None,
        limit: int,
    ) -> tuple[AuditRecordView, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("Audit result limit must be between 1 and 100.")
        if branch_id is not None and not context.can_access_branch(branch_id):
            raise TenantAccessDeniedError("Branch access denied.")
        return await self.repository.list_company_records(
            session,
            query=AuditQuery(
                company_id=context.company.id,
                authorized_branch_ids=context.authorized_branch_ids,
                has_all_branch_access=context.membership.has_all_branch_access,
                branch_id=branch_id,
                limit=limit,
            ),
        )


audit_access_service = AuditAccessService()
