from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.audit.contracts import AuditQuery, AuditRecordView
from app.platform.audit.models import AuditRecord


class AuditReadRepository:
    async def list_company_records(
        self, session: AsyncSession, *, query: AuditQuery
    ) -> tuple[AuditRecordView, ...]:
        statement: Select[tuple[AuditRecord]] = select(AuditRecord).where(
            AuditRecord.company_id == query.company_id
        )
        if query.branch_id is not None:
            statement = statement.where(AuditRecord.branch_id == query.branch_id)
        elif not query.has_all_branch_access:
            statement = statement.where(
                AuditRecord.branch_id.in_(query.authorized_branch_ids)
            )
        records = await session.scalars(
            statement.order_by(
                AuditRecord.occurred_at.desc(), AuditRecord.id.desc()
            ).limit(query.limit)
        )
        return tuple(
            AuditRecordView(
                id=record.id,
                action=record.action,
                outcome=record.outcome,
                actor_user_id=record.actor_user_id,
                company_id=record.company_id,  # type: ignore[arg-type]
                branch_id=record.branch_id,
                resource_type=record.resource_type,
                resource_id=record.resource_id,
                reason_code=record.reason_code,
                correlation_id=record.correlation_id,
                details=record.details,
                occurred_at=record.occurred_at,
            )
            for record in records
        )


audit_read_repository = AuditReadRepository()
